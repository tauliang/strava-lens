"""Shared upload/watch ingestion with fenced worker leases and atomic activation."""

import hashlib
import os
from pathlib import Path
import time
import threading
import uuid
from collections import Counter

from sqlalchemy import or_, select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from strava_lens_parser import iter_export
from .db import SessionLocal
from .models import ImportJob, Record, Setting, Snapshot, SnapshotRecord

MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024**3)))
LEASE_SECONDS = 120
MAX_ATTEMPTS = 3


def data_dir():
    path = Path(os.getenv("DATA_DIR", "./data")) / "archives"
    path.mkdir(parents=True, exist_ok=True)
    return path


def enqueue(stream, session):
    """Copy into immutable content-addressed storage; filenames are never trusted."""
    temporary = data_dir() / (str(uuid.uuid4()) + ".partial")
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("xb") as destination:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise ValueError("upload_too_large")
                digest.update(chunk)
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        target = data_dir() / (digest.hexdigest() + ".zip")
        try:
            os.link(temporary, target)
        except FileExistsError:
            pass
        config_row = session.get(Setting, "config")
        config = config_row.value if config_row else {}
        job = ImportJob(
            id=str(uuid.uuid4()),
            archive_path=str(target.resolve()),
            archive_hash=digest.hexdigest(),
            status="queued",
            created_at=time.time(),
            updated_at=time.time(),
            config=config,
        )
        session.add(job)
        session.commit()
        return job
    finally:
        temporary.unlink(missing_ok=True)


def claim(session):
    now = time.time()
    session.execute(
        update(ImportJob)
        .where(
            ImportJob.status == "running",
            ImportJob.lease_until < now,
            ImportJob.attempts >= MAX_ATTEMPTS,
        )
        .values(status="failed", error="RetryLimitExceeded")
    )
    session.commit()
    # Conditional UPDATE fences simultaneous claimers on both SQLite/PostgreSQL.
    candidate = session.scalar(
        select(ImportJob.id)
        .where(
            or_(
                ImportJob.status == "queued",
                (ImportJob.status == "running") & (ImportJob.lease_until < now),
            ),
            ImportJob.attempts < MAX_ATTEMPTS,
        )
        .order_by(ImportJob.created_at)
        .limit(1)
    )
    if not candidate:
        return None
    owner = str(uuid.uuid4())
    result = session.execute(
        update(ImportJob)
        .where(
            ImportJob.id == candidate,
            or_(
                ImportJob.status == "queued",
                (ImportJob.status == "running") & (ImportJob.lease_until < now),
            ),
            ImportJob.attempts < MAX_ATTEMPTS,
        )
        .values(
            status="running",
            lease_owner=owner,
            lease_until=now + LEASE_SECONDS,
            attempts=ImportJob.attempts + 1,
            updated_at=now,
        )
    )
    session.commit()
    return session.get(ImportJob, candidate) if result.rowcount else None


def _insert(session, model, values):
    dialect = session.bind.dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    session.execute(insert(model).values(values).on_conflict_do_nothing())


def process(job_id, owner, factory=SessionLocal):
    """Maintain a lease even while a large individual FIT file is decoding."""
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(LEASE_SECONDS / 3):
            with factory.begin() as session:
                session.execute(
                    update(ImportJob)
                    .where(
                        ImportJob.id == job_id,
                        ImportJob.lease_owner == owner,
                        ImportJob.status == "running",
                        ImportJob.lease_until >= time.time(),
                    )
                    .values(lease_until=time.time() + LEASE_SECONDS)
                )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        _process(job_id, owner, factory)
    finally:
        stop.set()
        thread.join(timeout=5)


