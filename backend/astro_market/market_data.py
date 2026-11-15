"""CSV parsing and validation for local one- and five-minute OHLC imports."""

from __future__ import annotations

from io import BytesIO
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd


MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def _normalized(name: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).strip().lower())


def _find_column(columns: list[object], choices: set[str]) -> object | None:
    for column in columns:
        if _normalized(column) in choices:
            return column
    return None


def parse_ohlc_csv(contents: bytes, timezone_name: str) -> pd.DataFrame:
    if not contents:
        raise ValueError("The uploaded CSV is empty")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise ValueError("CSV files must be 100 MB or smaller")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc
    try:
        frame = pd.read_csv(BytesIO(contents))
    except Exception as exc:
        raise ValueError(f"Could not read CSV: {exc}") from exc
    if frame.empty:
        raise ValueError("The CSV contains no candle rows")

    columns = list(frame.columns)
    timestamp_column = _find_column(columns, {"timestamp", "datetime", "date_time", "datetimeist", "datetimeutc"})
    date_column = _find_column(columns, {"date", "tradedate", "sessiondate"})
    time_column = _find_column(columns, {"time", "tradetime", "bartime"})
    if timestamp_column is None and date_column is not None and time_column is not None and date_column != time_column:
        timestamp_values = frame[date_column].astype(str).str.strip() + " " + frame[time_column].astype(str).str.strip()
    elif timestamp_column is not None:
        timestamp_values = frame[timestamp_column]
    elif time_column is not None:
        timestamp_values = frame[time_column]
    else:
        raise ValueError("CSV needs a timestamp/datetime column or separate Date and Time columns")

    canonical_columns = {
        "open": _find_column(columns, {"open", "o"}),
        "high": _find_column(columns, {"high", "h"}),
        "low": _find_column(columns, {"low", "l"}),
        "close": _find_column(columns, {"close", "c", "ltp"}),
        "volume": _find_column(columns, {"volume", "vol", "qty", "quantity"}),
    }
    missing = [name for name in ("open", "high", "low", "close") if canonical_columns[name] is None]
    if missing:
        raise ValueError(f"CSV is missing required OHLC columns: {', '.join(missing)}")

    parsed_times = []
    invalid_timestamps = []
    for row_number, raw in enumerate(timestamp_values, start=2):
        try:
            stamp = pd.Timestamp(raw)
            if pd.isna(stamp):
                raise ValueError
            if stamp.tzinfo is None:
                stamp = stamp.tz_localize(zone)
            parsed_times.append(stamp.tz_convert("UTC"))
        except Exception:
            invalid_timestamps.append(row_number)
            parsed_times.append(pd.NaT)
    if invalid_timestamps:
        raise ValueError(f"Invalid timestamps at CSV row(s): {', '.join(map(str, invalid_timestamps[:8]))}")

    result = pd.DataFrame({"timestamp_utc": parsed_times})
    for name in ("open", "high", "low", "close"):
        source = canonical_columns[name]
        result[name] = pd.to_numeric(frame[source], errors="coerce")
    volume_source = canonical_columns["volume"]
    result["volume"] = pd.to_numeric(frame[volume_source], errors="coerce") if volume_source is not None else pd.NA

    ohlc = result[["open", "high", "low", "close"]].to_numpy(dtype=float)
    invalid_prices = result[["open", "high", "low", "close"]].isna().any(axis=1) | ~np.isfinite(ohlc).all(axis=1) | (result[["open", "high", "low", "close"]] <= 0).any(axis=1)
    if invalid_prices.any():
        bad_rows = (invalid_prices[invalid_prices].index + 2).tolist()
        raise ValueError(f"Invalid or non-positive OHLC values at CSV row(s): {', '.join(map(str, bad_rows[:8]))}")
    invalid_shape = (
        (result["high"] < result["low"])
        | (result["high"] < result["open"])
        | (result["high"] < result["close"])
        | (result["low"] > result["open"])
        | (result["low"] > result["close"])
    )
    if invalid_shape.any():
        bad_rows = (invalid_shape[invalid_shape].index + 2).tolist()
        raise ValueError(f"OHLC high/low bounds are invalid at CSV row(s): {', '.join(map(str, bad_rows[:8]))}")
    finite_volume = result["volume"].dropna().to_numpy(dtype=float)
    if finite_volume.size and not np.isfinite(finite_volume).all():
        raise ValueError("Volume values must be finite numbers")
    if result["timestamp_utc"].duplicated().any():
        duplicates = result.loc[result["timestamp_utc"].duplicated(keep=False), "timestamp_utc"].dt.strftime("%Y-%m-%d %H:%M:%S").unique().tolist()
        raise ValueError(f"CSV contains duplicate candle timestamps: {', '.join(duplicates[:8])}")

    result.sort_values("timestamp_utc", inplace=True)
    result["timestamp_utc"] = result["timestamp_utc"].map(lambda stamp: stamp.isoformat())
    return result.reset_index(drop=True)
