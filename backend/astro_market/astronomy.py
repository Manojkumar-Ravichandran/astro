"""Swiss Ephemeris positions and exact aspect event searches.

All computation uses Julian Day UT internally. Input and returned datetimes are
timezone-aware. The default convention is geocentric tropical apparent
ecliptic longitude, with Swiss Ephemeris flags requested explicitly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
import threading
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import swisseph as swe
from scipy.optimize import brentq


class Zodiac(str, Enum):
    TROPICAL = "tropical"
    SIDEREAL = "sidereal"


class Planet(str, Enum):
    SUN = "Sun"
    MOON = "Moon"
    MERCURY = "Mercury"
    VENUS = "Venus"
    MARS = "Mars"
    JUPITER = "Jupiter"
    SATURN = "Saturn"


PLANET_IDS: dict[Planet, int] = {
    Planet.SUN: swe.SUN,
    Planet.MOON: swe.MOON,
    Planet.MERCURY: swe.MERCURY,
    Planet.VENUS: swe.VENUS,
    Planet.MARS: swe.MARS,
    Planet.JUPITER: swe.JUPITER,
    Planet.SATURN: swe.SATURN,
}


ASPECTS: dict[str, float] = {
    "Conjunction": 0.0,
    "Semi-square": 45.0,
    "Sextile": 60.0,
    "Square": 90.0,
    "Trine": 120.0,
    "Sesquiquadrate": 135.0,
    "Opposition": 180.0,
}


@dataclass(frozen=True)
class CalculationConfig:
    zodiac: Zodiac = Zodiac.TROPICAL
    timezone: str = "Asia/Kolkata"
    sidereal_mode: int | None = None
    ephemeris_path: str | None = None
    require_swiss_files: bool = True
    flags: int = swe.FLG_SWIEPH | swe.FLG_SPEED

    def __post_init__(self) -> None:
        object.__setattr__(self, "zodiac", Zodiac(self.zodiac))
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {self.timezone}") from exc
        if self.zodiac is Zodiac.SIDEREAL and self.sidereal_mode is None:
            raise ValueError("sidereal_mode is required for sidereal calculations")


@dataclass(frozen=True)
class Position:
    planet: Planet
    longitude_degrees: float
    latitude_degrees: float
    distance_au: float
    longitude_speed_degrees_per_day: float
    returned_flags: int
    warning: str | None = None


@dataclass(frozen=True)
class AspectEvent:
    planet_1: Planet
    planet_2: Planet
    aspect_name: str
    aspect_angle_degrees: float
    exact_time_utc: datetime
    exact_time_local: datetime
    timezone: str
    longitude_1_degrees: float
    longitude_2_degrees: float
    angular_separation_degrees: float
    orb_before_degrees: float
    orb_after_degrees: float
    calculation_settings: dict[str, object]


_SWISS_LOCK = threading.RLock()
_JULIAN_UNIX_EPOCH = 2440587.5
_SECONDS_PER_DAY = 86400.0


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Datetime must include a timezone")
    return value.astimezone(timezone.utc)


def datetime_to_jd(value: datetime) -> float:
    utc_value = _aware_utc(value)
    return _JULIAN_UNIX_EPOCH + utc_value.timestamp() / _SECONDS_PER_DAY


def jd_to_datetime(jd_ut: float) -> datetime:
    return datetime.fromtimestamp((jd_ut - _JULIAN_UNIX_EPOCH) * _SECONDS_PER_DAY, timezone.utc)


def _configure(config: CalculationConfig) -> None:
    if config.ephemeris_path:
        swe.set_ephe_path(config.ephemeris_path)
    if config.zodiac is Zodiac.SIDEREAL:
        assert config.sidereal_mode is not None
        swe.set_sid_mode(config.sidereal_mode)


def _flags_for(config: CalculationConfig) -> int:
    flags = config.flags
    if config.zodiac is Zodiac.SIDEREAL:
        flags |= swe.FLG_SIDEREAL
    else:
        flags &= ~swe.FLG_SIDEREAL
    return flags


def _position_at_jd(planet: Planet, jd_ut: float, config: CalculationConfig) -> Position:
    with _SWISS_LOCK:
        _configure(config)
        result = swe.calc_ut(jd_ut, PLANET_IDS[planet], _flags_for(config))
    values, returned_flags = result[0], result[1]
    warning = result[2] if len(result) > 2 else None
    if warning and "using Moshier eph." not in warning:
        raise RuntimeError(f"Swiss Ephemeris calculation warning for {planet.value}: {warning.strip()}")
    if config.require_swiss_files and returned_flags & swe.FLG_MOSEPH:
        raise RuntimeError(
            "Swiss Ephemeris files were not used (Swiss Ephemeris fell back to Moshier). "
            "Configure an ephemeris path containing the required Swiss files."
        )
    return Position(
        planet=planet,
        longitude_degrees=float(values[0] % 360.0),
        latitude_degrees=float(values[1]),
        distance_au=float(values[2]),
        longitude_speed_degrees_per_day=float(values[3]),
        returned_flags=int(returned_flags),
        warning=warning.strip() if warning else None,
    )


def calculate_position(planet: Planet | str, instant: datetime, config: CalculationConfig | None = None) -> Position:
    """Calculate geocentric apparent ecliptic position at an aware instant."""
    planet_value = Planet(planet)
    selected_config = config or CalculationConfig()
    return _position_at_jd(planet_value, datetime_to_jd(instant), selected_config)


def angular_separation(longitude_1: float, longitude_2: float) -> float:
    """Return the minor angular separation in [0, 180] degrees."""
    return abs((longitude_2 - longitude_1 + 180.0) % 360.0 - 180.0)


def signed_angle_difference(angle: float, reference: float) -> float:
    """Smallest signed difference from reference to angle, in [-180, 180)."""
    return (angle - reference + 180.0) % 360.0 - 180.0


def _directed_targets(aspect_angle: float) -> tuple[float, ...]:
    first = aspect_angle % 360.0
    second = (-aspect_angle) % 360.0
    return (first,) if math.isclose(first, second, abs_tol=1e-10) else (first, second)


def _relative_longitude(p1: Planet, p2: Planet, jd_ut: float, config: CalculationConfig) -> float:
    lon1 = _position_at_jd(p1, jd_ut, config).longitude_degrees
    lon2 = _position_at_jd(p2, jd_ut, config).longitude_degrees
    return (lon2 - lon1) % 360.0


def find_aspect_events(
    planet_1: Planet | str,
    planet_2: Planet | str,
    start: datetime,
    end: datetime,
    *,
    aspects: Iterable[str] | None = None,
    config: CalculationConfig | None = None,
    scan_step: timedelta = timedelta(hours=3),
    tolerance_seconds: float = 0.05,
) -> list[AspectEvent]:
    """Find exact aspect formations in [start, end] using bracketed root solving.

    Samples only identify brackets. Each timestamp is refined with Brent's
    method against Swiss Ephemeris longitudes. Directed phase is unwrapped over
    each short bracket, so 0/360-degree wrap does not hide conjunctions.
    """
    p1, p2 = Planet(planet_1), Planet(planet_2)
    start_utc, end_utc = _aware_utc(start), _aware_utc(end)
    if end_utc <= start_utc:
        raise ValueError("end must be after start")
    if scan_step.total_seconds() <= 0:
        raise ValueError("scan_step must be positive")
    if tolerance_seconds <= 0:
        raise ValueError("tolerance_seconds must be positive")
    selected_config = config or CalculationConfig()
    aspect_names = list(aspects) if aspects is not None else list(ASPECTS)
    for name in aspect_names:
        if name not in ASPECTS:
            raise ValueError(f"Unsupported aspect: {name}")

    start_jd, end_jd = datetime_to_jd(start_utc), datetime_to_jd(end_utc)
    step_days = scan_step.total_seconds() / _SECONDS_PER_DAY
    sample_jds = [start_jd]
    while sample_jds[-1] + step_days < end_jd:
        sample_jds.append(sample_jds[-1] + step_days)
    if sample_jds[-1] < end_jd:
        sample_jds.append(end_jd)

    raw_samples = [_relative_longitude(p1, p2, jd, selected_config) for jd in sample_jds]
    unwrapped = [raw_samples[0]]
    for previous, current in zip(raw_samples, raw_samples[1:]):
        unwrapped.append(unwrapped[-1] + signed_angle_difference(current, previous))

    roots: list[tuple[float, str, float]] = []
    for aspect_name in aspect_names:
        angle = ASPECTS[aspect_name]
        for target_phase in _directed_targets(angle):
            for index, (left, right) in enumerate(zip(unwrapped, unwrapped[1:])):
                low, high = sorted((left, right))
                first_k = math.ceil((low - target_phase) / 360.0)
                last_k = math.floor((high - target_phase) / 360.0)
                for cycle in range(first_k, last_k + 1):
                    target = target_phase + 360.0 * cycle
                    if math.isclose(target, left, abs_tol=1e-12):
                        root = sample_jds[index]
                    elif math.isclose(target, right, abs_tol=1e-12):
                        root = sample_jds[index + 1]
                    elif not (low < target < high):
                        continue
                    else:
                        left_jd = sample_jds[index]
                        left_raw = raw_samples[index]
                        left_unwrapped = left

                        def residual(jd: float) -> float:
                            raw = _relative_longitude(p1, p2, jd, selected_config)
                            continuous = left_unwrapped + signed_angle_difference(raw, left_raw)
                            return continuous - target

                        root = brentq(
                            residual,
                            sample_jds[index],
                            sample_jds[index + 1],
                            xtol=max(1e-12, tolerance_seconds / _SECONDS_PER_DAY),
                            rtol=4 * math.ulp(1.0),
                        )
                    if start_jd - 1e-12 <= root <= end_jd + 1e-12:
                        roots.append((root, aspect_name, angle))

    roots.sort(key=lambda item: item[0])
    unique: list[tuple[float, str, float]] = []
    dedupe_days = max(tolerance_seconds, 0.1) / _SECONDS_PER_DAY
    for item in roots:
        if unique and item[1:] == unique[-1][1:] and abs(item[0] - unique[-1][0]) <= dedupe_days:
            continue
        unique.append(item)

    tz = ZoneInfo(selected_config.timezone)
    results: list[AspectEvent] = []
    for root_jd, aspect_name, angle in unique:
        instant_utc = jd_to_datetime(root_jd)
        pos1 = _position_at_jd(p1, root_jd, selected_config)
        pos2 = _position_at_jd(p2, root_jd, selected_config)
        orb_window_days = 15.0 / 1440.0
        before_separation = angular_separation(
            _position_at_jd(p1, root_jd - orb_window_days, selected_config).longitude_degrees,
            _position_at_jd(p2, root_jd - orb_window_days, selected_config).longitude_degrees,
        )
        after_separation = angular_separation(
            _position_at_jd(p1, root_jd + orb_window_days, selected_config).longitude_degrees,
            _position_at_jd(p2, root_jd + orb_window_days, selected_config).longitude_degrees,
        )
        results.append(
            AspectEvent(
                planet_1=p1,
                planet_2=p2,
                aspect_name=aspect_name,
                aspect_angle_degrees=angle,
                exact_time_utc=instant_utc,
                exact_time_local=instant_utc.astimezone(tz),
                timezone=selected_config.timezone,
                longitude_1_degrees=pos1.longitude_degrees,
                longitude_2_degrees=pos2.longitude_degrees,
                angular_separation_degrees=angular_separation(pos1.longitude_degrees, pos2.longitude_degrees),
                orb_before_degrees=abs(before_separation - angle),
                orb_after_degrees=abs(after_separation - angle),
                calculation_settings={
                    **asdict(selected_config),
                    "zodiac": selected_config.zodiac.value,
                    "flags_requested": _flags_for(selected_config),
                    "flags_returned_planet_1": pos1.returned_flags,
                    "flags_returned_planet_2": pos2.returned_flags,
                    "warnings": [warning for warning in (pos1.warning, pos2.warning) if warning],
                    "ephemeris_version": getattr(swe, "version", "unknown"),
                    "root_tolerance_seconds": tolerance_seconds,
                    "scan_step_seconds": scan_step.total_seconds(),
                    "orb_window_minutes": 15,
                },
            )
        )
    return results
