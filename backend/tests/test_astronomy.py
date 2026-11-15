from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from astro_market.astronomy import (  # noqa: E402
    ASPECTS,
    CalculationConfig,
    angular_separation,
    find_aspect_events,
)


EPHEMERIS_PATH = BACKEND / "ephe"
HAS_REQUIRED_FILES = all((EPHEMERIS_PATH / name).is_file() for name in ("sepl_18.se1", "semo_18.se1"))
CONFIG = CalculationConfig(
    ephemeris_path=str(EPHEMERIS_PATH) if HAS_REQUIRED_FILES else None,
    require_swiss_files=HAS_REQUIRED_FILES,
)
IST = ZoneInfo("Asia/Kolkata")


class AspectMathTests(unittest.TestCase):
    def test_standard_aspect_names_and_angles(self) -> None:
        self.assertEqual(
            ASPECTS,
            {
                "Conjunction": 0.0,
                "Semi-square": 45.0,
                "Sextile": 60.0,
                "Square": 90.0,
                "Trine": 120.0,
                "Sesquiquadrate": 135.0,
                "Opposition": 180.0,
            },
        )

    def test_separation_wraps_at_zero_degrees(self) -> None:
        self.assertAlmostEqual(angular_separation(359.0, 1.0), 2.0)


class SwissEphemerisEventTests(unittest.TestCase):
    def event_near(self, day: str, p1: str, p2: str, aspect: str, expected: str) -> None:
        start = datetime.fromisoformat(day).replace(tzinfo=IST)
        events = find_aspect_events(p1, p2, start, start + timedelta(days=1), aspects=[aspect], config=CONFIG)
        self.assertTrue(events, f"No {aspect} event for {p1}-{p2} on {day}")
        target = datetime.fromisoformat(f"{day}T{expected}").replace(tzinfo=IST)
        nearest = min(events, key=lambda event: abs((event.exact_time_local - target).total_seconds()))
        self.assertLessEqual(abs((nearest.exact_time_local - target).total_seconds()), 60)
        self.assertAlmostEqual(nearest.angular_separation_degrees, nearest.aspect_angle_degrees, places=5)
        self.assertEqual(nearest.timezone, "Asia/Kolkata")

    def test_june_conjunction_crosses_zero_wrap(self) -> None:
        self.event_near("2026-06-18", "Moon", "Venus", "Conjunction", "01:58:06")

    def test_may_square_matches_reference_calculation(self) -> None:
        self.event_near("2026-05-26", "Moon", "Venus", "Square", "12:38:24")

    def test_sun_saturn_exact_135_falls_after_trader_date(self) -> None:
        start = datetime(2026, 8, 20, tzinfo=IST)
        events = find_aspect_events(
            "Sun", "Saturn", start, start + timedelta(days=1), aspects=["Sesquiquadrate"], config=CONFIG
        )
        self.assertEqual(events, [])
        wider = find_aspect_events(
            "Sun", "Saturn", start, start + timedelta(days=4), aspects=["Sesquiquadrate"], config=CONFIG
        )
        self.assertTrue(wider)
        self.assertEqual(wider[0].exact_time_local.date().isoformat(), "2026-08-22")


if __name__ == "__main__":
    unittest.main()