def _process(job_id, owner, factory):
    """Stage immutable records; only an exhausted, reconciled snapshot is readable."""
    with factory() as session:
        job = session.get(ImportJob, job_id)
        settings = dict(job.config)
        timezone = settings.pop("timezone", "UTC")
        counts = Counter()
        members = []
        manifest = None
        from strava_lens_parser import inspect_export

        sid = None
        batch = []
        try:
            sid = inspect_export(
                job.archive_path, timezone=timezone, config=settings
            ).snapshot_id
            for record in iter_export(
                job.archive_path,
                timezone=timezone,
                config=settings,
                observed_at=job.created_at,
            ):
                if record["kind"] == "snapshot":
                    manifest = record
                if sid is None and record.get("snapshot_id"):
                    sid = record["snapshot_id"]
                counts[record["kind"]] += 1
                if record["kind"] == "membership":
                    members.append(record)
                batch.append(record)
                if len(batch) >= 500:
                    _stage(factory, job_id, owner, sid, batch)
                    batch.clear()
            if manifest is None:
                raise ValueError("missing_manifest")
            sid = manifest["snapshot_id"]
            _stage(factory, job_id, owner, sid, batch)
            expected = sum(
                counts[k]
                for k in ("activity", "social", "exercise", "goal", "gear_threshold")
            )
            if (
                expected != manifest["expected_records"]
                or 1 + len(members) != manifest["expected_groups"]
            ):
                raise ValueError("manifest_mismatch")
            with factory.begin() as final:
                fenced = final.execute(
                    update(ImportJob)
                    .where(
                        ImportJob.id == job_id,
                        ImportJob.lease_owner == owner,
                        ImportJob.status == "running",
                        ImportJob.lease_until >= time.time(),
                    )
                    .values(
                        status="ready",
                        snapshot_id=sid,
                        progress=sum(counts.values()),
                        updated_at=time.time(),
                    )
                )
                if not fenced.rowcount:
                    raise ValueError("lease_lost")
                for member in members:
                    actual_count = final.scalar(
                        select(func.count())
                        .select_from(Record)
                        .join(
                            SnapshotRecord, Record.event_id == SnapshotRecord.event_id
                        )
                        .where(
                            SnapshotRecord.snapshot_id == sid,
                            Record.activity_id == member["activity_id"],
                            Record.kind.not_in(("membership", "activity")),
                            Record.payload["stream_revision_id"].as_string()
                            == member["stream_revision_id"],
                        )
                    )
                    if actual_count != member["expected_records"]:
                        raise ValueError("stream_count_mismatch")
                snapshot = final.get(Snapshot, sid)
                snapshot.status, snapshot.manifest = "ready", manifest
                active = final.get(Setting, "active_snapshot")
                if active:
                    active.value = {"id": sid}
                else:
                    final.add(Setting(key="active_snapshot", value={"id": sid}))
        except Exception as error:
            with factory.begin() as failed:
                failed.execute(
                    update(ImportJob)
                    .where(ImportJob.id == job_id, ImportJob.lease_owner == owner)
                    .values(
                        status="failed",
                        error=type(error).__name__,
                        updated_at=time.time(),
                    )
                )
            raise


def _stage(factory, job_id, owner, sid, batch):
    with factory.begin() as session:
        result = session.execute(
            update(ImportJob)
            .where(
                ImportJob.id == job_id,
                ImportJob.lease_owner == owner,
                ImportJob.status == "running",
                ImportJob.lease_until >= time.time(),
            )
            .values(
                lease_until=time.time() + LEASE_SECONDS,
                updated_at=time.time(),
                progress=ImportJob.progress + len(batch),
            )
        )
        if not result.rowcount:
            raise ValueError("lease_lost")
        # Telemetry precedes its membership; buffer association until sid is known.
        if sid is None:
            job = session.get(ImportJob, job_id)
            from strava_lens_parser import inspect_export

            cfg = dict(job.config)
            sid = inspect_export(
                job.archive_path, timezone=cfg.pop("timezone", "UTC"), config=cfg
            ).snapshot_id
        _insert(
            session,
            Snapshot,
            {"id": sid, "status": "staging", "created_at": time.time(), "manifest": {}},
        )
        if batch:
            _insert(
                session,
                Record,
                [
                    {
                        "event_id": row["event_id"],
                        "kind": row["kind"],
                        "snapshot_id": row.get("snapshot_id"),
                        "activity_id": row.get("activity_id"),
                        "payload": row,
                    }
                    for row in batch
                ],
            )
            _insert(
                session,
                SnapshotRecord,
                [{"snapshot_id": sid, "event_id": row["event_id"]} for row in batch],
            )
