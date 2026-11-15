from __future__ import annotations

from datetime import date, datetime, timedelta
import os
from pathlib import Path
import sys
import tempfile
import unittest

from starlette.background import BackgroundTasks
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from astro_market.api import (  # noqa: E402
    RangeCalculationRequest,
    TimingAnalysisRequest,
    analyze_published_timing,
    calculate_interval,
    calculation_run_details,
    calculation_run_events,
    start_range_calculation,
    timing_comparisons,
    trader_observations,
)
from astro_market.db.sqlite import initialize_database  # noqa: E402


class CalculatorRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db = os.environ.get("ASTRO_DB_PATH")
        self.previous_ephe = os.environ.get("ASTRO_EPHE_PATH")
        os.environ["ASTRO_DB_PATH"] = str(Path(self.temp_dir.name) / "test.sqlite3")
        os.environ["ASTRO_EPHE_PATH"] = str(BACKEND / "ephe")
        initialize_database()

    def tearDown(self) -> None:
        if self.previous_db is None:
            os.environ.pop("ASTRO_DB_PATH", None)
        else:
            os.environ["ASTRO_DB_PATH"] = self.previous_db
        if self.previous_ephe is None:
            os.environ.pop("ASTRO_EPHE_PATH", None)
        else:
            os.environ["ASTRO_EPHE_PATH"] = self.previous_ephe
        self.temp_dir.cleanup()

    def test_range_calculation_persists_event_and_orb_details(self) -> None:
        request = RangeCalculationRequest(
            start_date=date(2026, 5, 26),
            end_date=date(2026, 5, 26),
            pairs=[("Moon", "Venus")],
            aspects=["Square"],
        )
        tasks = BackgroundTasks()
        queued = start_range_calculation(request, tasks)
        self.assertEqual(queued.status, "running")
        start = datetime(2026, 5, 26, tzinfo=ZoneInfo("Asia/Kolkata"))
        calculate_interval(queued.id, start, start + timedelta(days=1), [("Moon", "Venus")], ["Square"], "Asia/Kolkata")

        result = calculation_run_details(queued.id)
        events = calculation_run_events(queued.id)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.event_count, 1)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.aspect_name, "Square")
        self.assertEqual(event.timezone, "Asia/Kolkata")
        self.assertIsNotNone(event.orb_before_degrees)
        self.assertIsNotNone(event.orb_after_degrees)
        self.assertEqual(event.calculation_settings["zodiac"], "tropical")

    def test_user_supplied_timing_sources_and_formula_comparisons_are_separate(self) -> None:
        observations = trader_observations()
        self.assertEqual(len(observations), 6)
        self.assertEqual(sum(len(item["published_times"]) for item in observations), 25)
        selected = observations[0]
        result = analyze_published_timing(
            TimingAnalysisRequest(
                published_event_id=selected["id"],
                method="session_open_interval",
                interval_minutes=65,
            )
        )
        self.assertEqual(result["candidate_times"][0], "09:15")
        self.assertGreater(result["random_phase_baseline_rmse_minutes"], 0)
        self.assertEqual(len(timing_comparisons(selected["id"])), 1)


if __name__ == "__main__":
    unittest.main()
