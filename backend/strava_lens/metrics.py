"""Allowlisted metric metadata and unit conversions shared by API and UI."""

import csv
from pathlib import Path

with Path(__file__).with_name("metric_catalog.csv").open() as source:
    METRICS = {row["metric_id"]: row for row in csv.DictReader(source)}


def metadata(key: str, units: str = "metric") -> dict:
    """Return display metadata; executable expressions never come from requests."""
    row = METRICS[key]
    system = "imperial" if units.lower() == "imperial" else "metric"
    return {
        "key": key,
        "label": row["label"],
        "unit": row[f"{system}_unit"],
        "factor": float(row[f"{system}_factor"]),
        "group": row["group_id"],
    }
