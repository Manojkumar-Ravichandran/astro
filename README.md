# Astro Market Analyzer

Local-first research platform for calculating planetary events and testing trader-published market hypotheses against historical NIFTY and BANK NIFTY data. Astronomical calculations, trader interpretations, and observed market results are stored as separate records.

## Current milestone

Phases 1–10 are implemented for private local research: astronomy calculations and calendar, planetary range calculator, timing-method comparisons, CSV import/backtesting, editable trader hypothesis rulebook, and annual, daily, and per-event PDF reports. The 2026 comparison reproduced five supplied Moon–Venus event times within seconds of the preliminary results and found the Sun–Saturn 135° event on August 22 rather than the trader's August 20 date. See [`backend/research/2026-example-validation.md`](backend/research/2026-example-validation.md).

## Proposed architecture

- `frontend/`: Next.js App Router, TypeScript, and Ant Design dashboard and research modules.
- `backend/`: FastAPI service; astronomy and numerical analysis modules remain independent of the API layer.
- `backend/astro_market/db/`: SQLite connection and repository boundary, keeping SQL-specific code out of domain logic.
- `backend/migrations/`: ordered SQL migrations. The initial schema uses portable relational concepts so the repository layer can later target MongoDB or another store.
- Astronomy calculations will use Swiss Ephemeris (`pyswisseph`) explicitly, beginning with geocentric tropical apparent ecliptic longitudes. Settings, flags, ephemeris version, and timezone are recorded for reproducibility. Licensing will be reviewed before distributing the application or ephemeris data.

The initial data model keeps source material (`source_documents`, `published_events`, `published_times`, `trader_rules`) distinct from calculated facts (`calculation_runs`, `planetary_events`) and observed data (`market_candles`, `backtest_runs`, `event_market_metrics`). Candidate timing methods and their results are also stored independently from published timings.

The calculation module is `backend/astro_market/astronomy.py`. It requests Swiss Ephemeris apparent geocentric ecliptic longitude with speed, handles UTC/JD conversions, exposes the seven planets and seven standard aspects, and brackets then refines angular crossings using `scipy.optimize.brentq`. The dependency uses `pysweph`, the maintained Windows-wheel-capable continuation of the `pyswisseph` Python binding; it links to the same official Swiss Ephemeris C library and retains the `swisseph` import. Swiss Ephemeris data-file use is required by default; if the library falls back to its built-in Moshier method, the calculation raises rather than silently returning that result. Supply an ephemeris path in `CalculationConfig` containing the required Swiss data files.

## Swiss Ephemeris licensing

For this private local-use project, the distribution/public-service decision is not in scope. If you later distribute the software or activate a public service using Swiss Ephemeris, its terms require choosing and complying with AGPL or the Swiss Ephemeris Professional License first. See [`backend/LICENSE-NOTES.md`](backend/LICENSE-NOTES.md) and the [official Swiss Ephemeris licensing page](https://www.astro.com/swisseph/swephinfo_e.htm).

## Local development

The frontend and FastAPI service run as separate local processes. SQLite is the local store. CSV market imports are the initial ingestion path.

Install the Python package with `python -m pip install -e backend`, then fetch the official planetary and lunar Swiss Ephemeris data files with `python backend/scripts/download_ephemeris.py`. They are stored under `backend/ephe/` and are intentionally excluded from Git. Pass that directory as `CalculationConfig(ephemeris_path=...)`.

Run the local service with `python -m uvicorn astro_market.api:app --app-dir backend --reload` from the project root. In a second terminal, run `npm ci` and `npm run dev` from `frontend/`. The app uses `http://localhost:8000` for the API by default; set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to change it. The reports screen downloads annual and daily PDFs; click an event in the calendar to download its event report.

## Phase 2 schema

The initial SQLite schema is in [`backend/migrations/0001_initial.sql`](backend/migrations/0001_initial.sql). It includes reproducible calculation settings, event/source provenance, original trader times, editable hypotheses, market candles, and backtest outputs. It does not seed invented astronomical events or trader interpretations.
