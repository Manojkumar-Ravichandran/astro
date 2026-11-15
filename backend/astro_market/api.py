"""Local FastAPI endpoints for yearly calculations and calendar summaries."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from .astronomy import ASPECTS, CalculationConfig, Planet, find_aspect_events
from .db.sqlite import BACKEND_ROOT, connect, initialize_database
from .timing import fit_timing_cycle, minutes_to_clock
from .market_data import MAX_UPLOAD_BYTES, parse_ohlc_csv
from .backtest import execute_backtest
from .reports import annual_calendar_pdf, research_detail_pdf


PLANETARY_PAIRS: tuple[tuple[Planet, Planet], ...] = (
    (Planet.SUN, Planet.MOON),
    (Planet.MOON, Planet.MERCURY),
    (Planet.MOON, Planet.VENUS),
    (Planet.MOON, Planet.MARS),
    (Planet.MOON, Planet.JUPITER),
    (Planet.MOON, Planet.SATURN),
    (Planet.SUN, Planet.MERCURY),
    (Planet.SUN, Planet.VENUS),
    (Planet.SUN, Planet.MARS),
    (Planet.SUN, Planet.JUPITER),
    (Planet.SUN, Planet.SATURN),
    (Planet.VENUS, Planet.MARS),
    (Planet.VENUS, Planet.JUPITER),
    (Planet.VENUS, Planet.SATURN),
    (Planet.MARS, Planet.JUPITER),
    (Planet.MARS, Planet.SATURN),
    (Planet.JUPITER, Planet.SATURN),
)

_JOB_LOCK = threading.Lock()


class CalculationRequest(BaseModel):
    year: int = Field(ge=1800, le=2399)


class RangeCalculationRequest(BaseModel):
    start_date: date
    end_date: date
    pairs: list[tuple[Planet, Planet]] = Field(min_length=1, max_length=17)
    aspects: list[str] = Field(default_factory=lambda: list(ASPECTS), min_length=1, max_length=7)
    timezone: str = "Asia/Kolkata"

    @model_validator(mode="after")
    def validate_range(self) -> "RangeCalculationRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.start_date.year < 1800 or self.end_date.year > 2399:
            raise ValueError("Swiss ephemeris files currently support years 1800 through 2399")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("A custom calculation can cover at most 367 calendar days")
        if any(name not in ASPECTS for name in self.aspects):
            raise ValueError("Unknown aspect name")
        if any(p1 == p2 for p1, p2 in self.pairs):
            raise ValueError("A planetary pair must contain two different planets")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {self.timezone}") from exc
        return self


class TimingAnalysisRequest(BaseModel):
    published_event_id: int = Field(gt=0)
    method: Literal[
        "session_open_interval",
        "aspect_time_interval",
        "session_fraction",
        "best_fit_repeating_interval",
    ]
    interval_minutes: int = Field(default=65, ge=5, le=360)
    minimum_interval_minutes: int = Field(default=50, ge=5, le=360)
    maximum_interval_minutes: int = Field(default=90, ge=5, le=360)
    subdivisions: int = Field(default=6, ge=2, le=24)
    market_open: str = "09:15"
    market_close: str = "15:30"
    timezone: str = "Asia/Kolkata"


class BacktestRequest(BaseModel):
    symbol: Literal["NIFTY", "BANKNIFTY"]
    timeframe_minutes: Literal[1, 5]
    year: int = Field(ge=1800, le=2399)
    horizon_minutes: int = Field(default=60, ge=1, le=240)
    reversal_threshold_percent: float | None = Field(default=None, gt=0, le=50)
    sideways_threshold_percent: float | None = Field(default=None, gt=0, le=50)
    planet: str | None = None
    aspect: str | None = None


class RuleAspectInput(BaseModel):
    planet_1: Planet
    planet_2: Planet
    aspect_angle_degrees: float

    @model_validator(mode="after")
    def validate_pair_aspect(self) -> "RuleAspectInput":
        if self.planet_1 == self.planet_2:
            raise ValueError("A rule aspect needs two different planets")
        if self.aspect_angle_degrees not in ASPECTS.values():
            raise ValueError("Aspect angle must be one of the seven supported standard aspects")
        return self


class RuleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    hypothesis_text: str = Field(min_length=1, max_length=5000)
    status: Literal["hypothesis", "under_test", "supported", "not_supported", "retired"] = "hypothesis"
    source_document_id: int | None = None
    aspects: list[RuleAspectInput] = Field(min_length=1, max_length=17)


class RulePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    hypothesis_text: str | None = Field(default=None, min_length=1, max_length=5000)
    status: Literal["hypothesis", "under_test", "supported", "not_supported", "retired"] | None = None
    source_document_id: int | None = None
    aspects: list[RuleAspectInput] | None = Field(default=None, min_length=1, max_length=17)


class RunResponse(BaseModel):
    id: int
    year: int
    status: str
    started_at: str
    completed_at: str | None = None
    event_count: int = 0
    error_message: str | None = None


class EventResponse(BaseModel):
    id: int
    planet_1: str
    planet_2: str
    aspect_name: str
    aspect_angle_degrees: float
    exact_time_utc: str
    exact_time_local: str
    timezone: str
    longitude_1_degrees: float
    longitude_2_degrees: float
    angular_separation_degrees: float
    orb_before_degrees: float | None = None
    orb_after_degrees: float | None = None
    orb_window_minutes: int = 15
    calculation_settings: dict[str, object] = Field(default_factory=dict)


def _range_for_year(year: int, tz_name: str = "Asia/Kolkata") -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    local_start = datetime.combine(date(year, 1, 1), time.min, tzinfo=tz)
    local_end = datetime.combine(date(year + 1, 1, 1), time.min, tzinfo=tz)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _run_to_response(row, count: int = 0) -> RunResponse:
    year = datetime.fromisoformat(row["range_start_utc"]).astimezone(ZoneInfo("Asia/Kolkata")).year
    return RunResponse(
        id=row["id"],
        year=year,
        status=row["status"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        event_count=count,
        error_message=row["error_message"],
    )


def calculate_interval(
    run_id: int,
    start_local: datetime,
    end_local: datetime,
    pairs: tuple[tuple[Planet, Planet], ...] | list[tuple[Planet, Planet]],
    aspects: tuple[str, ...] | list[str],
    timezone_name: str,
) -> None:
    """Background worker that stores exact events for the requested interval."""
    ephe_dir = Path(os.environ.get("ASTRO_EPHE_PATH", BACKEND_ROOT / "ephe")).expanduser().resolve()
    config = CalculationConfig(ephemeris_path=str(ephe_dir), timezone=timezone_name)
    event_count = 0
    try:
        for p1, p2 in pairs:
            events = find_aspect_events(
                p1,
                p2,
                start_local,
                end_local,
                aspects=aspects,
                config=config,
            )
            if not events:
                continue
            with connect() as connection:
                connection.executemany(
                    """INSERT INTO planetary_events
                       (calculation_run_id, planet_1, planet_2, aspect_name,
                        aspect_angle_degrees, exact_time_utc, exact_time_local,
                        timezone, longitude_1_degrees, longitude_2_degrees,
                        angular_separation_degrees, event_metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            run_id,
                            event.planet_1.value,
                            event.planet_2.value,
                            event.aspect_name,
                            event.aspect_angle_degrees,
                            event.exact_time_utc.isoformat(),
                            event.exact_time_local.isoformat(),
                            event.timezone,
                            event.longitude_1_degrees,
                            event.longitude_2_degrees,
                            event.angular_separation_degrees,
                            json.dumps(
                                {
                                    "calculation_settings": event.calculation_settings,
                                    "orb_before_degrees": event.orb_before_degrees,
                                    "orb_after_degrees": event.orb_after_degrees,
                                    "orb_window_minutes": 15,
                                },
                                sort_keys=True,
                            ),
                        )
                        for event in events
                    ],
                )
            event_count += len(events)
        with connect() as connection:
            connection.execute(
                "UPDATE calculation_runs SET status='completed', completed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (run_id,),
            )
    except Exception as exc:
        with connect() as connection:
            connection.execute(
                "UPDATE calculation_runs SET status='failed', error_message=?, completed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (str(exc)[:2000], run_id),
            )


