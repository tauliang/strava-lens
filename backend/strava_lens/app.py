"""Authenticated HTTP boundary. Run behind a same-origin reverse proxy."""

import hmac
import os
from typing import Annotated
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .db import get_session
from .imports import enqueue
from .models import ImportJob, Setting, Snapshot, Record, SnapshotRecord


def authorize(authorization: str | None = Header(default=None)):
    token = os.getenv("TRAINING_LENS_TOKEN")
    if not token and os.getenv("ALLOW_INSECURE_LOCAL") != "1":
        raise HTTPException(503, "Configure TRAINING_LENS_TOKEN")
    if token and not hmac.compare_digest(authorization or "", "Bearer " + token):
        raise HTTPException(401, "Authentication required")


app = FastAPI(
    title="Training Lens API", version="0.1.0", dependencies=[Depends(authorize)]
)
DB = Annotated[Session, Depends(get_session)]


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = "UTC"
    exact_gps: bool = False
    hr_zones: list[float | dict] = Field(default_factory=list, max_length=10)
    goals: list[dict] = Field(default_factory=list, max_length=100)
    gear_thresholds: list[dict] = Field(default_factory=list, max_length=100)
    overrides: list[dict] = Field(default_factory=list, max_length=1000)
    privacy_zones: list[dict] = Field(default_factory=list, max_length=100)
    cadence_convention: str = "source"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as error:
            raise ValueError("Unknown IANA timezone") from error
        return value


@app.get("/api/health")
def health(session: DB):
    session.execute(select(1))
    return {"status": "ok"}


def job_json(job):
    return {
        key: getattr(job, key)
        for key in (
            "id",
            "status",
            "snapshot_id",
            "created_at",
            "updated_at",
            "attempts",
            "progress",
            "error",
        )
    }


@app.post("/api/imports", status_code=202)
def upload(session: DB, file: UploadFile = File(...)):
    try:
        return job_json(enqueue(file.file, session))
    except ValueError:
        raise HTTPException(413, "Archive exceeds upload limit") from None


@app.get("/api/imports")
def jobs(session: DB):
    return [
        job_json(j)
        for j in session.scalars(
            select(ImportJob).order_by(ImportJob.created_at.desc()).limit(100)
        )
    ]


@app.get("/api/imports/{job_id}")
def job(job_id: str, session: DB):
    row = session.get(ImportJob, job_id)
    if not row:
        raise HTTPException(404, "Import not found")
    return job_json(row)


@app.post("/api/imports/{job_id}/retry")
def retry(job_id: str, session: DB):
    row = session.get(ImportJob, job_id)
    if not row or row.status != "failed":
        raise HTTPException(409, "Only failed imports can be retried")
    row.status, row.attempts, row.error = "queued", 0, None
    session.commit()
    return job_json(row)


@app.get("/api/snapshots")
def snapshots(session: DB):
    active = session.get(Setting, "active_snapshot")
    return [
        {
            "id": row.id,
            "status": row.status,
            "created_at": row.created_at,
            "manifest": row.manifest,
            "active": bool(active and active.value["id"] == row.id),
        }
        for row in session.scalars(
            select(Snapshot)
            .where(Snapshot.status == "ready")
            .order_by(Snapshot.created_at.desc())
        )
    ]


@app.post("/api/snapshots/{snapshot_id}/activate")
def activate(snapshot_id: str, session: DB):
    row = session.get(Snapshot, snapshot_id)
    if not row or row.status != "ready":
        raise HTTPException(404, "Ready snapshot not found")
    session.merge(Setting(key="active_snapshot", value={"id": snapshot_id}))
    session.commit()
    return {"id": snapshot_id}


@app.get("/api/config")
def config(session: DB):
    row = session.get(Setting, "config")
    return row.value if row else Configuration().model_dump()


@app.put("/api/config")
def configure(value: Configuration, session: DB):
    session.merge(Setting(key="config", value=value.model_dump()))
    session.commit()
    return {**value.model_dump(), "requires_reimport": True}


from . import analytics  # noqa: E402


def snapshot_records(session, snapshot_id=None, include_samples=False):
    if not snapshot_id:
        active = session.get(Setting, "active_snapshot")
        snapshot_id = active.value["id"] if active else None
    row = session.get(Snapshot, snapshot_id) if snapshot_id else None
    if not row or row.status != "ready":
        return [], snapshot_id
    query = (
        select(Record.payload)
        .join(SnapshotRecord, Record.event_id == SnapshotRecord.event_id)
        .where(SnapshotRecord.snapshot_id == snapshot_id)
    )
    if not include_samples:
        query = query.where(Record.kind != "sample")
    records = session.scalars(query).all()
    return records, snapshot_id


