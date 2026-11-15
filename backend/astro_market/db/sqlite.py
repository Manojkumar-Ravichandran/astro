"""Small SQLite boundary; domain modules use this adapter rather than SQL paths."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = BACKEND_ROOT / "migrations" / "0001_initial.sql"
MIGRATIONS_DIR = MIGRATION_PATH.parent


def database_path() -> Path:
    configured = os.environ.get("ASTRO_DB_PATH")
    return Path(configured).expanduser().resolve() if configured else BACKEND_ROOT / "data" / "astro_market.sqlite3"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with connect() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
        )
    for migration in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version = migration.stem
        with connect() as connection:
            applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
            ).fetchone()
            if not applied:
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
    with connect() as connection:
        connection.execute(
            """INSERT OR IGNORE INTO calculation_configs
               (id, name, zodiac, coordinate_frame, longitude_type, timezone,
                ephemeris_name, ephemeris_version, ephemeris_flags, parameters_json)
               VALUES (1, 'Default tropical apparent geocentric', 'tropical',
                       'geocentric', 'apparent_ecliptic', 'Asia/Kolkata',
                       'Swiss Ephemeris', NULL, '["FLG_SWIEPH","FLG_SPEED"]', '{}')"""
        )
