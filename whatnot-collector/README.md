# Whatnot Livestream Collector

Playwright-based collector for Whatnot livestream auctions, plus a local dashboard for live ops.

## Status
- Collector extracts live events.
- `python -m server` serves the API used by the dashboard UI.
- `dashboard-vite` is the React UI.

## Quick Start
1. Create a virtualenv.
2. Install deps.
3. Install Playwright browsers.
4. Configure `.env`.
5. Run the collector.
6. Run the API server (`python -m server`).
7. Run the React dashboard (`dashboard-vite`).

## Login (cookie-based)
1. Export cookies for `whatnot.com` from a real browser to `www.whatnot.com_cookies.json`.
2. Set `COOKIES_PATH` in `.env`.
3. Use `tools_open.py` to verify login and inspect selectors.

## API Server
- Start: `python -m server`
- Base URL: `http://localhost:8088`
- Provides live events plus local company/inventory/order endpoints for dashboard actions.

## Next-Gen FastAPI + Celery Runtime
- The new additive runtime lives under [`app/`](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/app).
- It is scaffolded beside the current `python -m server` runtime so we can migrate safely.
- Install runtime packages:
  - `pip install '.[runtime]'`
- Start FastAPI:
  - `uvicorn app.main:app --host 0.0.0.0 --port 8090`
- Start default worker:
  - `celery -A app.workers.celery_app.celery_app worker -Q default --loglevel=info`
- Start analytics worker:
  - `celery -A app.workers.celery_app.celery_app worker -Q analytics --loglevel=info`
- Start ingest/support worker:
  - `celery -A app.workers.celery_app.celery_app worker -Q ingest_support --loglevel=info`
- Optional beat scheduler:
  - `celery -A app.workers.celery_app.celery_app beat --loglevel=info`

## React Dashboard (Vite)
- Location: `dashboard-vite`
- Run:
  - `npm install`
  - `npm run dev`

## Optional Viewer Count
- Set `VIEWER_COUNT_SELECTOR` to a CSS selector that targets the viewer count element.
- Example: `VIEWER_COUNT_SELECTOR="button[aria-label*='viewers']"`

## Company Runtime
- The collector stores live event data in SQLite.
- The dashboard API reads and writes company sessions, lots, products, inventory, customers, and sale orders from the local app database.
- `WHATNOT_SESSION_ID` is used to bind the collector process to the active local company session.

## Odoo Integration
- Set `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_API_KEY` to enable posting winners to Odoo.
- Optional: `WHATNOT_SESSION_ID` to bind events to a specific session.

## Notes
- Ensure your usage complies with Whatnot's Terms of Service.
- This project stores raw events in SQLite by default.

## Optional Redis Sidecar
- Redis is scaffolded as an optional sidecar and is disabled by default.
- Nothing in the app uses Redis unless you explicitly turn it on later.
- Intended future use:
  - live collector leases / failover
  - current lot and winner cache
  - pending winner queue acceleration
  - pub/sub or websocket fanout for low-latency dashboard updates
  - stream append-only live event buffers
  - token-based standby promotion safety
  - ephemeral counters and health heartbeats
- Config:
  - `REDIS_ENABLED=0`
  - `REDIS_URL=redis://127.0.0.1:6379/0`
  - `REDIS_PREFIX=wnlive`
  - `REDIS_LEASE_TTL_SEC=10`
  - `REDIS_SOCKET_CONNECT_TIMEOUT_SEC=1.0`
  - `REDIS_SOCKET_TIMEOUT_SEC=1.5`
  - `REDIS_HEALTH_CACHE_SEC=2.0`
- Current isolated sidecar helpers:
  - JSON get/set
  - pub/sub publish
  - stream append
  - counters
  - lease acquire / renew / release
  - heartbeat keys
  - cached health checks
  - sync service for:
    - collector state
    - shared scan state
    - company sessions
    - pending winner queues
    - auction result snapshots
- Optional install:
  - `pip install '.[redis]'`

## Postgres + Redis Sidecar Mirror
- The live app can keep using SQLite while a sidecar mirrors data to Postgres and Redis.
- Intended use:
  - prepare a safe PostgreSQL migration without changing live reads/writes
  - keep hot live state available in Redis for future low-latency features
- Local sidecar dependencies:
  - `pip install '.[sidecar]'`
- Sidecar config:
  - `POSTGRES_SIDECAR_ENABLED=0`
  - `POSTGRES_SIDECAR_DBNAME=whatnot_sidecar`
  - `POSTGRES_SIDECAR_DSN=dbname=whatnot_sidecar`
  - `POSTGRES_SIDECAR_SCHEMA=sqlite_mirror`
  - `POSTGRES_SIDECAR_BATCH_SIZE=5000`
  - `POSTGRES_SIDECAR_HOT_SYNC_INTERVAL_SEC=60`
  - `POSTGRES_SIDECAR_FULL_SYNC_INTERVAL_SEC=21600`
  - `REDIS_EMBEDDED_DB_PATH=<project>/data/redislite/sidecar.redis`
  - `REDIS_SIDECAR_SYNC_INTERVAL_SEC=15`
- Run once:
  - `python -m server.sidecar_runner --once --postgres --redis`
- Run continuously:
  - `python -m server.sidecar_runner --postgres --redis`

## Docs
- [Documentation Index](docs/INDEX.md)
- [Intern Handbook](docs/intern_handbook.md)
- [Technical Architecture Guide](docs/technical_architecture.md)
- [API Reference](docs/api_reference.md)
- [Database Schema Reference](docs/database_schema_reference.md)
- [Sidecar Mirror Guide](docs/sidecar_mirror_guide.md)
- [Postgres Primary Cutover Plan](docs/postgres_primary_cutover_plan.md)
