from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astro_market.timing import fit_timing_cycle


class TimingCandidateTests(unittest.TestCase):
    def test_session_open_interval_returns_comparable_grid_and_baseline(self) -> None:
        result = fit_timing_cycle(
            ["10:10", "11:20", "12:25", "13:25", "14:35"],
            method="session_open_interval",
            interval_minutes=65,
        )
        self.assertEqual([f"{minute // 60:02d}:{minute % 60:02d}" for minute in result.candidate_minutes],
                         ["09:15", "10:20", "11:25", "12:30", "13:35", "14:40"])
        self.assertAlmostEqual(result.mean_absolute_error_minutes, 7.0)
        self.assertGreater(result.random_phase_baseline_rmse_minutes, result.root_mean_square_error_minutes)
        self.assertEqual(len(result.comparisons), 5)

    def test_session_fraction_is_a_candidate_not_a_fixed_prediction(self) -> None:
        result = fit_timing_cycle(
            ["10:25", "11:25", "12:30", "13:35", "14:40"],
            method="session_fraction",
            subdivisions=6,
        )
        self.assertAlmostEqual(result.interval_minutes, 62.5)
        self.assertEqual(result.anchor_minutes, 555)
        self.assertTrue(result.candidate_minutes)

    def test_aspect_anchor_requires_an_exact_event_time(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact aspect event time"):
            fit_timing_cycle(["10:15"], method="aspect_time_interval")


if __name__ == "__main__":
    unittest.main()
