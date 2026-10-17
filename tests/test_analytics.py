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
        result = dashboard("overview", [a, b], {"grain": "year"})
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
