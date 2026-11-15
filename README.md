# Astro Market Analyzer

Local-first research platform for calculating planetary events and testing trader-published market hypotheses against historical NIFTY and BANK NIFTY data. Astronomical calculations, trader interpretations, and observed market results are stored as separate records.

## Current milestone

Phase 1 inspection found an empty workspace: no existing application, package manifest, backend, or database. Phase 2 establishes the architecture and initial SQLite schema. No astronomy calculations or market predictions are implemented yet.

## Proposed architecture

- `frontend/`: Next.js App Router, TypeScript, and Ant Design dashboard and research modules.
- `backend/`: FastAPI service; astronomy and numerical analysis modules remain independent of the API layer.
- `backend/astro_market/db/`: SQLite connection and repository boundary, keeping SQL-specific code out of domain logic.
- `backend/migrations/`: ordered SQL migrations. The initial schema uses portable relational concepts so the repository layer can later target MongoDB or another store.
- Astronomy calculations will use Swiss Ephemeris (`pyswisseph`) explicitly, beginning with geocentric tropical apparent ecliptic longitudes. Settings, flags, ephemeris version, and timezone are recorded for reproducibility. Licensing will be reviewed before distributing the application or ephemeris data.

The initial data model keeps source material (`source_documents`, `published_events`, `published_times`, `trader_rules`) distinct from calculated facts (`calculation_runs`, `planetary_events`) and observed data (`market_candles`, `backtest_runs`, `event_market_metrics`). Candidate timing methods and their results are also stored independently from published timings.

## Local development

The frontend and FastAPI service will run as separate local processes. SQLite is the initial store. CSV market imports are the initial ingestion path. Setup commands will be added as the respective application phases are implemented.

## Phase 2 schema

The initial SQLite schema is in [`backend/migrations/0001_initial.sql`](backend/migrations/0001_initial.sql). It includes reproducible calculation settings, event/source provenance, original trader times, editable hypotheses, market candles, and backtest outputs. It does not seed invented astronomical events or trader interpretations.
