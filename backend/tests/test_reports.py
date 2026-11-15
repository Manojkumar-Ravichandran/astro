from __future__ import annotations

import unittest
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from astro_market.reports import annual_calendar_pdf  # noqa: E402


class AnnualReportTests(unittest.TestCase):
    def test_pdf_contains_all_months_and_event_text(self) -> None:
        data = annual_calendar_pdf(2026, [{
            "exact_time_local": "2026-06-18T01:58:06+05:30",
            "planet_1": "Moon", "planet_2": "Venus", "aspect_name": "Conjunction",
        }], "Asia/Kolkata")
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertIn(b"/Count 12", data)
        self.assertIn(b"Moon-Venus Conjunction", data)
        self.assertIn(b"June 2026", data)
        self.assertTrue(data.endswith(b"%%EOF\n"))


if __name__ == "__main__":
    unittest.main()
