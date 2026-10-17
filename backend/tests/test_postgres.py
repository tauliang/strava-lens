"""Real PostgreSQL upload-to-dashboard regression, enabled by integration URL.

This uses an isolated schema and only synthetic exports; it never drops an existing
schema or reads the user's export. CI supplies the disposable PostgreSQL service.
"""

import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker
from strava_lens.app import app
from strava_lens.db import get_session
from strava_lens.imports import claim, process
from strava_lens.models import Base, Record
from tests.test_export import fixture
from tests.test_csv import data


@unittest.skipUnless(os.getenv("POSTGRES_TEST_URL"), "POSTGRES_TEST_URL not set")
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_upload_retry_and_all_dashboard_routes(self):
        engine = create_engine(os.environ["POSTGRES_TEST_URL"])
        schema = "lens_test_" + uuid.uuid4().hex
        with engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
        scoped = engine.execution_options(schema_translate_map={None: schema})
        Base.metadata.create_all(scoped)
        factory = sessionmaker(scoped, expire_on_commit=False)

        def session_dependency():
            with factory() as session:
                yield session

        app.dependency_overrides[get_session] = session_dependency
        try:
            with (
                tempfile.TemporaryDirectory() as directory,
                patch.dict(
                    os.environ,
                    {
                        "DATA_DIR": directory,
                        "TRAINING_LENS_TOKEN": "integration-test-token",
                    },
                ),
            ):
                client = TestClient(app)
                headers = {"Authorization": "Bearer integration-test-token"}
                self.assertEqual(client.get("/api/health").status_code, 401)
                archive = fixture(Path(directory) / "fixture.zip")
                counts = []
                for _ in range(2):
                    response = client.post(
                        "/api/imports",
                        headers=headers,
                        files={"file": ("fixture.zip", archive.read_bytes())},
                    )
                    self.assertEqual(response.status_code, 202)
                    with factory() as session:
                        job = claim(session)
                    process(job.id, job.lease_owner, factory)
                    counts.append(0)
                    with factory() as session:
                        counts[-1] = session.scalar(
                            select(func.count()).select_from(Record)
                        )
                self.assertEqual(counts[0], counts[1])
                # Overlapping full exports must replace membership, not add totals.
                for expected in (219, 220, 219):
                    header = data().split(b"\n", 1)[0] + b"\n"
                    payload = header + b"".join(
                        data(**{"0": str(index), "7": ""}).split(b"\n", 1)[1]
                        for index in range(expected)
                    )
                    fixture(archive, payload=payload)
                    response = client.post(
                        "/api/imports",
                        headers=headers,
                        files={"file": ("fixture.zip", archive.read_bytes())},
                    )
                    self.assertEqual(response.status_code, 202)
                    with factory() as session:
                        job = claim(session)
                    process(job.id, job.lease_owner, factory)
                    response = client.get("/api/dashboards/overview", headers=headers)
                    self.assertEqual(response.status_code, 200, response.text)
                    summary = response.json()["panels"][0]["series"]
                    total = sum(
                        point["y"] or 0
                        for series in summary
                        for point in series["data"]
                    )
                    self.assertEqual(total, expected)
                registry = client.get("/api/dashboards", headers=headers).json()[
                    "dashboards"
                ]
                self.assertEqual(len(registry), 10)
                self.assertEqual(sum(len(row["panels"]) for row in registry), 28)
                for dashboard in registry:
                    response = client.get(
                        "/api/dashboards/" + dashboard["id"], headers=headers
                    )
                    self.assertEqual(response.status_code, 200, response.text)
        finally:
            app.dependency_overrides.clear()
            with engine.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            engine.dispose()
