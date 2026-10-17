"""Transactional ingestion regressions against an isolated database."""

import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from strava_lens.models import Base, ImportJob, Record, Setting, Snapshot
from strava_lens.imports import claim, enqueue, process


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DATA_DIR": self.temp.name})
        self.env.start()
        self.engine = create_engine("sqlite:///" + self.temp.name + "/test.db")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.records = json.loads(
            (
                Path(__file__).parents[2] / "tests/fixtures/golden_gpx_export.json"
            ).read_text()
        )
        from types import SimpleNamespace

        self.identity = patch(
            "strava_lens_parser.inspect_export",
            return_value=SimpleNamespace(
                snapshot_id=next(
                    r["snapshot_id"] for r in self.records if r["kind"] == "snapshot"
                )
            ),
        )
        self.identity.start()
        self.records.sort(key=lambda r: r["kind"] == "snapshot")

    def tearDown(self):
        self.identity.stop()
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def job(self):
        with self.factory() as session:
            return enqueue(io.BytesIO(b"archive"), session).id

    def run_job(self, jid, rows=None):
        with self.factory() as session:
            job = claim(session)
        with patch(
            "strava_lens.imports.iter_export", return_value=iter(rows or self.records)
        ):
            process(jid, job.lease_owner, self.factory)

    def test_ready_and_repeated_import_reuse_records(self):
        self.run_job(self.job())
        with self.factory() as session:
            first_count = session.scalar(select(func.count()).select_from(Record))
            self.assertEqual(session.scalar(select(Snapshot.status)), "ready")
        self.run_job(self.job())
        with self.factory() as session:
            self.assertEqual(
                first_count, session.scalar(select(func.count()).select_from(Record))
            )
            self.assertIsNotNone(session.get(Setting, "active_snapshot"))

    def test_partial_failure_never_activates(self):
        jid = self.job()
        with self.assertRaises(ValueError):
            self.run_job(jid, self.records[:-1])
        with self.factory() as session:
            self.assertEqual(session.get(ImportJob, jid).status, "failed")
            self.assertIsNone(session.get(Setting, "active_snapshot"))

    def test_expired_lease_is_reclaimed_and_fenced(self):
        jid = self.job()
        with self.factory() as session:
            first = claim(session)
            old_owner = first.lease_owner
            first.lease_until = time.time() - 1
            session.commit()
            second = claim(session)
            self.assertNotEqual(old_owner, second.lease_owner)
            self.assertEqual(second.attempts, 2)
        with patch("strava_lens.imports.iter_export", return_value=iter(self.records)):
            with self.assertRaises(ValueError):
                process(jid, old_owner, self.factory)
        with self.factory() as session:
            self.assertEqual(session.get(ImportJob, jid).status, "running")

    def test_upload_limit_removes_partial(self):
        with self.factory() as session, patch("strava_lens.imports.MAX_UPLOAD", 2):
            with self.assertRaises(ValueError):
                enqueue(io.BytesIO(b"123"), session)
        self.assertFalse(list(Path(self.temp.name).rglob("*.partial")))
