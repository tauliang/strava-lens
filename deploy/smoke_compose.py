"""Exercise an already-started disposable Compose stack with synthetic ZIPs.

Run from repository root: python -m deploy.smoke_compose /absolute/test-inbox
Set LENS_TEST_URL and TRAINING_LENS_TOKEN. Never point this at a personal instance.
"""

import json
import os
from pathlib import Path
import sys
import time
import urllib.request

from tests.test_csv import data
from tests.test_export import fixture


def request(path):
    req = urllib.request.Request(
        os.getenv("LENS_TEST_URL", "http://localhost:8080") + "/api" + path,
        headers={"Authorization": "Bearer " + os.environ["TRAINING_LENS_TOKEN"]},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def wait_ready(expected_jobs):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        jobs = request("/imports")
        if any(job["status"] == "failed" for job in jobs):
            raise AssertionError("Synthetic import failed")
        if len(jobs) == expected_jobs and all(job["status"] == "ready" for job in jobs):
            return
        time.sleep(2)
    raise AssertionError("Timed out waiting for the worker")


def main():
    inbox = Path(sys.argv[1]).resolve()
    assert inbox.is_dir(), "Create the temporary host inbox first"
    assert request("/imports") == [], "Use a fresh disposable Compose project"
    temporary = inbox / "first.partial"
    fixture(temporary)
    temporary.rename(inbox / "first.zip")
    wait_ready(1)
    # Identical contents under a new filename must not create another job.
    (inbox / "duplicate.zip").write_bytes((inbox / "first.zip").read_bytes())
    time.sleep(6)
    assert len(request("/imports")) == 1, "Identical archive was enqueued again"
    payload = data(**{"7": "activities/a.gpx"})
    payload += data(**{"0": "2", "7": ""}).split(b"\n", 1)[1]
    fixture(temporary, payload=payload)
    temporary.rename(inbox / "second.zip")
    wait_ready(2)
    overview = request("/dashboards/overview")
    total = sum(p["y"] or 0 for s in overview["panels"][0]["series"] for p in s["data"])
    assert total == 2, "Overlapping export inflated activity totals"
    assert len(request("/dashboards")["dashboards"]) == 10
    print(
        "Compose smoke passed: external ZIP discovery, identical ZIP skip, overlapping export totals"
    )


if __name__ == "__main__":
    main()
