from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from starlette.datastructures import UploadFile

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from astro_market.api import import_market_csv  # noqa: E402
from astro_market.backtest import execute_backtest  # noqa: E402
from astro_market.db.sqlite import connect, initialize_database  # noqa: E402


class EventWindowBacktestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db = os.environ.get("ASTRO_DB_PATH")
        os.environ["ASTRO_DB_PATH"] = str(Path(self.temp_dir.name) / "test.sqlite3")
        initialize_database()

    def tearDown(self) -> None:
        if self.previous_db is None:
            os.environ.pop("ASTRO_DB_PATH", None)
        else:
            os.environ["ASTRO_DB_PATH"] = self.previous_db
        self.temp_dir.cleanup()

    def test_csv_import_and_prior_only_baseline(self) -> None:
        lines = ["Date,Time,Open,High,Low,Close,Volume"]
        for session_date, base_price in (("2026-06-17", 100.0), ("2026-06-18", 100.0)):
            for minute in range(10):
                time_value = f"09:{15 + minute:02d}"
                if session_date == "2026-06-18" and minute == 0:
                    values = (100, 100.3, 99.9, 100.1)
                elif session_date == "2026-06-18" and minute == 1:
                    values = (100.1, 100.8, 100.0, 100.6)
                elif session_date == "2026-06-18" and minute == 2:
                    values = (100.6, 100.7, 99.9, 99.95)
                else:
                    values = (base_price, base_price + 0.2, base_price - 0.2, base_price + 0.05)
                lines.append(f"{session_date},{time_value},{values[0]},{values[1]},{values[2]},{values[3]},1000")
        content = ("\n".join(lines) + "\n").encode()
        imported = import_market_csv(
            UploadFile(filename="nifty-sample.csv", file=BytesIO(content)),
            symbol="NIFTY",
            timeframe_minutes=1,
            timezone_name="Asia/Kolkata",
        )
        self.assertEqual(imported["row_count"], 20)

        with connect() as connection:
            calculation = connection.execute(
                """INSERT INTO calculation_runs
                   (config_id, range_start_utc, range_end_utc, status)
                   VALUES (1, '2025-12-31T18:30:00+00:00', '2026-12-31T18:30:00+00:00', 'completed')"""
            )
            event_id = connection.execute(
                """INSERT INTO planetary_events
                   (calculation_run_id, planet_1, planet_2, aspect_name, aspect_angle_degrees,
                    exact_time_utc, exact_time_local, timezone, longitude_1_degrees,
                    longitude_2_degrees, angular_separation_degrees)
                   VALUES (?, 'Moon', 'Venus', 'Square', 90,
                           '2026-06-18T03:45:00+00:00', '2026-06-18T09:15:00+05:30',
                           'Asia/Kolkata', 10, 100, 90)""",
                (calculation.lastrowid,),
            ).lastrowid
            instrument_id = connection.execute("SELECT id FROM market_instruments WHERE symbol='NIFTY'").fetchone()[0]
            cursor = connection.execute(
                """INSERT INTO backtest_runs
                   (name, instrument_id, timeframe_minutes, calculation_run_id,
                    parameters_json, baseline_description, prevents_lookahead)
                   VALUES ('test', ?, 1, ?, ?, 'prior-only windows', 1)""",
                (instrument_id, calculation.lastrowid, json.dumps({
                    "horizon_minutes": 10,
                    "reversal_threshold_percent": 0.5,
                    "sideways_threshold_percent": 1.0,
                })),
            )
            run_id = cursor.lastrowid

        execute_backtest(run_id, {"horizon_minutes": 10, "reversal_threshold_percent": 0.5, "sideways_threshold_percent": 1.0})
        with connect() as connection:
            run = connection.execute("SELECT status, prevents_lookahead FROM backtest_runs WHERE id=?", (run_id,)).fetchone()
            metric = connection.execute("SELECT * FROM event_market_metrics WHERE backtest_run_id=?", (run_id,)).fetchone()
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["prevents_lookahead"], 1)
        self.assertEqual(metric["planetary_event_id"], event_id)
        self.assertEqual(metric["reversal_observed"], 1)
        self.assertEqual(metric["time_to_reversal_seconds"], 120)
        self.assertEqual(metric["sideways_observed"], 1)
        self.assertIsNone(metric["directional_accuracy"])
        baseline = json.loads(metric["baseline_metric_json"])
        self.assertEqual(baseline["prior_windows"], 1)
        self.assertTrue(baseline["uses_only_prior_candles"])


if __name__ == "__main__":
    unittest.main()