@app.get("/api/dashboards")
def dashboards(session: DB, snapshot_id: str | None = None):
    records, _ = snapshot_records(session, snapshot_id)
    return analytics.dashboard_registry(records)


@app.get("/api/dashboards/{dashboard_id}")
def dashboard(
    dashboard_id: str, request: Request, session: DB, snapshot_id: str | None = None
):
    records, selected = snapshot_records(session, snapshot_id)
    if dashboard_id == "data_health":
        records += [
            {"kind": "worker", **job_json(job)}
            for job in session.scalars(
                select(ImportJob).order_by(ImportJob.created_at.desc()).limit(100)
            )
        ]
    if dashboard_id == "activity_detail":
        activity_id = request.query_params.get("activity_id")
        if activity_id:
            records += bounded_samples(session, selected, activity_id, 2000)
    if dashboard_id == "social":
        history = session.scalars(
            select(Record.payload)
            .join(SnapshotRecord, Record.event_id == SnapshotRecord.event_id)
            .join(Snapshot, Snapshot.id == SnapshotRecord.snapshot_id)
            .where(Snapshot.status == "ready", Record.kind == "social")
        ).all()
        seen = {r["event_id"] for r in records}
        records += [
            r
            for r in history
            if r.get("social_type") == "network"
            and r["event_id"] not in seen
            and not seen.add(r["event_id"])
        ]
    try:
        result = analytics.dashboard(dashboard_id, records, dict(request.query_params))
        result["snapshot_id"] = selected
        return result
    except (KeyError, ValueError) as error:
        status = 404 if dashboard_id not in analytics.DASHBOARDS else 422
        raise HTTPException(status, "Unknown dashboard or invalid metric") from error


@app.get("/api/activities")
def activities(
    session: DB, snapshot_id: str | None = None, offset: int = 0, limit: int = 100
):
    records, _ = snapshot_records(session, snapshot_id)
    return [r for r in records if r["kind"] == "activity"][
        max(0, offset) : max(0, offset) + min(500, max(1, limit))
    ]


def bounded_samples(session, snapshot_id, activity_id, limit):
    """SQL-scoped ordered telemetry with extrema and missing-value markers per bucket."""
    ready = session.get(Snapshot, snapshot_id) if snapshot_id else None
    if not ready or ready.status != "ready":
        return []
    query = (
        select(Record.payload)
        .join(SnapshotRecord, Record.event_id == SnapshotRecord.event_id)
        .where(
            SnapshotRecord.snapshot_id == snapshot_id,
            Record.activity_id == activity_id,
            Record.kind == "sample",
        )
    )
    count = session.scalar(select(func.count()).select_from(query.subquery()))
    if not count:
        return []
    metrics = ("speed_mps", "hr", "cadence", "watts", "altitude_m")
    # At most first/last + 3 representatives per metric + a time-gap marker.
    width = max(1, (count + max(1, limit // 20) - 1) // max(1, limit // 20))
    result, bucket = [], []
    previous_time = None

    def flush():
        chosen = {0, len(bucket) - 1}
        gap = next(
            (
                i
                for i, row in enumerate(bucket)
                if row.get("gap_before") or row.get("segment_start")
            ),
            None,
        )
        if gap is not None:
            chosen.add(gap)
        for metric in metrics:
            valid = [
                (i, row[metric])
                for i, row in enumerate(bucket)
                if isinstance(row.get(metric), (float, int))
            ]
            if valid:
                chosen.update(
                    (
                        min(valid, key=lambda x: x[1])[0],
                        max(valid, key=lambda x: x[1])[0],
                    )
                )
            missing = next(
                (i for i, row in enumerate(bucket) if row.get(metric) is None), None
            )
            if missing is not None:
                chosen.add(missing)
        result.extend(bucket[i] for i in sorted(chosen))
        bucket.clear()

    ordered = query.order_by(Record.payload["timestamp"].as_float()).execution_options(
        yield_per=1000
    )
    for row in session.scalars(ordered):
        clean = {
            k: v
            for k, v in row.items()
            if k not in ("latitude", "longitude", "lat", "lon")
        }
        timestamp = clean.get("timestamp")
        if (
            previous_time is not None
            and timestamp is not None
            and timestamp - previous_time > 30
        ):
            clean = {**clean, "gap_before": True}
        previous_time = timestamp
        bucket.append(clean)
        if len(bucket) >= width:
            flush()
    if bucket:
        flush()
    return result


@app.get("/api/activities/{activity_id}/streams")
def streams(
    activity_id: str, session: DB, snapshot_id: str | None = None, limit: int = 1000
):
    _, selected = snapshot_records(session, snapshot_id)
    ready = session.get(Snapshot, selected) if selected else None
    if not ready or ready.status != "ready":
        return []
    return bounded_samples(session, selected, activity_id, min(5000, max(20, limit)))
