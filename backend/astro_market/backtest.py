"""Descriptive event-window analysis over imported OHLC candles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import numpy as np
import pandas as pd

from .db.sqlite import connect


NANOSECONDS_PER_MINUTE = 60 * 1_000_000_000


def _window_summary(frame: pd.DataFrame, anchor_price: float) -> dict[str, float | int | None]:
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    up = (float(np.max(highs)) / anchor_price) - 1.0
    down = (float(np.min(lows)) / anchor_price) - 1.0
    price_range = (float(np.max(highs)) - float(np.min(lows))) / anchor_price
    returns = np.diff(np.log(closes))
    volatility = float(np.std(returns, ddof=1)) if returns.size > 1 else None
    return {
        "max_upward_move": up,
        "max_downward_move": down,
        "price_range": price_range,
        "volatility": volatility,
        "candle_count": int(len(frame)),
    }


def _reversal_observation(frame: pd.DataFrame, anchor_price: float, threshold_percent: float, event_ns: int) -> tuple[int, int | None]:
    threshold = threshold_percent / 100.0
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    times = frame["timestamp_ns"].to_numpy(dtype=np.int64)
    up_hits = np.flatnonzero(highs >= anchor_price * (1.0 + threshold))
    down_hits = np.flatnonzero(lows <= anchor_price * (1.0 - threshold))
    first_up = int(up_hits[0]) if up_hits.size else None
    first_down = int(down_hits[0]) if down_hits.size else None
    if first_up is None and first_down is None:
        return 0, None
    if first_down is None or (first_up is not None and first_up <= first_down):
        impulse_index = first_up
        crossed_back = np.flatnonzero(closes[impulse_index + 1 :] <= anchor_price)
    else:
        impulse_index = first_down
        crossed_back = np.flatnonzero(closes[impulse_index + 1 :] >= anchor_price)
    if crossed_back.size == 0:
        return 0, None
    reversal_index = impulse_index + 1 + int(crossed_back[0])
    return 1, max(0, int((times[reversal_index] - event_ns) // 1_000_000_000))


def _summary_for_window(
    all_times: np.ndarray,
    all_candles: pd.DataFrame,
    start_ns: int,
    horizon_ns: int,
) -> tuple[pd.DataFrame, dict[str, float | int | None] | None]:
    left = int(np.searchsorted(all_times, start_ns, side="left"))
    right = int(np.searchsorted(all_times, start_ns + horizon_ns, side="right"))
    if right <= left:
        return all_candles.iloc[0:0], None
    frame = all_candles.iloc[left:right]
    anchor = float(frame.iloc[0]["close"])
    return frame, _window_summary(frame, anchor)


def execute_backtest(run_id: int, request: dict[str, object]) -> None:
    """Store event outcomes and a prior-session baseline without future inputs.

    Post-event candles are used only as outcome measurements. Baseline windows
    are drawn only from earlier dates at the same clock time. No direction
    accuracy is computed because the supplied source records contain no explicit
    directional calls.
    """
    try:
        with connect() as connection:
            run = connection.execute("SELECT * FROM backtest_runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                return
            event_where = ["event.calculation_run_id=?"]
            event_params: list[object] = [run["calculation_run_id"]]
            if params := json.loads(run["parameters_json"]):
                if params.get("planet"):
                    event_where.append("(event.planet_1=? OR event.planet_2=?)")
                    event_params.extend((params["planet"], params["planet"]))
                if params.get("aspect"):
                    event_where.append("event.aspect_name=?")
                    event_params.append(params["aspect"])
            events = connection.execute(
                """SELECT event.id, event.exact_time_utc, event.planet_1, event.planet_2,
                          event.aspect_name, event.aspect_angle_degrees,
                          (SELECT source.id FROM published_events source
                           WHERE source.event_date=substr(event.exact_time_local,1,10)
                             AND source.planet_1=event.planet_1 AND source.planet_2=event.planet_2
                             AND source.source_angle_degrees=event.aspect_angle_degrees
                           ORDER BY source.id LIMIT 1) AS published_event_id
                   FROM planetary_events event WHERE """ + " AND ".join(event_where) + " ORDER BY event.exact_time_utc",
                event_params,
            ).fetchall()
            candle_rows = connection.execute(
                """SELECT timestamp_utc, open, high, low, close, volume
                   FROM market_candles WHERE instrument_id=? AND timeframe_minutes=?
                   ORDER BY timestamp_utc""",
                (run["instrument_id"], run["timeframe_minutes"]),
            ).fetchall()

        if not candle_rows:
            raise ValueError("No market candles are available for this instrument and timeframe")
        candles = pd.DataFrame([dict(row) for row in candle_rows])
        candles["timestamp"] = pd.to_datetime(candles["timestamp_utc"], utc=True)
        candles["timestamp_ns"] = candles["timestamp"].astype("int64")
        times = candles["timestamp_ns"].to_numpy(dtype=np.int64)
        params = json.loads(run["parameters_json"])
        horizon_minutes = int(params["horizon_minutes"])
        horizon_ns = horizon_minutes * NANOSECONDS_PER_MINUTE
        reversal_threshold = params.get("reversal_threshold_percent")
        sideways_threshold = params.get("sideways_threshold_percent")
        records = []

        for event in events:
            event_ns = int(pd.Timestamp(event["exact_time_utc"]).value)
            window_start = pd.Timestamp(event["exact_time_utc"])
            frame, observed = _summary_for_window(times, candles, event_ns, horizon_ns)
            window_end = window_start + pd.Timedelta(minutes=horizon_minutes)
            reversal_observed = None
            time_to_reversal = None
            sideways_observed = None
            baseline_values: list[dict[str, float | int | None]] = []
            observed_details: dict[str, object] = {
                "data_available": observed is not None,
                "horizon_minutes": horizon_minutes,
                "outcome_only": True,
            }
            if observed is not None:
                anchor_price = float(frame.iloc[0]["close"])
                observed_details.update(observed)
                if reversal_threshold is not None:
                    reversal_observed, time_to_reversal = _reversal_observation(
                        frame, anchor_price, float(reversal_threshold), event_ns
                    )
                if sideways_threshold is not None:
                    sideways_observed = int(observed["price_range"] is not None and observed["price_range"] * 100 <= float(sideways_threshold))

                # Same clock slot on prior calendar sessions only; no later candles
                # enter the comparison baseline.
                for prior_day in range(1, 15):
                    prior_start = event_ns - prior_day * 24 * 60 * NANOSECONDS_PER_MINUTE
                    _prior_frame, prior_summary = _summary_for_window(times, candles, prior_start, horizon_ns)
                    if prior_summary is not None:
                        baseline_values.append(prior_summary)
                    if len(baseline_values) >= 5:
                        break
            baseline = {
                "method": "mean of up to five prior available same-clock windows",
                "prior_windows": len(baseline_values),
                "uses_only_prior_candles": True,
            }
            for metric in ("max_upward_move", "max_downward_move", "price_range", "volatility"):
                values = [float(value[metric]) for value in baseline_values if value.get(metric) is not None]
                baseline[f"mean_{metric}"] = float(np.mean(values)) if values else None

            records.append(
                (
                    run_id,
                    event["id"],
                    event["published_event_id"],
                    window_start.isoformat(),
                    window_end.isoformat(),
                    observed["max_upward_move"] if observed else None,
                    observed["max_downward_move"] if observed else None,
                    observed["price_range"] if observed else None,
                    observed["volatility"] if observed else None,
                    reversal_observed,
                    time_to_reversal,
                    sideways_observed,
                    None,
                    json.dumps(baseline, sort_keys=True),
                    json.dumps(observed_details, sort_keys=True),
                )
            )

        with connect() as connection:
            connection.executemany(
                """INSERT INTO event_market_metrics
                   (backtest_run_id, planetary_event_id, published_event_id,
                    window_start_utc, window_end_utc, max_upward_move,
                    max_downward_move, price_range, volatility, reversal_observed,
                    time_to_reversal_seconds, sideways_observed, directional_accuracy,
                    baseline_metric_json, observed_metric_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                records,
            )
            connection.execute(
                "UPDATE backtest_runs SET status='completed', completed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (run_id,),
            )
    except Exception as exc:
        with connect() as connection:
            connection.execute(
                "UPDATE backtest_runs SET status='failed', completed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (run_id,),
            )
            connection.execute("UPDATE backtest_runs SET parameters_json=json_set(parameters_json,'$.error_message',?) WHERE id=?", (str(exc)[:2000], run_id))
