"""Testable intraday time-cycle candidates compared with published clock times."""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import fmean


@dataclass(frozen=True)
class TimingFit:
    interval_minutes: float
    anchor_minutes: float
    candidate_minutes: tuple[int, ...]
    comparisons: tuple[dict[str, object], ...]
    mean_absolute_error_minutes: float
    root_mean_square_error_minutes: float
    random_phase_baseline_rmse_minutes: float


def clock_to_minutes(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Clock time must be HH:MM: {value}")
    hour, minute = map(int, parts)
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError(f"Clock time is out of range: {value}")
    return hour * 60 + minute


def minutes_to_clock(value: float) -> str:
    minute = round(value) % (24 * 60)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _candidate_grid(anchor: float, interval: float, open_minute: int, close_minute: int) -> tuple[int, ...]:
    first_index = math.ceil((open_minute - anchor) / interval)
    last_index = math.floor((close_minute - anchor) / interval)
    return tuple(
        round(anchor + index * interval)
        for index in range(first_index, last_index + 1)
        if open_minute <= round(anchor + index * interval) <= close_minute
    )


def _scores(observed: tuple[int, ...], candidates: tuple[int, ...]) -> tuple[float, tuple[dict[str, object], ...]]:
    if not candidates:
        return float("inf"), tuple(
            {"published_time": minutes_to_clock(value), "candidate_time": None, "error_minutes": None}
            for value in observed
        )
    errors: list[float] = []
    details: list[dict[str, object]] = []
    for actual in observed:
        predicted = min(candidates, key=lambda candidate: abs(candidate - actual))
        error = predicted - actual
        errors.append(float(error))
        details.append(
            {
                "published_time": minutes_to_clock(actual),
                "candidate_time": minutes_to_clock(predicted),
                "error_minutes": error,
                "absolute_error_minutes": abs(error),
            }
        )
    return math.sqrt(fmean(error * error for error in errors)), tuple(details)


def fit_timing_cycle(
    published_times: list[str],
    *,
    method: str,
    interval_minutes: int = 65,
    anchor_minutes: float | None = None,
    minimum_interval_minutes: int = 50,
    maximum_interval_minutes: int = 90,
    subdivisions: int = 6,
    market_open: str = "09:15",
    market_close: str = "15:30",
) -> TimingFit:
    """Fit one candidate grid and compare it to supplied source clock times.

    The baseline averages RMSE over every whole-minute phase for the selected
    interval (or the best-fit interval). It is a timing comparison only, not a
    market-performance benchmark.
    """
    if not published_times:
        raise ValueError("No published times were supplied")
    opened, closed = clock_to_minutes(market_open), clock_to_minutes(market_close)
    if closed <= opened:
        raise ValueError("Market close must be after market open")
    observed = tuple(clock_to_minutes(value) for value in published_times)

    if method == "session_open_interval":
        interval = float(interval_minutes)
        anchor = float(opened)
    elif method == "aspect_time_interval":
        if anchor_minutes is None:
            raise ValueError("An exact aspect event time is required for this method")
        interval = float(interval_minutes)
        anchor = float(anchor_minutes)
    elif method == "session_fraction":
        if not 2 <= subdivisions <= 24:
            raise ValueError("subdivisions must be between 2 and 24")
        interval = (closed - opened) / float(subdivisions)
        anchor = float(opened)
    elif method == "best_fit_repeating_interval":
        if minimum_interval_minutes < 5 or maximum_interval_minutes > 360 or minimum_interval_minutes > maximum_interval_minutes:
            raise ValueError("Provide an ordered interval search range from 5 to 360 minutes")
        candidates_to_try: list[tuple[float, float, tuple[int, ...], float]] = []
        for candidate_interval in range(minimum_interval_minutes, maximum_interval_minutes + 1):
            for phase in range(candidate_interval):
                grid = _candidate_grid(float(phase), float(candidate_interval), opened, closed)
                rmse, _ = _scores(observed, grid)
                candidates_to_try.append((rmse, float(candidate_interval), grid, float(phase)))
        best_rmse, interval, grid, anchor = min(candidates_to_try, key=lambda item: item[0])
        comparisons: tuple[dict[str, object], ...]
        _, comparisons = _scores(observed, grid)
        baseline_values = []
        for phase in range(max(1, round(interval))):
            baseline_values.append(_scores(observed, _candidate_grid(float(phase), interval, opened, closed))[0])
        baseline_rmse = fmean(baseline_values)
        errors = [float(item["absolute_error_minutes"]) for item in comparisons]
        return TimingFit(
            interval_minutes=interval,
            anchor_minutes=anchor,
            candidate_minutes=grid,
            comparisons=comparisons,
            mean_absolute_error_minutes=fmean(errors),
            root_mean_square_error_minutes=best_rmse,
            random_phase_baseline_rmse_minutes=baseline_rmse,
        )
    else:
        raise ValueError(f"Unknown timing method: {method}")

    grid = _candidate_grid(anchor, interval, opened, closed)
    rmse, comparisons = _scores(observed, grid)
    baseline_values = []
    for phase in range(max(1, math.ceil(interval))):
        baseline_values.append(_scores(observed, _candidate_grid(float(phase), interval, opened, closed))[0])
    errors = [float(item["absolute_error_minutes"]) for item in comparisons if item["absolute_error_minutes"] is not None]
    return TimingFit(
        interval_minutes=interval,
        anchor_minutes=anchor,
        candidate_minutes=grid,
        comparisons=comparisons,
        mean_absolute_error_minutes=fmean(errors) if errors else float("inf"),
        root_mean_square_error_minutes=rmse,
        random_phase_baseline_rmse_minutes=fmean(baseline_values),
    )
