"""HTTP authentication, configuration and ready-snapshot boundaries."""

import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from strava_lens.app import app
from strava_lens.db import get_session
from strava_lens.models import Base, Snapshot


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite:///" + self.temp.name + "/test.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine)

        def session():
            with self.factory() as value:
                yield value

        app.dependency_overrides[get_session] = session
        self.env = patch.dict(
            os.environ,
            {"TRAINING_LENS_TOKEN": "test-secret", "DATA_DIR": self.temp.name},
        )
        self.env.start()
        self.client = TestClient(app, headers={"Authorization": "Bearer test-secret"})

    def tearDown(self):
        app.dependency_overrides.clear()
        self.env.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_auth_and_no_staging_visibility(self):
        self.assertEqual(TestClient(app).get("/api/snapshots").status_code, 401)
        with self.factory.begin() as session:
            session.add(
                Snapshot(id="partial", status="staging", created_at=1, manifest={})
            )
        self.assertEqual(self.client.get("/api/snapshots").json(), [])
        self.assertEqual(
            self.client.post("/api/snapshots/partial/activate").status_code, 404
        )

    def test_configuration_and_upload(self):
        response = self.client.put(
            "/api/config", json={"timezone": "America/New_York", "exact_gps": False}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["requires_reimport"])
        response = self.client.post(
            "/api/imports",
            files={"file": ("../../unsafe.zip", b"not a zip", "application/zip")},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(len(self.client.get("/api/imports").json()), 1)

    def test_dashboard_registry_and_empty_state(self):
        response = self.client.get("/api/dashboards")
        self.assertEqual(response.status_code, 200)
        for key in ("overview", "training", "activity_detail", "social", "vitals"):
            self.assertEqual(self.client.get("/api/dashboards/" + key).status_code, 200)
