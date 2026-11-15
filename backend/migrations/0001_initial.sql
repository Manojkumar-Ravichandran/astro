PRAGMA foreign_keys = ON;

-- Calculation configuration is immutable once referenced by a run. Store all
-- choices that can change a result, including timezone and ephemeris version.
CREATE TABLE calculation_configs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    zodiac TEXT NOT NULL CHECK (zodiac IN ('tropical', 'sidereal')),
    coordinate_frame TEXT NOT NULL DEFAULT 'geocentric',
    longitude_type TEXT NOT NULL DEFAULT 'apparent_ecliptic',
    sidereal_mode TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    ephemeris_name TEXT NOT NULL DEFAULT 'Swiss Ephemeris',
    ephemeris_version TEXT,
    ephemeris_flags TEXT NOT NULL DEFAULT '[]',
    parameters_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK ((zodiac = 'sidereal' AND sidereal_mode IS NOT NULL) OR zodiac = 'tropical')
);

CREATE TABLE calculation_runs (
    id INTEGER PRIMARY KEY,
    config_id INTEGER NOT NULL REFERENCES calculation_configs(id),
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    completed_at TEXT,
    range_start_utc TEXT NOT NULL,
    range_end_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    software_version TEXT,
    error_message TEXT,
    CHECK (range_end_utc > range_start_utc)
);

CREATE TABLE source_documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    source_name TEXT,
    source_url TEXT,
    published_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Source labels preserve wording from a trader's material; calculated events
-- use standard aspect names and angles in planetary_events.
CREATE TABLE published_events (
    id INTEGER PRIMARY KEY,
    source_document_id INTEGER REFERENCES source_documents(id) ON DELETE SET NULL,
    event_date TEXT NOT NULL,
    planet_1 TEXT NOT NULL,
    planet_2 TEXT NOT NULL,
    source_aspect_label TEXT,
    source_angle_degrees REAL,
    prediction_text TEXT,
    source_locator TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE published_times (
    id INTEGER PRIMARY KEY,
    published_event_id INTEGER NOT NULL REFERENCES published_events(id) ON DELETE CASCADE,
    local_time TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    source_locator TEXT,
    notes TEXT
);

CREATE TABLE planetary_events (
    id INTEGER PRIMARY KEY,
    calculation_run_id INTEGER NOT NULL REFERENCES calculation_runs(id) ON DELETE CASCADE,
    planet_1 TEXT NOT NULL,
    planet_2 TEXT NOT NULL,
    aspect_name TEXT NOT NULL,
    aspect_angle_degrees REAL NOT NULL,
    exact_time_utc TEXT NOT NULL,
    exact_time_local TEXT NOT NULL,
    timezone TEXT NOT NULL,
    longitude_1_degrees REAL NOT NULL CHECK (longitude_1_degrees >= 0 AND longitude_1_degrees < 360),
    longitude_2_degrees REAL NOT NULL CHECK (longitude_2_degrees >= 0 AND longitude_2_degrees < 360),
    angular_separation_degrees REAL NOT NULL,
    event_metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (calculation_run_id, planet_1, planet_2, aspect_angle_degrees, exact_time_utc)
);

CREATE TABLE timing_methods (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE timing_comparisons (
    id INTEGER PRIMARY KEY,
    timing_method_id INTEGER NOT NULL REFERENCES timing_methods(id) ON DELETE CASCADE,
    published_event_id INTEGER NOT NULL REFERENCES published_events(id) ON DELETE CASCADE,
    calculated_at TEXT NOT NULL,
    timezone TEXT NOT NULL,
    error_seconds REAL,
    result_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE trader_rules (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    hypothesis_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'hypothesis' CHECK (status IN ('hypothesis','under_test','supported','not_supported','retired')),
    source_document_id INTEGER REFERENCES source_documents(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE rule_aspects (
    id INTEGER PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES trader_rules(id) ON DELETE CASCADE,
    planet_1 TEXT NOT NULL,
    planet_2 TEXT NOT NULL,
    aspect_angle_degrees REAL NOT NULL,
    UNIQUE (rule_id, planet_1, planet_2, aspect_angle_degrees)
);

CREATE TABLE market_instruments (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    exchange TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata'
);

CREATE TABLE market_imports (
    id INTEGER PRIMARY KEY,
    instrument_id INTEGER NOT NULL REFERENCES market_instruments(id),
    source_filename TEXT NOT NULL,
    timeframe_minutes INTEGER NOT NULL CHECK (timeframe_minutes IN (1,5)),
    imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    row_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('running','completed','failed')),
    error_message TEXT
);

CREATE TABLE market_candles (
    id INTEGER PRIMARY KEY,
    market_import_id INTEGER NOT NULL REFERENCES market_imports(id) ON DELETE CASCADE,
    instrument_id INTEGER NOT NULL REFERENCES market_instruments(id),
    timeframe_minutes INTEGER NOT NULL CHECK (timeframe_minutes IN (1,5)),
    timestamp_utc TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    UNIQUE (instrument_id, timeframe_minutes, timestamp_utc),
    CHECK (high >= low),
    CHECK (high >= open AND high >= close),
    CHECK (low <= open AND low <= close)
);

CREATE TABLE backtest_runs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    instrument_id INTEGER NOT NULL REFERENCES market_instruments(id),
    timeframe_minutes INTEGER NOT NULL CHECK (timeframe_minutes IN (1,5)),
    calculation_run_id INTEGER REFERENCES calculation_runs(id),
    parameters_json TEXT NOT NULL DEFAULT '{}',
    baseline_description TEXT,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    prevents_lookahead INTEGER NOT NULL DEFAULT 1 CHECK (prevents_lookahead IN (0,1))
);

CREATE TABLE event_market_metrics (
    id INTEGER PRIMARY KEY,
    backtest_run_id INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    planetary_event_id INTEGER REFERENCES planetary_events(id) ON DELETE SET NULL,
    published_event_id INTEGER REFERENCES published_events(id) ON DELETE SET NULL,
    window_start_utc TEXT NOT NULL,
    window_end_utc TEXT NOT NULL,
    max_upward_move REAL,
    max_downward_move REAL,
    price_range REAL,
    volatility REAL,
    reversal_observed INTEGER CHECK (reversal_observed IN (0,1)),
    time_to_reversal_seconds INTEGER,
    sideways_observed INTEGER CHECK (sideways_observed IN (0,1)),
    directional_accuracy REAL,
    baseline_metric_json TEXT NOT NULL DEFAULT '{}',
    observed_metric_json TEXT NOT NULL DEFAULT '{}',
    CHECK (window_end_utc > window_start_utc)
);

CREATE INDEX idx_planetary_events_time ON planetary_events(exact_time_utc);
CREATE INDEX idx_planetary_events_pair ON planetary_events(planet_1, planet_2, aspect_angle_degrees);
CREATE INDEX idx_published_events_date ON published_events(event_date);
CREATE INDEX idx_published_times_event ON published_times(published_event_id);
CREATE INDEX idx_market_candles_lookup ON market_candles(instrument_id, timeframe_minutes, timestamp_utc);
CREATE INDEX idx_metrics_run ON event_market_metrics(backtest_run_id);
