"""Deterministic dashboard projections over committed normalized export records.

The persistence adapter supplies only completed snapshots. No SQL or browser code is
constructed from metric identifiers. Missing observations stay null, never zero.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from statistics import median
from .metrics import METRICS, metadata

# Each entry maps directly to a Dashboard Studio visualization in Training Lens.
DASHBOARDS = {
    "overview": (
        "Training overview",
        [
            (
                "volume_summary",
                "Selected volume",
                "single",
                ["activities", "hours", "distance", "elevation", "active_days"],
            ),
            (
                "volume_chart",
                "Activity history",
                "chart",
                ["activities", "hours", "distance", "elevation", "active_days"],
            ),
            ("activities", "Activities and coverage", "table", []),
        ],
    ),
    "training": (
        "Training and goals",
        [
            (
                "load",
                "Training history",
                "chart",
                ["effort", "hours", "distance", "zones"],
            ),
            ("goals", "Configured goals · progress at import", "table", []),
            ("training_details", "Training details", "table", []),
        ],
    ),
    "run_performance": (
        "Sport performance",
        [
            (
                "performance",
                "Sport performance history",
                "chart",
                ["pace", "speed", "cadence", "avg_hr", "distance"],
            ),
            ("best_efforts", "Best efforts · elapsed seconds", "table", []),
            ("run_details", "Comparable runs / annual coverage", "table", []),
        ],
    ),
    "gear_sports": (
        "Gear and sports",
        [
            (
                "usage",
                "Gear / sport history",
                "chart",
                ["activities", "distance", "hours", "elevation"],
            ),
            (
                "equipment",
                "Equipment thresholds · recorded lifetime mileage",
                "table",
                [],
            ),
            ("sport_details", "Gear / sport details", "table", []),
        ],
    ),
    "geography": (
        "Geography",
        [
            ("map", "Privacy-masked visits · top 1000 cells", "map", []),
            ("geo_details", "Geography details", "table", []),
        ],
    ),
    "activity_detail": (
        "Activity detail",
        [
            ("summary", "Activity summary", "table", []),
            (
                "telemetry",
                "Activity telemetry",
                "chart",
                [
                    "sample_hr",
                    "sample_pace",
                    "sample_speed",
                    "sample_altitude",
                    "sample_cadence",
                    "sample_power",
                ],
            ),
            ("detail", "Activity details", "table", []),
        ],
    ),
    "social": (
        "Social network",
        [
            (
                "network",
                "Observed follower history",
                "chart",
                ["followers", "following", "pending", "mutual"],
            ),
            ("engagement", "Interactions", "chart", ["given", "received"]),
            ("followers", "Followers", "table", []),
            ("sources", "Current network and source availability", "table", []),
        ],
    ),
    "vitals": (
        "Vitals",
        [
            (
                "vital",
                "Exercise vitals history",
                "chart",
                ["hr_comparison", "avg_hr", "peak_hr", "weight"],
            ),
            ("zone_history", "Heart-rate zone history", "chart", ["zones"]),
            ("vitals_details", "Vitals coverage and limitations", "table", []),
        ],
    ),
    "data_health": (
        "Data health",
        [
            ("readiness", "Import readiness", "table", []),
            (
                "coverage",
                "Coverage history",
                "chart",
                ["hr_coverage", "effort_coverage", "stream_coverage"],
            ),
            ("diagnostics", "Diagnostics", "table", []),
        ],
    ),
    "setup": ("Setup", [("configuration", "Configuration", "table", [])]),
}

# Keep metric groups aligned with the original validated selector allowlists.
DASHBOARDS["overview"][1][0][3].append("flagged")
DASHBOARDS["overview"][1][1][3].append("flagged")
DASHBOARDS["training"][1][0][3][:] = ["effort", "hours", "activities", "zones"]
DASHBOARDS["gear_sports"][1][0][3][:] = [
    "activities",
    "distance",
    "hours",
    "speed",
    "pace",
    "elevation",
    "avg_hr",
]

MODES = {
    "activities": ["Recent activities", "Coverage", "Annual changes"],
    "training_details": [
        "Weekly log",
        "Effort comparison",
        "HR observation coverage",
        "Effort coverage",
    ],
    "sport_details": [
        "Gear usage",
        "Sport summaries",
        "Strength sessions",
        "Annual coverage",
    ],
    "run_details": ["Comparable runs", "Annual coverage"],
    "geo_details": ["Cells (top 1000)", "Sport coverage"],
    "detail": ["Laps", "Splits", "Zones", "Exercises"],
    "followers": ["Top interactions", "Roster", "Observed changes"],
    "vitals_details": ["Availability", "Annual coverage"],
    "readiness": ["Active snapshot", "Reconciliation", "Availability cache"],
    "diagnostics": [
        "Completeness",
        "Quality issues",
        "Import manifests",
        "Worker status",
    ],
}


def dashboard_registry(records=None):
    return {
        "dashboards": [
            {
                "id": key,
                "title": title,
                "description": description(key),
                "panels": [
                    {
                        "id": pid,
                        "title": label,
                        "type": kind,
                        "metrics": [metadata(m) for m in metrics],
                        "default_metric": metrics[0] if metrics else None,
                        "modes": MODES.get(pid, []),
                    }
                    for pid, label, kind, metrics in panels
                ],
            }
            for key, (title, panels) in DASHBOARDS.items()
        ]
    }


def description(key):
    if key == "social":
        return (
            "Follower counts are observed at import, not historical follow dates. "
            "Received interactions require supplemental source records."
        )
    if key == "vitals":
        return (
            "Exercise heart rate is not resting heart rate. "
            "VO₂ max and HRV are not imported or estimated. "
            "Weight retains unknown export units."
        )
    return (
        "Recorded export observations. Missing data remains unavailable. "
        "Select a metric, units and historical grain."
    )


def number(row, field):
    value = row.get(field)
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def eligible(row, key, filters):
    field = METRICS[key]["source_field"]
    value = number(row, field)
    if key in ("activities", "active_days", "flagged"):
        return True
    if key in ("pace", "speed"):
        return (
            row.get("pace_valid") == 1
            and (number(row, "distance_m") or 0) > 0
            and (number(row, "moving_time_s") or 0) > 0
        )
    if key in ("avg_hr", "hr_comparison"):
        return (
            value is not None
            and 0 < value <= 255
            and row.get("duration_valid") == 1
            and (number(row, "moving_time_s") or 0) > 0
        )
    if key == "peak_hr":
        return (
            value is not None
            and 0 < value <= 255
            and (row.get("average_hr") is None or value >= row["average_hr"])
        )
    if key == "cadence":
        return (
            row.get("sport") == "Run"
            and (value or 0) > 0
            and row.get("duration_valid") == 1
            and (number(row, "moving_time_s") or 0) > 0
            and filters.get("cadence", "unconfirmed").lower() not in ("unconfirmed", "")
        )
    if key in ("hours", "distance"):
        return value is not None and (
            filters.get("quality", "reported").lower() != "validated"
            or row.get("duration_valid" if key == "hours" else "distance_valid") == 1
        )
    if key == "stream_coverage":
        return row.get("stream_status") == "decoded"
    if key in ("weight", "hr_coverage"):
        return (value or 0) > 0
    if key == "effort_coverage":
        return value is not None
    if key in ("followers", "following", "pending", "mutual"):
        required = (
            ["followers_available"]
            if key in ("followers", "pending")
            else ["following_available"]
            if key == "following"
            else ["followers_available", "following_available"]
        )
        return row.get("social_type") == "network" and all(
            row.get(r) == 1 for r in required
        )
    if key in ("given", "received"):
        return (
            row.get("social_type") == "interaction"
            and row.get("direction") == key
            and (key != "received" or row.get("is_current_follower") == 1)
        )
    return value is not None


def aggregate(rows, key, filters):
    valid = [r for r in rows if eligible(r, key, filters)]
    meta = metadata(key, filters.get("units", "metric"))
    if not valid:
        return (
            (0.0, 0)
            if rows and METRICS[key]["aggregation_key"] == "coverage"
            else (None, 0)
        )
    row = METRICS[key]
    field = row["source_field"]
    operation = row["aggregation_key"]
    values = [number(r, field) or 0 for r in valid]
    if operation == "count":
        result = len(valid)
    elif operation == "distinct":
        result = len({r.get(field) for r in valid})
    elif operation == "coverage":
        result = len(valid) / len(rows)
    elif operation == "speed":
        result = sum(r["distance_m"] for r in valid) / sum(
            r["moving_time_s"] for r in valid
        )
    elif operation == "pace":
        result = sum(r["moving_time_s"] for r in valid) / sum(
            r["distance_m"] for r in valid
        )
    elif operation == "weighted":
        result = sum(v * r["moving_time_s"] for v, r in zip(values, valid)) / sum(
            r["moving_time_s"] for r in valid
        )
        if key == "cadence" and filters.get("cadence", "").lower() in (
            "strides",
            "strides/min",
        ):
            result *= 2
    elif operation == "max":
        result = max(values)
    elif operation == "median":
        result = median(values)
    elif operation == "mean":
        result = sum(values) / len(values)
    else:
        result = sum(values)
    return round(result * meta["factor"], 2), len(valid)


def date_of(row):
    return str(
        row.get("local_date")
        or datetime.fromtimestamp(row.get("timestamp", 0), timezone.utc).date()
    )


def bucket(row, grain):
    date = date_of(row)
    if grain == "year":
        return date[:4]
    if grain == "month":
        return date[:7]
    if grain == "day":
        return date
    return row.get("local_week_start") or str(
        (
            datetime.fromisoformat(date[:10])
            - timedelta(days=datetime.fromisoformat(date[:10]).weekday())
        ).date()
    )


def selected(records, filters):
    snapshots = [r for r in records if r.get("kind") == "snapshot"]
    sid = filters.get("snapshot", "latest")
    if sid == "latest" and snapshots:
        sid = max(
            snapshots, key=lambda r: r.get("import_epoch", r.get("timestamp", 0))
        )["snapshot_id"]
    base = [
        r
        for r in records
        if not r.get("snapshot_id") or sid == "latest" or r.get("snapshot_id") == sid
    ]
    activities = []
    for row in base:
        if row.get("kind") != "activity":
            continue
        if any(
            filters.get(k, "All") not in ("All", "all", "", None, row.get(k))
            for k in ("sport", "gear")
        ):
            continue
        if filters.get("quality", "").lower() in (
            "flagged",
            "flagged only",
        ) and not row.get("flagged"):
            continue
        day = date_of(row)
        if filters.get("grain", "month").lower() != "year" and (
            (filters.get("start") and day < filters["start"])
            or (filters.get("end") and day > filters["end"])
        ):
            continue
        if filters.get("history") in ("ytd", "Comparable YTD") and day[5:10] > row.get(
            "comparison_month_day", "12-31"
        ):
            continue
        if filters.get("activity_id") and str(row.get("activity_id")) != str(
            filters["activity_id"]
        ):
            continue
        activities.append(row)
    refs = {
        r.get("stream_revision_id") for r in activities if r.get("stream_revision_id")
    }
    associated = [
        r
        for r in records
        if r.get("stream_revision_id") in refs
        and r.get("kind") not in ("activity", "membership")
    ]
    return base, activities, associated


def chart(records, activities, associated, key, filters, panel_id):
    grain = filters.get("grain", "month").lower()
    source = METRICS[key]["source_kind"]
    rows = (
        activities
        if source == "activity"
        else [r for r in associated if r.get("kind") == source]
    )
    if source == "social":
        rows = [r for r in records if r.get("kind") == "social"]
        if key in ("followers", "following", "pending", "mutual"):
            unique = {}
            for row in sorted(
                rows, key=lambda r: r.get("import_epoch", r.get("timestamp", 0))
            ):
                unique.setdefault(row.get("archive_hash", row.get("event_id")), row)
            rows = list(unique.values())
        rows = [
            r
            for r in rows
            if (not filters.get("start") or date_of(r) >= filters["start"])
            and (not filters.get("end") or date_of(r) <= filters["end"])
        ]
    groups = defaultdict(list)
    parents = {
        r["stream_revision_id"]: r for r in activities if r.get("stream_revision_id")
    }
    for row in rows:
        parent = parents.get(row.get("stream_revision_id"), row)
        if key in ("followers", "following", "pending", "mutual"):
            if row.get("social_type") != "network":
                continue
            x = datetime.fromtimestamp(
                row.get("timestamp", 0), timezone.utc
            ).isoformat()
            label = "Observed at import"
        else:
            x = (
                str(row.get("elapsed_s", row.get("timestamp", 0)))
                if panel_id == "telemetry"
                else bucket(parent, grain)
            )
            split = filters.get("split", "sport")
            label = (
                str(parent.get(split, "Selected activities"))
                if split in ("sport", "gear")
                else "Selected activities"
            )
            if key in ("pace", "speed") and filters.get("sport", "All") == "All":
                label = str(parent.get("sport", "Unspecified"))
            if key == "zones":
                label = "Zone " + str(row.get("zone", "?"))
            if key in ("given", "received"):
                label = str(row.get("interaction_type", "Interaction"))
        groups[(x, label)].append(row)
    series = defaultdict(list)
    valid_count = 0
    total_count = 0
    keys = ["avg_hr", "peak_hr"] if key == "hr_comparison" else [key]
    for (x, label), items in sorted(
        groups.items(),
        key=lambda item: (
            float(item[0][0]) if panel_id == "telemetry" else item[0][0],
            item[0][1],
        ),
    ):
        for metric in keys:
            value, valid = aggregate(items, metric, filters)
            meta = metadata(metric, filters.get("units", "metric"))
            series[f"{label} · {meta['label']} ({meta['unit']})"].append(
                {"x": x, "y": value}
            )
            valid_count += valid
            total_count += len(items)
    # Retain visible annual gaps instead of joining across missing years.
    if grain == "year" and groups:
        years = [int(x) for x, _ in groups if x.isdigit() and len(x) == 4]
        if years:
            for name, data in series.items():
                points = {r["x"]: r["y"] for r in data}
                series[name] = [
                    {"x": str(y), "y": points.get(str(y))}
                    for y in range(min(years), max(years) + 1)
                ]
    return [{"name": name, "data": data} for name, data in series.items()], {
        "valid": valid_count,
        "total": total_count,
    }


def coverage_rows(activities, filters=None):
    filters = filters or {}
    grouped = defaultdict(list)
    for r in activities:
        grouped[(date_of(r)[:4], r.get("sport", "Unspecified"))].append(r)
    return [
        {
            "year": year,
            "sport": sport,
            "activities": len(items),
            "hr_activities": sum((number(r, "average_hr") or 0) > 0 for r in items),
            "effort_activities": sum(
                r.get("relative_effort") is not None for r in items
            ),
            "decoded_activities": sum(
                r.get("stream_status") == "decoded" for r in items
            ),
            "flagged_activities": sum(bool(r.get("flagged")) for r in items),
            "speed": aggregate(items, "speed", filters)[0],
            "speed_unit": metadata("speed", filters.get("units", "metric"))["unit"],
            "pace": aggregate(items, "pace", filters)[0],
            "cadence": aggregate(items, "cadence", filters)[0],
            "speed_coverage_pct": 100
            * sum(eligible(r, "speed", filters) for r in items)
            / len(items),
            "cadence_coverage_pct": 100
            * sum(eligible(r, "cadence", filters) for r in items)
            / len(items),
        }
        for (year, sport), items in sorted(grouped.items())
    ]


def table_rows(pid, base, activities, associated, records, filters):
    mode = filters.get("mode_" + pid, MODES.get(pid, [""])[0])
    if pid in ("activities", "summary"):
        if mode == "Coverage":
            return coverage_rows(activities, filters)
        if mode == "Annual changes":
            counts = Counter(
                (date_of(r)[:4], r.get("sport", "Unspecified")) for r in activities
            )
            years = [int(y) for y, _ in counts]
            result = []
            for sport in sorted({s for _, s in counts}):
                previous = None
                for year in range(min(years), max(years) + 1) if years else []:
                    count = counts[(str(year), sport)]
                    result.append(
                        {
                            "year": year,
                            "sport": sport,
                            "activities": count,
                            "previous_year_activities": previous,
                            "change_activities": count - previous
                            if previous is not None
                            else None,
                            "yoy_pct": round(100 * (count - previous) / previous, 1)
                            if previous
                            else None,
                        }
                    )
                    previous = count
            return result
        return sorted(activities, key=lambda r: r.get("timestamp", 0), reverse=True)[
            :100
        ]
    if pid in ("goals", "equipment"):
        return [
            r
            for r in base
            if r.get("kind") == ("goal" if pid == "goals" else "gear")
            or (pid == "equipment" and r.get("kind") == "gear_threshold")
        ]
    if pid == "best_efforts":
        best = {}
        for r in associated:
            if r.get("kind") != "best_effort" or filters.get(
                "effort_target", "All"
            ) not in ("All", str(r.get("target_m"))):
                continue
            key = r.get("target_m")
            val = r.get("duration_s")
            if val is not None and (key not in best or val < best[key]):
                best[key] = val
        return [{"target_m": k, "elapsed_seconds": v} for k, v in sorted(best.items())]
    if pid == "detail":
        kind = {
            "Laps": "lap",
            "Splits": "split",
            "Zones": "zone",
            "Exercises": "exercise",
        }.get(mode, "lap")
        ids = {str(r.get("activity_id")) for r in activities}
        return [
            r
            for r in associated + base
            if r.get("kind") == kind
            and (r in associated or str(r.get("activity_id")) in ids)
        ]
    if pid in ("vitals_details", "diagnostics", "run_details"):
        if mode == "Quality issues":
            return [r for r in activities if r.get("flagged")]
        if mode == "Import manifests":
            return [r for r in records if r.get("kind") == "snapshot"]
        if mode == "Worker status":
            return [r for r in records if r.get("kind") == "worker"]
        if mode == "Comparable runs":
            return [
                r
                for r in activities
                if r.get("sport") == "Run" and r.get("pace_valid") == 1
            ]
        if mode == "Availability":
            return [
                {
                    "activities": len(activities),
                    "average_hr_activities": sum(
                        (number(r, "average_hr") or 0) > 0 for r in activities
                    ),
                    "vo2_max": "Not imported; no estimate made",
                    "resting_hr": "Exercise HR is not resting HR",
                    "hrv": "No supported HRV imported",
                    "weight_basis": "Export units; activity dates, not weigh-in dates",
                }
            ]
        return coverage_rows(activities, filters)
    if pid in ("training_details", "sport_details"):
        if mode == "Annual coverage":
            return coverage_rows(activities, filters)
        if mode == "HR observation coverage":
            zones = {
                r.get("activity_id", r.get("stream_revision_id")): r
                for r in associated
                if r.get("kind") == "zone"
            }
            return [
                {
                    field: sum(r.get(field, 0) for r in zones.values())
                    for field in ("observed_s", "unobserved_s", "paused_s")
                }
            ]
        if mode == "Effort coverage":
            grouped = defaultdict(list)
            for r in activities:
                grouped[r.get("sport", "Unspecified")].append(r)
            return [
                {
                    "sport": sport,
                    "activities": len(items),
                    "known_effort": sum(
                        r.get("relative_effort") is not None for r in items
                    ),
                    "coverage_pct": aggregate(items, "effort_coverage", filters)[0],
                }
                for sport, items in grouped.items()
            ]
        if mode == "Effort comparison":
            grouped = defaultdict(list)
            for r in activities:
                grouped[bucket(r, "week")].append(r)
            result = []
            for week, items in sorted(grouped.items()):
                preceding = [
                    r["effort"] for r in result[-4:] if r["effort"] is not None
                ]
                result.append(
                    {
                        "local_week_start": week,
                        "effort": aggregate(items, "effort", filters)[0],
                        "preceding_recorded_weeks": sum(preceding) / len(preceding)
                        if preceding
                        else None,
                    }
                )
            return result
        if mode == "Strength sessions":
            return [
                r
                for r in activities
                if r.get("sport") in ("WeightTraining", "Weight Training", "Workout")
            ]
        groups = defaultdict(list)
        for r in activities:
            groups[
                str(
                    r.get("gear", "Unspecified")
                    if mode == "Gear usage"
                    else r.get("sport", "Unspecified")
                    if mode == "Sport summaries"
                    else bucket(r, "week")
                )
            ].append(r)
        return [
            {
                "group": k,
                **{
                    m: aggregate(items, m, filters)[0]
                    for m in ("activities", "hours", "distance", "effort", "avg_hr")
                },
            }
            for k, items in sorted(groups.items())
        ]
    if pid in ("map", "geo_details"):
        if mode == "Sport coverage":
            mapped = defaultdict(set)
            for row in associated:
                if row.get("kind") == "geography":
                    mapped[row.get("sport", "Unspecified")].add(row.get("activity_id"))
            return [
                {"sport": sport, "mapped_activities": len(ids)}
                for sport, ids in mapped.items()
            ]
        cells = defaultdict(set)
        for r in associated:
            if r.get("kind") == "geography" and r.get("latitude") is not None:
                cells[(r["latitude"], r["longitude"])].add(r.get("activity_id"))
        return [
            {"latitude": k[0], "longitude": k[1], "visits": len(v)}
            for k, v in sorted(cells.items(), key=lambda item: -len(item[1]))[:1000]
        ]
    if pid == "sources":
        return [
            {
                **r,
                "history": "Observed at import; no follow dates",
                "received_interactions": "Supplemental records supplied"
                if r.get("received_available")
                else "Unavailable; supply social_interactions.csv",
            }
            for r in base
            if r.get("social_type") == "network"
        ]
    if pid == "followers":
        if mode == "Roster":
            return [r for r in base if r.get("social_type") == "relationship"]
        if mode == "Observed changes":
            observations = sorted(
                [
                    r
                    for r in records
                    if r.get("social_type") == "network"
                    and r.get("followers_available")
                ],
                key=lambda r: r.get("timestamp", 0),
            )
            result = []
            previous = None
            seen = set()
            for r in observations:
                archive = r.get("archive_hash", r.get("snapshot_id"))
                if archive in seen:
                    continue
                seen.add(archive)
                result.append(
                    {
                        "observed_at": r.get("timestamp"),
                        "followers": r.get("followers"),
                        "previous_followers": previous,
                        "net_change": r["followers"] - previous
                        if previous is not None
                        else None,
                    }
                )
                previous = r["followers"]
            return result
        counts = defaultdict(Counter)
        for r in base:
            if (
                r.get("social_type") == "interaction"
                and r.get("direction") == "received"
                and r.get("is_current_follower") == 1
            ):
                counts[str(r.get("actor_id"))][str(r.get("interaction_type"))] += 1
        return sorted(
            [
                {
                    "follower_athlete_id": k,
                    "comments": v["Comment"],
                    "kudos": v["Kudos"],
                    "interactions": sum(v.values()),
                }
                for k, v in counts.items()
            ],
            key=lambda r: (
                -r["interactions"],
                -r["comments"],
                r["follower_athlete_id"],
            ),
        )[:20]
    if pid == "readiness":
        return [
            dict(
                r,
                status="committed",
                availability="Calculated directly; no stale lookup cache",
            )
            for r in base
            if r.get("kind") == "snapshot"
        ]
    if pid == "configuration":
        return [
            {
                "parser_version": r.get("parser_version"),
                "timezone": r.get("timezone"),
                "exact_gps": r.get("exact_gps"),
                "snapshot_id": r.get("snapshot_id"),
            }
            for r in base
            if r.get("kind") == "snapshot"
        ]
    return []


def dashboard(dashboard_id, records, filters=None):
    """Build one dashboard. Unknown dashboard/metric IDs raise ValueError."""
    if dashboard_id not in DASHBOARDS:
        raise ValueError("unknown_dashboard")
    filters = dict(filters or {})
    records = list(
        {r.get("event_id", str(i)): r for i, r in enumerate(records)}.values()
    )
    base, activities, associated = selected(records, filters)
    base = [
        r
        for r in base
        if r.get("kind") != "social"
        or r.get("social_type") != "interaction"
        or (
            (not filters.get("start") or date_of(r) >= filters["start"])
            and (not filters.get("end") or date_of(r) <= filters["end"])
        )
    ]
    title, definitions = DASHBOARDS[dashboard_id]
    panels = []
    for pid, label, kind, allowed in definitions:
        panel = {
            "id": pid,
            "title": label,
            "type": kind,
            "unit": "",
            "series": [],
            "rows": [],
            "coverage": {},
        }
        if allowed:
            metric = filters.get("metric_" + pid, filters.get("metric", allowed[0]))
            if metric not in allowed:
                raise ValueError("unsupported_metric")
            meta = metadata(metric, filters.get("units", "metric"))
            panel.update(title=meta["label"], unit=meta["unit"], metric=metric)
            chart_records = (
                records
                if metric in ("followers", "following", "pending", "mutual")
                else base
            )
            panel["series"], panel["coverage"] = chart(
                chart_records, activities, associated, metric, filters, pid
            )
            if kind == "single":
                panel["value"] = aggregate(activities, metric, filters)[0]
            panel["metrics"] = [
                {
                    **metadata(m, filters.get("units", "metric")),
                    "available": any(
                        eligible(r, m, filters)
                        for r in (
                            activities
                            if METRICS[m]["source_kind"] == "activity"
                            else base
                            if METRICS[m]["source_kind"] == "social"
                            else associated
                        )
                        if r.get("kind") == METRICS[m]["source_kind"]
                    ),
                }
                for m in allowed
            ]
            if not panel["series"]:
                panel["message"] = (
                    "No eligible observations for the selected metric and filters."
                )
        else:
            panel["rows"] = table_rows(
                pid, base, activities, associated, records, filters
            )
        panels.append(panel)
    return {
        "id": dashboard_id,
        "title": title,
        "description": description(dashboard_id),
        "panels": panels,
        "dimensions": {
            "sports": sorted(
                {
                    str(r.get("sport"))
                    for r in base
                    if r.get("kind") == "activity" and r.get("sport")
                }
            ),
            "gears": sorted(
                {
                    str(r.get("gear"))
                    for r in base
                    if r.get("kind") == "activity" and r.get("gear")
                }
            ),
        },
    }
