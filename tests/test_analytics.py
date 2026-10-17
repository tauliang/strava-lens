"""Regression checks for semantic parity with the Splunk metric compiler."""

import unittest
from strava_lens.analytics import aggregate, dashboard, dashboard_registry


def activity(identity, **updates):
    return dict(
        kind="activity",
        event_id=identity,
        activity_id=identity,
        local_date="2024-01-01",
        sport="Run",
        distance_m=1000,
        moving_time_s=300,
        duration_valid=1,
        distance_valid=1,
        pace_valid=1,
        **updates,
    )


class AnalyticsTests(unittest.TestCase):
    def test_registry_covers_all_original_panels(self):
        registry = dashboard_registry()["dashboards"]
        self.assertEqual(len(registry), 10)
        self.assertEqual(sum(len(r["panels"]) for r in registry), 28)

    def test_weighted_heart_rate_and_ratio_pace(self):
        a = activity("a", average_hr=100)
        b = activity("b", average_hr=160)
        b.update(distance_m=3000, moving_time_s=900)
        self.assertEqual(aggregate([a, b], "avg_hr", {})[0], 145)
        self.assertEqual(aggregate([a, b], "pace", {})[0], 5)
        self.assertEqual(aggregate([a, b], "speed", {"units": "imperial"})[0], 7.46)

    def test_cadence_requires_explicit_convention(self):
        a = activity("a", average_cadence=85)
        self.assertEqual(aggregate([a], "cadence", {}), (None, 0))
        self.assertEqual(aggregate([a], "cadence", {"cadence": "strides"})[0], 170)

    def test_latest_snapshot_and_dedup(self):
        a = activity("a", snapshot_id="new")
        old = activity("old", snapshot_id="old")
        rows = [
            a,
            a,
            old,
            dict(kind="snapshot", snapshot_id="old", import_epoch=1),
            dict(kind="snapshot", snapshot_id="new", import_epoch=2),
        ]
        result = dashboard("overview", rows)
        self.assertEqual(result["panels"][0]["value"], 1)

    def test_missing_year_is_null_and_ski_speed_is_separate(self):
        a = activity("a")
        b = activity("b")
        b.update(local_date="2026-01-01", sport="AlpineSki")
        result = dashboard("overview", [a, b], {"grain": "year", "split": "sport"})
        series = result["panels"][1]["series"]
        self.assertEqual(len(series), 2)
        self.assertIsNone(series[0]["data"][1]["y"])

    def test_metric_id_allowlist(self):
        with self.assertRaises(ValueError):
            dashboard("overview", [], {"metric": "__bad__"})

    def test_invalid_measurements_remain_unavailable(self):
        a = activity("a", average_hr=999, max_hr=110)
        self.assertEqual(aggregate([a], "avg_hr", {}), (None, 0))
        self.assertEqual(aggregate([a], "peak_hr", {}), (None, 0))

    def test_validated_distance_and_coverage(self):
        a = activity("a")
        a.update(distance_valid=0)
        self.assertEqual(
            aggregate([a], "distance", {"quality": "validated"}), (None, 0)
        )
        self.assertEqual(aggregate([a], "hr_coverage", {})[0], 0)
        b = activity("b", average_hr=130)
        self.assertEqual(aggregate([a, b], "hr_coverage", {})[0], 50)

    def test_shared_telemetry_selected_by_revision(self):
        a = activity("a", stream_revision_id="revision")
        sample = dict(
            kind="sample",
            event_id="sample",
            stream_revision_id="revision",
            hr=140,
            timestamp=1,
            elapsed_s=1,
        )
        out = dashboard("activity_detail", [a, sample], {"activity_id": "a"})
        self.assertEqual(out["panels"][1]["series"][0]["data"][0]["y"], 140)

    def test_social_received_ranking_and_growth(self):
        rows = [
            dict(
                kind="social",
                event_id="a",
                social_type="interaction",
                direction="received",
                is_current_follower=1,
                actor_id="42",
                interaction_type="Comment",
            )
        ]
        result = dashboard("social", rows)
        self.assertEqual(result["panels"][2]["rows"][0]["interactions"], 1)

    def test_private_geography_cells_only(self):
        a = activity("a", stream_revision_id="r")
        geo = dict(
            kind="geography",
            stream_revision_id="r",
            latitude=20.005,
            longitude=30.005,
            event_id="g",
        )
        out = dashboard("geography", [a, geo])
        self.assertEqual(out["panels"][0]["rows"][0]["visits"], 1)

    def test_ytd_uses_export_calendar_day(self):
        a = activity("a", comparison_month_day="06-01")
        b = activity("b", comparison_month_day="06-01")
        b.update(local_date="2024-12-01")
        out = dashboard("overview", [a, b], {"grain": "year", "history": "ytd"})
        self.assertEqual(out["panels"][0]["value"], 1)

    def test_local_calendar_not_utc_bucket(self):
        a = activity("a", timestamp=1704067200)
        a.update(local_date="2023-12-31")
        out = dashboard("overview", [a], {"grain": "year"})
        self.assertEqual(out["panels"][1]["series"][0]["data"][0]["x"], "2023")

    def test_effort_comparison_preceding_recorded_weeks(self):
        rows = []
        for index, value in enumerate([10, 20, 30, 40, 50, 60]):
            a = activity(
                str(index),
                local_week_start=f"2024-0{index + 1}-01",
                relative_effort=value,
            )
            rows.append(a)
        out = dashboard(
            "training", rows, {"mode_training_details": "Effort comparison"}
        )
        self.assertEqual(out["panels"][2]["rows"][-1]["preceding_recorded_weeks"], 35)

    def test_annual_changes_fills_missing_year(self):
        a = activity("a")
        b = activity("b")
        b.update(local_date="2026-01-01")
        out = dashboard("overview", [a, b], {"mode_activities": "Annual changes"})
        rows = out["panels"][2]["rows"]
        self.assertEqual(rows[1]["activities"], 0)
        self.assertEqual(rows[1]["change_activities"], -1)
        self.assertIsNone(rows[2]["yoy_pct"])

    def test_annual_sport_coverage_has_speed_and_cadence(self):
        a = activity("a", average_cadence=90)
        out = dashboard(
            "gear_sports",
            [a],
            {
                "mode_sport_details": "Annual coverage",
                "cadence": "strides",
                "units": "imperial",
            },
        )
        row = out["panels"][2]["rows"][0]
        self.assertEqual(row["cadence"], 180)
        self.assertEqual(row["speed_unit"], "MPH")
        self.assertEqual(row["speed_coverage_pct"], 100)

    def test_activity_tables_project_product_columns_and_units(self):
        a = activity(
            "a", athlete_id="private", stream_revision_id="internal", average_hr=140
        )
        out = dashboard("overview", [a], {"units": "imperial"})
        row = out["panels"][2]["rows"][0]
        self.assertEqual(row["activity_id"], "a")
        self.assertEqual(row["distance"], 0.62)
        self.assertEqual(row["distance_unit"], "miles")
        self.assertEqual(row["moving_minutes"], 5)
        for field in (
            "event_id",
            "kind",
            "athlete_id",
            "stream_revision_id",
            "distance_m",
        ):
            self.assertNotIn(field, row)

    def test_network_history_ignores_relationship_rows_before_archive_dedup(self):
        common = dict(kind="social", archive_hash="same", timestamp=1704067200)
        relationship = dict(common, event_id="r", social_type="relationship")
        network = dict(
            common,
            event_id="n",
            social_type="network",
            followers=5,
            followers_available=1,
        )
        out = dashboard("social", [relationship, network])
        self.assertEqual(out["panels"][0]["series"][0]["data"][0]["y"], 5)

    def test_telemetry_breaks_lines_at_time_and_segment_boundaries(self):
        a = activity("a", stream_revision_id="r")
        samples = [
            dict(
                kind="sample",
                event_id="s1",
                stream_revision_id="r",
                elapsed_s=0,
                hr=100,
            ),
            dict(
                kind="sample",
                event_id="s2",
                stream_revision_id="r",
                elapsed_s=60,
                hr=150,
                gap_before=True,
            ),
            dict(
                kind="sample",
                event_id="s3",
                stream_revision_id="r",
                elapsed_s=61,
                hr=140,
            ),
            dict(
                kind="sample",
                event_id="s4",
                stream_revision_id="r",
                elapsed_s=90,
                hr=130,
                segment_start=True,
            ),
        ]
        out = dashboard(
            "activity_detail", [a, *samples], {"activity_id": "a", "grain": "year"}
        )
        data = out["panels"][1]["series"][0]["data"]
        self.assertEqual([p["y"] for p in data], [100, None, 150, 140, None, 130])
        self.assertEqual([float(p["x"]) for p in data], [0, 30, 60, 61, 75.5, 90])
        self.assertEqual(out["panels"][1]["coverage"], {"valid": 4, "total": 4})

    def test_combined_default_matches_selector_but_speed_keeps_sports_separate(self):
        a = activity("a")
        b = activity("b")
        b.update(sport="AlpineSki")
        overview = dashboard("overview", [a, b])
        self.assertEqual(len(overview["panels"][1]["series"]), 1)
        self.assertEqual(overview["panels"][1]["series"][0]["data"][0]["y"], 2)
        for sport_filter in ({}, {"sport": ""}, {"sport": "All"}):
            out = dashboard(
                "run_performance",
                [a, b],
                {"metric_performance": "speed", **sport_filter},
            )
            self.assertEqual(len(out["panels"][0]["series"]), 2)

    def test_automatic_metric_selects_first_eligible_from_filtered_sources(self):
        a = activity("a")
        for filters in ({}, {"metric_load": "auto"}):
            out = dashboard("training", [a], filters)
            self.assertEqual(out["panels"][0]["metric"], "hours")
        out = dashboard("training", [a], {"metric_load": "effort"})
        self.assertEqual(out["panels"][0]["metric"], "effort")
        self.assertIn("message", out["panels"][0])
        self.assertFalse(out["panels"][0]["metrics"][0]["available"])
        self.assertEqual(
            dashboard_registry()["dashboards"][0]["panels"][0]["default_metric"], "auto"
        )

    def test_automatic_telemetry_zones_and_empty_filters(self):
        a = activity("a", stream_revision_id="r")
        sample = dict(
            kind="sample",
            event_id="s",
            stream_revision_id="r",
            elapsed_s=0,
            speed_mps=2,
        )
        out = dashboard("activity_detail", [a, sample], {"activity_id": "a"})
        self.assertEqual(out["panels"][1]["metric"], "sample_speed")
        out = dashboard("training", [a], {"sport": "Ride"})
        self.assertIn("message", out["panels"][0])
        zone = dict(
            kind="zone", event_id="z", stream_revision_id="r", zone=1, seconds=60
        )
        a.pop("moving_time_s")
        out = dashboard("training", [a, zone], {"metric_load": "zones"})
        self.assertEqual(out["panels"][0]["series"][0]["data"][0]["y"], 0.02)
