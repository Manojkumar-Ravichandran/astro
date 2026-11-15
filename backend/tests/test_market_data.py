from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astro_market.market_data import parse_ohlc_csv  # noqa: E402


class MarketCsvTests(unittest.TestCase):
    def test_separate_date_time_columns_localize_to_india_then_convert_utc(self) -> None:
        contents = (
            "Date,Time,Open,High,Low,Close,Volume\n"
            "2026-06-18,09:15,100,102,99,101,1200\n"
            "2026-06-18,09:16,101,103,100,102,1300\n"
        ).encode()
        result = parse_ohlc_csv(contents, "Asia/Kolkata")
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0]["timestamp_utc"], "2026-06-18T03:45:00+00:00")
        self.assertEqual(float(result.iloc[1]["close"]), 102.0)

    def test_invalid_ohlc_bounds_are_rejected(self) -> None:
        contents = b"timestamp,open,high,low,close\n2026-06-18T09:15:00,100,98,99,101\n"
        with self.assertRaisesRegex(ValueError, "bounds are invalid"):
            parse_ohlc_csv(contents, "Asia/Kolkata")

    def test_duplicate_timestamps_are_rejected(self) -> None:
        contents = (
            b"timestamp,open,high,low,close\n"
            b"2026-06-18T09:15:00,100,102,99,101\n"
            b"2026-06-18T09:15:00,101,103,100,102\n"
        )
        with self.assertRaisesRegex(ValueError, "duplicate candle timestamps"):
            parse_ohlc_csv(contents, "Asia/Kolkata")


if __name__ == "__main__":
    unittest.main()