def calculate_run(run_id: int, year: int) -> None:
    """Calculate all configured pairs and standard aspects for a calendar year."""
    tz = ZoneInfo("Asia/Kolkata")
    calculate_interval(
        run_id,
        datetime(year, 1, 1, tzinfo=tz),
        datetime(year + 1, 1, 1, tzinfo=tz),
        PLANETARY_PAIRS,
        list(ASPECTS),
        "Asia/Kolkata",
    )


app = FastAPI(title="Astro Market Analyzer API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/calculations", response_model=RunResponse, status_code=202)
def start_calculation(request: CalculationRequest, background_tasks: BackgroundTasks) -> RunResponse:
    start_utc, end_utc = _range_for_year(request.year)
    with _JOB_LOCK, connect() as connection:
        running = connection.execute(
            "SELECT * FROM calculation_runs WHERE status='running' AND range_start_utc=? AND range_end_utc=? ORDER BY id DESC LIMIT 1",
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchone()
        if running:
            return _run_to_response(running)
        cursor = connection.execute(
            """INSERT INTO calculation_runs
               (config_id, range_start_utc, range_end_utc, status, software_version)
               VALUES (1, ?, ?, 'running', '0.1.0')""",
            (start_utc.isoformat(), end_utc.isoformat()),
        )
        row = connection.execute("SELECT * FROM calculation_runs WHERE id=?", (cursor.lastrowid,)).fetchone()
    background_tasks.add_task(calculate_run, row["id"], request.year)
    return _run_to_response(row)


@app.post("/api/calculations/range", response_model=RunResponse, status_code=202)
def start_range_calculation(request: RangeCalculationRequest, background_tasks: BackgroundTasks) -> RunResponse:
    tz = ZoneInfo(request.timezone)
    start_local = datetime.combine(request.start_date, time.min, tzinfo=tz)
    end_local = datetime.combine(request.end_date + timedelta(days=1), time.min, tzinfo=tz)
    start_utc, end_utc = start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
    with connect() as connection:
        cursor = connection.execute(
            """INSERT INTO calculation_runs
               (config_id, range_start_utc, range_end_utc, status, software_version)
               VALUES (1, ?, ?, 'running', '0.1.0')""",
            (start_utc.isoformat(), end_utc.isoformat()),
        )
        row = connection.execute("SELECT * FROM calculation_runs WHERE id=?", (cursor.lastrowid,)).fetchone()
    background_tasks.add_task(
        calculate_interval,
        row["id"],
        start_local,
        end_local,
        request.pairs,
        request.aspects,
        request.timezone,
    )
    return _run_to_response(row)


@app.get("/api/calculations/latest", response_model=RunResponse | None)
def latest_calculation(year: int = Query(ge=1800, le=2399)) -> RunResponse | None:
    start_utc, end_utc = _range_for_year(year)
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM calculation_runs WHERE range_start_utc=? AND range_end_utc=? ORDER BY id DESC LIMIT 1",
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchone()
        if not row:
            return None
        count = connection.execute(
            "SELECT COUNT(*) FROM planetary_events WHERE calculation_run_id=?", (row["id"],)
        ).fetchone()[0]
        return _run_to_response(row, count)


@app.get("/api/calculations/runs/{run_id}", response_model=RunResponse)
def calculation_run_details(run_id: int) -> RunResponse:
    with connect() as connection:
        row = connection.execute("SELECT * FROM calculation_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Calculation run not found")
        count = connection.execute("SELECT COUNT(*) FROM planetary_events WHERE calculation_run_id=?", (run_id,)).fetchone()[0]
    return _run_to_response(row, count)


@app.get("/api/calculations/runs/{run_id}/events", response_model=list[EventResponse])
def calculation_run_events(run_id: int) -> list[EventResponse]:
    with connect() as connection:
        exists = connection.execute("SELECT 1 FROM calculation_runs WHERE id=?", (run_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Calculation run not found")
        rows = connection.execute(
            """SELECT id, planet_1, planet_2, aspect_name, aspect_angle_degrees,
                      exact_time_utc, exact_time_local, timezone, longitude_1_degrees,
                      longitude_2_degrees, angular_separation_degrees, event_metadata_json
               FROM planetary_events WHERE calculation_run_id=? ORDER BY exact_time_utc""",
            (run_id,),
        ).fetchall()
    return [
        EventResponse(**{**dict(row), **_event_metadata(json.loads(row["event_metadata_json"]))})
        for row in rows
    ]


@app.get("/api/events", response_model=list[EventResponse])
def list_events(
    year: int = Query(ge=1800, le=2399),
    planet: str | None = None,
    aspect: str | None = None,
) -> list[EventResponse]:
    start_utc, end_utc = _range_for_year(year)
    with connect() as connection:
        latest = connection.execute(
            "SELECT id FROM calculation_runs WHERE range_start_utc=? AND range_end_utc=? AND status='completed' ORDER BY id DESC LIMIT 1",
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchone()
        if not latest:
            return []
        clauses = ["calculation_run_id=?"]
        params: list[object] = [latest["id"]]
        if planet:
            if planet not in {p.value for p in Planet}:
                raise HTTPException(status_code=422, detail="Unknown planet")
            clauses.append("(planet_1=? OR planet_2=?)")
            params.extend((planet, planet))
        if aspect:
            if aspect not in ASPECTS:
                raise HTTPException(status_code=422, detail="Unknown aspect")
            clauses.append("aspect_name=?")
            params.append(aspect)
        rows = connection.execute(
            "SELECT id, planet_1, planet_2, aspect_name, aspect_angle_degrees, exact_time_utc, exact_time_local, timezone, longitude_1_degrees, longitude_2_degrees, angular_separation_degrees, event_metadata_json FROM planetary_events WHERE "
            + " AND ".join(clauses)
            + " ORDER BY exact_time_utc",
            params,
        ).fetchall()
    return [EventResponse(**{**dict(row), **_event_metadata(json.loads(row["event_metadata_json"]))}) for row in rows]


@app.get("/api/reports/calendar/{year}.pdf")
def download_annual_calendar(year: int) -> Response:
    if year < 1800 or year > 2399:
        raise HTTPException(status_code=422, detail="Year must be between 1800 and 2399")
    start_utc, end_utc = _range_for_year(year)
    with connect() as connection:
        run = connection.execute(
            "SELECT * FROM calculation_runs WHERE range_start_utc=? AND range_end_utc=? AND status='completed' ORDER BY id DESC LIMIT 1",
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="Calculate this year before downloading its calendar")
        rows = connection.execute(
            "SELECT planet_1, planet_2, aspect_name, aspect_angle_degrees, exact_time_local, timezone FROM planetary_events WHERE calculation_run_id=? ORDER BY exact_time_utc",
            (run["id"],),
        ).fetchall()
    timezone_name = rows[0]["timezone"] if rows else "Asia/Kolkata"
    pdf = annual_calendar_pdf(year, [dict(row) for row in rows], timezone_name)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="astro-market-calendar-{year}.pdf"'})


def _pdf_download(filename: str, title: str, sections: list[tuple[str, list[str]]]) -> Response:
    return Response(content=research_detail_pdf(title, sections), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/reports/daily/{report_date}.pdf")
def download_daily_report(report_date: date) -> Response:
    """Daily research report; only includes source predictions already recorded."""
    start_utc, end_utc = _range_for_year(report_date.year)
    with connect() as connection:
        run = connection.execute(
            "SELECT id FROM calculation_runs WHERE range_start_utc=? AND range_end_utc=? AND status='completed' ORDER BY id DESC LIMIT 1",
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Calculate this year before downloading its daily report")
        events = connection.execute(
            "SELECT planet_1, planet_2, aspect_name, aspect_angle_degrees, exact_time_local FROM planetary_events WHERE calculation_run_id=? AND substr(exact_time_local,1,10)=? ORDER BY exact_time_utc",
            (run["id"], report_date.isoformat()),
        ).fetchall()
        published = connection.execute(
            """SELECT pe.id, pe.planet_1, pe.planet_2, pe.source_aspect_label, pe.source_angle_degrees,
                      pe.prediction_text, pe.source_locator, sd.title AS source_title
               FROM published_events pe LEFT JOIN source_documents sd ON sd.id=pe.source_document_id
               WHERE pe.event_date=? ORDER BY pe.id""", (report_date.isoformat(),),
        ).fetchall()
        times = {row["id"]: connection.execute("SELECT local_time, timezone, source_locator FROM published_times WHERE published_event_id=? ORDER BY local_time", (row["id"],)).fetchall() for row in published}
        rules = connection.execute(
            """SELECT DISTINCT tr.title, tr.hypothesis_text, tr.status, sd.title AS source_title
               FROM trader_rules tr JOIN rule_aspects ra ON ra.rule_id=tr.id
               LEFT JOIN source_documents sd ON sd.id=tr.source_document_id
               WHERE tr.status!='retired' AND EXISTS (
                 SELECT 1 FROM planetary_events pe WHERE pe.calculation_run_id=? AND substr(pe.exact_time_local,1,10)=?
                   AND pe.aspect_angle_degrees=ra.aspect_angle_degrees
                   AND ((pe.planet_1=ra.planet_1 AND pe.planet_2=ra.planet_2) OR (pe.planet_1=ra.planet_2 AND pe.planet_2=ra.planet_1))
               )""",
            (run["id"], report_date.isoformat()),
        ).fetchall()
    calculated_lines = [f"{event['exact_time_local'][11:16]}  {event['planet_1']} x {event['planet_2']}  {event['aspect_name']} {event['aspect_angle_degrees']} degrees" for event in events] or ["No calculated planetary aspects on this date."]
    source_lines: list[str] = []
    for item in published:
        source_lines.append(f"{item['planet_1']} x {item['planet_2']} | {item['source_aspect_label'] or 'aspect label not recorded'} | Source: {item['source_title'] or 'unspecified'}{(' | locator: ' + item['source_locator']) if item['source_locator'] else ''}")
        if item["prediction_text"]:
            source_lines.append(f"Published note: {item['prediction_text']}")
        for clock in times[item["id"]]:
            source_lines.append(f"Published time: {clock['local_time']} ({clock['timezone']}){(' | locator: ' + clock['source_locator']) if clock['source_locator'] else ''}")
    hypothesis_lines = [f"{rule['title']} [{rule['status']}] ({rule['source_title'] or 'no source linked'}): {rule['hypothesis_text']}" for rule in rules] or ["No associated trader hypotheses are recorded for this date."]
    return _pdf_download(f"astro-market-daily-{report_date.isoformat()}.pdf", f"Daily Research Report — {report_date.isoformat()}", [
        ("Calculated astronomical events (Asia/Kolkata)", calculated_lines),
        ("Trader-published notes and timings (source records)", source_lines or ["No trader prediction notes or published times are recorded for this date."]),
        ("Associated rulebook hypotheses (not verified claims)", hypothesis_lines),
        ("Market observations", ["Observed market results are available in the Backtesting module when matching historical candles have been imported."]),
    ])


@app.get("/api/reports/event/{event_id}.pdf")
def download_event_report(event_id: int) -> Response:
    with connect() as connection:
        event = connection.execute(
            """SELECT e.*, run.config_id FROM planetary_events e JOIN calculation_runs run ON run.id=e.calculation_run_id WHERE e.id=?""", (event_id,)
        ).fetchone()
        if not event:
            raise HTTPException(status_code=404, detail="Planetary event not found")
        rules = connection.execute(
            """SELECT tr.title, tr.status, tr.hypothesis_text, sd.title AS source_title FROM trader_rules tr
               JOIN rule_aspects ra ON ra.rule_id=tr.id LEFT JOIN source_documents sd ON sd.id=tr.source_document_id
               WHERE tr.status!='retired' AND ((ra.planet_1=? AND ra.planet_2=?) OR (ra.planet_1=? AND ra.planet_2=?)) AND ra.aspect_angle_degrees=?""",
            (event["planet_1"],event["planet_2"],event["planet_2"],event["planet_1"],event["aspect_angle_degrees"]),
        ).fetchall()
        published = connection.execute(
            """SELECT pe.*, sd.title AS source_title FROM published_events pe LEFT JOIN source_documents sd ON sd.id=pe.source_document_id
               WHERE pe.event_date=substr(?,1,10) AND ((pe.planet_1=? AND pe.planet_2=?) OR (pe.planet_1=? AND pe.planet_2=?))""",
            (event["exact_time_local"],event["planet_1"],event["planet_2"],event["planet_2"],event["planet_1"]),
        ).fetchall()
        market = connection.execute(
            """SELECT bm.symbol, br.timeframe_minutes, m.max_upward_move, m.max_downward_move, m.price_range, m.volatility, m.reversal_observed, m.time_to_reversal_seconds, m.sideways_observed
               FROM event_market_metrics m JOIN backtest_runs br ON br.id=m.backtest_run_id JOIN market_instruments bm ON bm.id=br.instrument_id
               WHERE m.planetary_event_id=?""", (event_id,),
        ).fetchall()
    event_lines = [f"Pair: {event['planet_1']} x {event['planet_2']}", f"Aspect: {event['aspect_name']} ({event['aspect_angle_degrees']} degrees)", f"Exact local time: {event['exact_time_local']} ({event['timezone']})", f"Longitude {event['planet_1']}: {event['longitude_1_degrees']:.6f} degrees", f"Longitude {event['planet_2']}: {event['longitude_2_degrees']:.6f} degrees", f"Angular separation: {event['angular_separation_degrees']:.6f} degrees", f"Calculation configuration id: {event['config_id']}"]
    rule_lines = [f"{row['title']} [{row['status']}] ({row['source_title'] or 'no linked source'}): {row['hypothesis_text']}" for row in rules] or ["No matching active hypotheses are recorded."]
    source_lines = [f"{row['planet_1']} x {row['planet_2']} | source aspect: {row['source_aspect_label'] or 'not recorded'} | {row['source_title'] or 'unspecified source'} | {row['prediction_text'] or 'No prediction text recorded.'}" for row in published] or ["No matching source prediction is recorded."]
    market_lines = [f"{row['symbol']} {row['timeframe_minutes']}m: max up {row['max_upward_move']}; max down {row['max_downward_move']}; range {row['price_range']}; volatility {row['volatility']}; reversal {row['reversal_observed']}; sideways {row['sideways_observed']}" for row in market] or ["No saved market backtest observation is linked to this event."]
    filename = f"astro-market-event-{event_id}.pdf"
    return _pdf_download(filename, f"Planetary Event Report — {event['exact_time_local'][:16]}", [("Calculated astronomical data", event_lines), ("Related rulebook hypotheses", rule_lines), ("Related source notes", source_lines), ("Observed market metrics", market_lines)])


def _event_metadata(metadata: dict[str, object]) -> dict[str, object]:
    if "calculation_settings" in metadata:
        return metadata
    # Read earlier records created before orb metadata was added.
    return {"calculation_settings": metadata}


@app.get("/api/dashboard")
def dashboard_summary(year: int = Query(ge=1800, le=2399)) -> dict[str, object]:
    start_utc, end_utc = _range_for_year(year)
    with connect() as connection:
        run = connection.execute(
            "SELECT * FROM calculation_runs WHERE range_start_utc=? AND range_end_utc=? ORDER BY id DESC LIMIT 1",
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchone()
        if run is None:
            return {"year": year, "run": None, "total_events": 0, "important_dates": 0, "moon_events": 0, "upcoming_events": [], "aspect_counts": []}
        count = connection.execute(
            "SELECT COUNT(*) FROM planetary_events WHERE calculation_run_id=?", (run["id"],)
        ).fetchone()[0]
        distinct_dates = connection.execute(
            "SELECT COUNT(DISTINCT substr(exact_time_local,1,10)) FROM planetary_events WHERE calculation_run_id=?",
            (run["id"],),
        ).fetchone()[0]
        moon_events = connection.execute(
            "SELECT COUNT(*) FROM planetary_events WHERE calculation_run_id=? AND (planet_1='Moon' OR planet_2='Moon')",
            (run["id"],),
        ).fetchone()[0]
        upcoming = connection.execute(
            "SELECT id, planet_1, planet_2, aspect_name, aspect_angle_degrees, exact_time_local FROM planetary_events WHERE calculation_run_id=? AND exact_time_utc>=? ORDER BY exact_time_utc LIMIT 6",
            (run["id"], datetime.now(timezone.utc).isoformat()),
        ).fetchall()
        counts = connection.execute(
            "SELECT aspect_name, COUNT(*) AS total FROM planetary_events WHERE calculation_run_id=? GROUP BY aspect_name ORDER BY total DESC",
            (run["id"],),
        ).fetchall()
        run_response = _run_to_response(run, count).model_dump()
    return {
        "year": year,
        "run": run_response,
        "total_events": count,
        "important_dates": distinct_dates,
        "moon_events": moon_events,
        "upcoming_events": [dict(row) for row in upcoming],
        "aspect_counts": [dict(row) for row in counts],
    }


@app.get("/api/trader/observations")
def trader_observations() -> list[dict[str, object]]:
    with connect() as connection:
        rows = connection.execute(
            """SELECT event.id, event.event_date, event.planet_1, event.planet_2,
                      event.source_aspect_label, event.source_angle_degrees,
                      event.prediction_text, event.source_locator, source.title AS source_title,
                      timing.id AS published_time_id, timing.local_time, timing.timezone
               FROM published_events event
               LEFT JOIN source_documents source ON source.id=event.source_document_id
               LEFT JOIN published_times timing ON timing.published_event_id=event.id
               ORDER BY event.event_date, event.id, timing.local_time"""
        ).fetchall()
    grouped: dict[int, dict[str, object]] = {}
    for row in rows:
        item = grouped.setdefault(
            row["id"],
            {
                "id": row["id"],
                "event_date": row["event_date"],
                "planet_1": row["planet_1"],
                "planet_2": row["planet_2"],
                "source_aspect_label": row["source_aspect_label"],
                "source_angle_degrees": row["source_angle_degrees"],
                "prediction_text": row["prediction_text"],
                "source_locator": row["source_locator"],
                "source_title": row["source_title"],
                "published_times": [],
            },
        )
        if row["published_time_id"] is not None:
            item["published_times"].append(
                {"id": row["published_time_id"], "time": row["local_time"], "timezone": row["timezone"]}
            )
    return list(grouped.values())


@app.post("/api/timing/analyze")
def analyze_published_timing(request: TimingAnalysisRequest) -> dict[str, object]:
    try:
        tz = ZoneInfo(request.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {request.timezone}") from exc
    with connect() as connection:
        observation = connection.execute(
            "SELECT * FROM published_events WHERE id=?", (request.published_event_id,)
        ).fetchone()
        if not observation:
            raise HTTPException(status_code=404, detail="Published timing observation not found")
        published_times = [
            row["local_time"]
            for row in connection.execute(
                "SELECT local_time FROM published_times WHERE published_event_id=? ORDER BY local_time",
                (request.published_event_id,),
            ).fetchall()
        ]
        method = connection.execute("SELECT id FROM timing_methods WHERE name=?", (request.method,)).fetchone()
        if not method:
            raise HTTPException(status_code=500, detail=f"Timing candidate '{request.method}' is not registered")
        event_rows = connection.execute(
            """SELECT event.exact_time_local
               FROM planetary_events event
               JOIN calculation_runs run ON run.id=event.calculation_run_id
               WHERE run.status='completed'
                 AND event.aspect_angle_degrees=?
                 AND ((event.planet_1=? AND event.planet_2=?) OR (event.planet_1=? AND event.planet_2=?))""",
            (
                observation["source_angle_degrees"],
                observation["planet_1"], observation["planet_2"],
                observation["planet_2"], observation["planet_1"],
            ),
        ).fetchall()

    source_midday = datetime.combine(date.fromisoformat(observation["event_date"]), time(12), tzinfo=tz)
    nearby_events = [
        datetime.fromisoformat(row["exact_time_local"])
        for row in event_rows
        if abs((datetime.fromisoformat(row["exact_time_local"]) - source_midday).total_seconds()) <= 3 * 86400
    ]
    exact_event = min(nearby_events, key=lambda item: abs((item - source_midday).total_seconds())) if nearby_events else None
    anchor = None
    if request.method == "aspect_time_interval":
        if exact_event is None:
            raise HTTPException(
                status_code=409,
                detail="No independently calculated event was found within three days. Calculate the relevant calendar year first.",
            )
        anchor = exact_event.hour * 60 + exact_event.minute + exact_event.second / 60

    try:
        fit = fit_timing_cycle(
            published_times,
            method=request.method,
            interval_minutes=request.interval_minutes,
            anchor_minutes=anchor,
            minimum_interval_minutes=request.minimum_interval_minutes,
            maximum_interval_minutes=request.maximum_interval_minutes,
            subdivisions=request.subdivisions,
            market_open=request.market_open,
            market_close=request.market_close,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = {
        "published_event_id": request.published_event_id,
        "method": request.method,
        "formula_parameters": {
            "interval_minutes": fit.interval_minutes,
            "anchor_time": minutes_to_clock(fit.anchor_minutes),
            "subdivisions": request.subdivisions if request.method == "session_fraction" else None,
            "market_open": request.market_open,
            "market_close": request.market_close,
        },
        "exact_aspect_time": exact_event.isoformat() if exact_event else None,
        "candidate_times": [minutes_to_clock(value) for value in fit.candidate_minutes],
        "comparisons": list(fit.comparisons),
        "mean_absolute_error_minutes": fit.mean_absolute_error_minutes,
        "root_mean_square_error_minutes": fit.root_mean_square_error_minutes,
        "random_phase_baseline_rmse_minutes": fit.random_phase_baseline_rmse_minutes,
        "training_note": "This score compares a candidate with the same published times used to fit it. Validate on separate dates before drawing conclusions.",
    }
    with connect() as connection:
        cursor = connection.execute(
            """INSERT INTO timing_comparisons
               (timing_method_id, published_event_id, calculated_at, timezone, error_seconds, result_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                method["id"],
                request.published_event_id,
                datetime.now(timezone.utc).isoformat(),
                request.timezone,
                fit.mean_absolute_error_minutes * 60,
                json.dumps(result, sort_keys=True),
            ),
        )
        result["comparison_id"] = cursor.lastrowid
    return result


@app.get("/api/timing/comparisons")
def timing_comparisons(published_event_id: int | None = Query(default=None, gt=0)) -> list[dict[str, object]]:
    with connect() as connection:
        if published_event_id is None:
            rows = connection.execute(
                """SELECT comparison.id, comparison.published_event_id, comparison.calculated_at,
                          method.name AS method, comparison.error_seconds, comparison.result_json
                   FROM timing_comparisons comparison
                   JOIN timing_methods method ON method.id=comparison.timing_method_id
                   ORDER BY comparison.id DESC LIMIT 50"""
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT comparison.id, comparison.published_event_id, comparison.calculated_at,
                          method.name AS method, comparison.error_seconds, comparison.result_json
                   FROM timing_comparisons comparison
                   JOIN timing_methods method ON method.id=comparison.timing_method_id
                   WHERE comparison.published_event_id=?
                   ORDER BY comparison.id DESC LIMIT 50""",
                (published_event_id,),
            ).fetchall()
    return [
        {
            "id": row["id"],
            "published_event_id": row["published_event_id"],
            "calculated_at": row["calculated_at"],
            "method": row["method"],
            "error_seconds": row["error_seconds"],
            "result": json.loads(row["result_json"]),
        }
        for row in rows
    ]


@app.post("/api/market/import")
def import_market_csv(
    file: UploadFile = File(...),
    symbol: Literal["NIFTY", "BANKNIFTY"] = Form(...),
    timeframe_minutes: Literal[1, 5] = Form(...),
    timezone_name: str = Form("Asia/Kolkata"),
) -> dict[str, object]:
    contents = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV files must be 100 MB or smaller")
    try:
        candles = parse_ohlc_csv(contents, timezone_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    display_names = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY Bank"}
    filename = Path((file.filename or "market-data.csv").replace("\\", "/")).name
    content_hash = hashlib.sha256(contents).hexdigest()
    first_timestamp = candles.iloc[0]["timestamp_utc"]
    last_timestamp = candles.iloc[-1]["timestamp_utc"]
    try:
        with connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO market_instruments(symbol,name,exchange,timezone) VALUES(?,?,?,?)",
                (symbol, display_names[symbol], "NSE", timezone_name),
            )
            instrument = connection.execute("SELECT id FROM market_instruments WHERE symbol=?", (symbol,)).fetchone()
            cursor = connection.execute(
                """INSERT INTO market_imports
                   (instrument_id, source_filename, timeframe_minutes, row_count, content_hash, status)
                   VALUES (?, ?, ?, ?, ?, 'completed')""",
                (instrument["id"], filename, timeframe_minutes, len(candles), content_hash),
            )
            import_id = cursor.lastrowid
            connection.executemany(
                """INSERT INTO market_candles
                   (market_import_id, instrument_id, timeframe_minutes, timestamp_utc,
                    open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        import_id,
                        instrument["id"],
                        timeframe_minutes,
                        row.timestamp_utc,
                        float(row.open),
                        float(row.high),
                        float(row.low),
                        float(row.close),
                        None if row.volume is None or str(row.volume).lower() in {"<na>", "nan"} else float(row.volume),
                    )
                    for row in candles.itertuples(index=False)
                ],
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="This import overlaps candle timestamps already stored for that instrument and timeframe. Remove duplicate rows from the CSV or import a non-overlapping range.",
        ) from exc

    return {
        "id": import_id,
        "symbol": symbol,
        "timeframe_minutes": timeframe_minutes,
        "row_count": len(candles),
        "first_timestamp_utc": first_timestamp,
        "last_timestamp_utc": last_timestamp,
        "source_filename": filename,
        "content_hash": content_hash,
    }


@app.get("/api/market/imports")
def market_imports() -> list[dict[str, object]]:
    with connect() as connection:
        rows = connection.execute(
            """SELECT imported.id, imported.source_filename, imported.timeframe_minutes,
                      imported.imported_at, imported.row_count, imported.status,
                      instrument.symbol, instrument.name,
                      MIN(candle.timestamp_utc) AS first_timestamp_utc,
                      MAX(candle.timestamp_utc) AS last_timestamp_utc
               FROM market_imports imported
               JOIN market_instruments instrument ON instrument.id=imported.instrument_id
               LEFT JOIN market_candles candle ON candle.market_import_id=imported.id
               GROUP BY imported.id ORDER BY imported.id DESC"""
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/backtests", status_code=202)
def start_backtest(request: BacktestRequest, background_tasks: BackgroundTasks) -> dict[str, object]:
    if request.planet and request.planet not in {planet.value for planet in Planet}:
        raise HTTPException(status_code=422, detail="Unknown planet")
    if request.aspect and request.aspect not in ASPECTS:
        raise HTTPException(status_code=422, detail="Unknown aspect")
    start_utc, end_utc = _range_for_year(request.year)
    with connect() as connection:
        instrument = connection.execute("SELECT * FROM market_instruments WHERE symbol=?", (request.symbol,)).fetchone()
        if not instrument:
            raise HTTPException(status_code=409, detail=f"Import {request.symbol} candles first")
        candle_count = connection.execute(
            "SELECT COUNT(*) FROM market_candles WHERE instrument_id=? AND timeframe_minutes=?",
            (instrument["id"], request.timeframe_minutes),
        ).fetchone()[0]
        if not candle_count:
            raise HTTPException(status_code=409, detail=f"Import {request.timeframe_minutes}-minute candles first")
        calculation = connection.execute(
            """SELECT id FROM calculation_runs
               WHERE range_start_utc=? AND range_end_utc=? AND status='completed'
               ORDER BY id DESC LIMIT 1""",
            (start_utc.isoformat(), end_utc.isoformat()),
        ).fetchone()
        if not calculation:
            raise HTTPException(status_code=409, detail=f"Calculate planetary events for {request.year} first")
        params = request.model_dump()
        cursor = connection.execute(
            """INSERT INTO backtest_runs
               (name, instrument_id, timeframe_minutes, calculation_run_id,
                parameters_json, baseline_description, prevents_lookahead)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (
                f"{request.symbol} {request.year} event windows",
                instrument["id"],
                request.timeframe_minutes,
                calculation["id"],
                json.dumps(params, sort_keys=True),
                "Outcomes use post-event candles for measurement; comparison windows use only up to five earlier available same-clock windows.",
            ),
        )
        run_id = cursor.lastrowid
    background_tasks.add_task(execute_backtest, run_id, params)
    return {"id": run_id, "status": "running", "year": request.year, "symbol": request.symbol}


@app.get("/api/backtests/{run_id}")
def backtest_details(run_id: int) -> dict[str, object]:
    with connect() as connection:
        run = connection.execute("SELECT * FROM backtest_runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Backtest run not found")
        count = connection.execute("SELECT COUNT(*) FROM event_market_metrics WHERE backtest_run_id=?", (run_id,)).fetchone()[0]
        available = connection.execute(
            "SELECT COUNT(*) FROM event_market_metrics WHERE backtest_run_id=? AND observed_metric_json LIKE '%\"data_available\": true%'",
            (run_id,),
        ).fetchone()[0]
        aggregates = connection.execute(
            """SELECT AVG(max_upward_move) AS mean_max_upward_move,
                      AVG(max_downward_move) AS mean_max_downward_move,
                      AVG(price_range) AS mean_price_range,
                      AVG(volatility) AS mean_volatility,
                      SUM(CASE WHEN reversal_observed=1 THEN 1 ELSE 0 END) AS reversals,
                      SUM(CASE WHEN sideways_observed=1 THEN 1 ELSE 0 END) AS sideways_windows
               FROM event_market_metrics WHERE backtest_run_id=?""",
            (run_id,),
        ).fetchone()
    params = json.loads(run["parameters_json"])
    return {
        "id": run["id"],
        "name": run["name"],
        "status": run["status"],
        "instrument_id": run["instrument_id"],
        "timeframe_minutes": run["timeframe_minutes"],
        "parameters": params,
        "baseline_description": run["baseline_description"],
        "prevents_lookahead": bool(run["prevents_lookahead"]),
        "started_at": run["started_at"],
        "completed_at": run["completed_at"],
        "event_windows": count,
        "windows_with_data": available,
        "metrics": dict(aggregates),
        "directional_accuracy": None,
    }


@app.get("/api/backtests/{run_id}/metrics")
def backtest_metrics(run_id: int, limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, object]]:
    with connect() as connection:
        exists = connection.execute("SELECT 1 FROM backtest_runs WHERE id=?", (run_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Backtest run not found")
        rows = connection.execute(
            """SELECT metric.id, metric.planetary_event_id, metric.published_event_id,
                      metric.window_start_utc, metric.window_end_utc, metric.max_upward_move,
                      metric.max_downward_move, metric.price_range, metric.volatility,
                      metric.reversal_observed, metric.time_to_reversal_seconds,
                      metric.sideways_observed, metric.directional_accuracy,
                      metric.baseline_metric_json, metric.observed_metric_json,
                      event.planet_1, event.planet_2, event.aspect_name,
                      event.aspect_angle_degrees, event.exact_time_local
               FROM event_market_metrics metric
               LEFT JOIN planetary_events event ON event.id=metric.planetary_event_id
               WHERE metric.backtest_run_id=? ORDER BY metric.window_start_utc LIMIT ?""",
            (run_id, limit),
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["baseline_metrics"] = json.loads(item.pop("baseline_metric_json"))
        item["observed_metrics"] = json.loads(item.pop("observed_metric_json"))
        results.append(item)
    return results


def _serialize_rule(connection, row) -> dict[str, object]:
    aspects = connection.execute(
        "SELECT planet_1, planet_2, aspect_angle_degrees FROM rule_aspects WHERE rule_id=? ORDER BY id",
        (row["id"],),
    ).fetchall()
    source = connection.execute(
        "SELECT title FROM source_documents WHERE id=?", (row["source_document_id"],)
    ).fetchone() if row["source_document_id"] is not None else None
    return {
        "id": row["id"],
        "title": row["title"],
        "hypothesis_text": row["hypothesis_text"],
        "status": row["status"],
        "source_document_id": row["source_document_id"],
        "source_title": source["title"] if source else None,
        "aspects": [dict(aspect) for aspect in aspects],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@app.get("/api/rules")
def list_rules(include_retired: bool = False) -> list[dict[str, object]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM trader_rules " + ("" if include_retired else "WHERE status!='retired' ") + "ORDER BY id"
        ).fetchall()
        return [_serialize_rule(connection, row) for row in rows]


@app.post("/api/rules", status_code=201)
def create_rule(request: RuleCreate) -> dict[str, object]:
    try:
        with connect() as connection:
            cursor = connection.execute(
                """INSERT INTO trader_rules (title, hypothesis_text, status, source_document_id)
                   VALUES (?, ?, ?, ?)""",
                (request.title.strip(), request.hypothesis_text.strip(), request.status, request.source_document_id),
            )
            rule_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO rule_aspects (rule_id, planet_1, planet_2, aspect_angle_degrees) VALUES (?, ?, ?, ?)",
                [(rule_id, aspect.planet_1.value, aspect.planet_2.value, aspect.aspect_angle_degrees) for aspect in request.aspects],
            )
            row = connection.execute("SELECT * FROM trader_rules WHERE id=?", (rule_id,)).fetchone()
            return _serialize_rule(connection, row)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A rule with this source and title already exists, or its source record is missing") from exc


@app.get("/api/rules/{rule_id}")
def get_rule(rule_id: int) -> dict[str, object]:
    with connect() as connection:
        row = connection.execute("SELECT * FROM trader_rules WHERE id=?", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")
        return _serialize_rule(connection, row)


@app.patch("/api/rules/{rule_id}")
def update_rule(rule_id: int, request: RulePatch) -> dict[str, object]:
    fields = request.model_dump(exclude_unset=True)
    fields.pop("aspects", None)
    aspects = request.aspects if "aspects" in request.model_fields_set else None
    if "title" in fields and fields["title"] is not None:
        fields["title"] = fields["title"].strip()
    if "hypothesis_text" in fields and fields["hypothesis_text"] is not None:
        fields["hypothesis_text"] = fields["hypothesis_text"].strip()
    columns = {"title", "hypothesis_text", "status", "source_document_id"}
    assignments = [f"{column}=?" for column in fields if column in columns]
    values = [fields[column] for column in fields if column in columns]
    if assignments:
        assignments.append("updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')")
    try:
        with connect() as connection:
            exists = connection.execute("SELECT 1 FROM trader_rules WHERE id=?", (rule_id,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Rule not found")
            if assignments:
                connection.execute(
                    "UPDATE trader_rules SET " + ", ".join(assignments) + " WHERE id=?",
                    (*values, rule_id),
                )
            if aspects is not None:
                connection.execute("DELETE FROM rule_aspects WHERE rule_id=?", (rule_id,))
                connection.executemany(
                    "INSERT INTO rule_aspects (rule_id, planet_1, planet_2, aspect_angle_degrees) VALUES (?, ?, ?, ?)",
                    [(rule_id, aspect.planet_1.value, aspect.planet_2.value, aspect.aspect_angle_degrees) for aspect in aspects],
                )
                connection.execute("UPDATE trader_rules SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (rule_id,))
            row = connection.execute("SELECT * FROM trader_rules WHERE id=?", (rule_id,)).fetchone()
            return _serialize_rule(connection, row)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A rule with this source and title already exists, or its source record is missing") from exc


@app.delete("/api/rules/{rule_id}")
def retire_rule(rule_id: int) -> dict[str, object]:
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE trader_rules SET status='retired', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (rule_id,),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
    return {"id": rule_id, "status": "retired"}
