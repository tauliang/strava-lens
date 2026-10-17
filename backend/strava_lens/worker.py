"""Separate durable worker; SIGTERM stops after the current import."""

import logging
import os
from pathlib import Path
import signal
import time
from .db import SessionLocal
from .imports import claim, enqueue, process
from .models import ImportJob
from sqlalchemy import select

log = logging.getLogger(__name__)


def run():
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    stable = {}
    observed = {}
    while running:
        inbox = Path(
            os.getenv("INBOX_DIR", str(Path(os.getenv("DATA_DIR", "./data")) / "inbox"))
        )
        for path in inbox.glob("*.zip"):
            try:
                stat = path.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
                if stable.get(path) != signature:
                    stable[path] = signature
                    continue
                if observed.get(path) == signature:
                    continue
                import hashlib

                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                with SessionLocal() as session:
                    exists = session.scalar(
                        select(ImportJob.id)
                        .where(ImportJob.archive_hash == digest)
                        .limit(1)
                    )
                    if not exists:
                        with path.open("rb") as stream:
                            enqueue(stream, session)
                observed[path] = signature
            except OSError:
                log.warning("Watch file unavailable")
        with SessionLocal() as session:
            job = claim(session)
            if job:
                job_id, owner = job.id, job.lease_owner
        if job:
            try:
                process(job_id, owner)
            except Exception:
                log.warning(
                    "Import failed; details retained as safe category in job state"
                )
        else:
            time.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
