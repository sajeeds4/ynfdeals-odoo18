# HJAY9672-WN Portable Project Documentation

## 1. Project Overview

This repository contains the YNF Deals livestream operations platform, including:

- Legacy server runtime under `whatnot-collector/server`
- FastAPI additive runtime under `whatnot-collector/app`
- Dashboard frontend under `whatnot-collector/dashboard-vite`
- Operational scripts, migration tooling, and backup assets

The primary runtime used by the team is typically served on port `8088`.

## 2. Repository Layout

- `whatnot-collector/`
  - `app/`: FastAPI app, API routers, services, background worker integration
  - `server/`: Legacy runtime, database access, analytics logic, collectors
  - `dashboard-vite/`: React/Vite frontend for Company and Operator pages
  - `docs/`: System and migration documentation
  - `tools/`: Operational scripts and maintenance tooling
  - `data/`: Runtime state, backups, migration artifacts (mostly ignored in git)

- `medusa/`: Medusa-related integration scaffolding
- `tools/`: Top-level helper scripts

## 3. Runtime Components

### 3.1 API Layer

- Legacy entry point: `python -m server`
- FastAPI entry point: `uvicorn app.main:app --host 0.0.0.0 --port 8088`

### 3.2 Frontend

- Path: `whatnot-collector/dashboard-vite`
- Build/dev commands:
  - `npm install`
  - `npm run dev`

### 3.3 Async/Worker Stack

Optional Celery worker queues are configured under `whatnot-collector/app/workers`.

## 4. Database Model

The project is in a PostgreSQL-primary migration phase with sidecar and historical SQLite support.

- Legacy and sidecar logic: `whatnot-collector/server/postgres_sidecar.py`
- Cutover control and domain toggles: `whatnot-collector/server/postgres_cutover.py`
- Runtime diagnostics and database health: `whatnot-collector/app/services/database_status_service.py`

## 5. PostgreSQL Copy Included In GitLab

Two SQL export artifacts exist in local storage:

1. Large archive (not committed):
   - `whatnot-collector/data/migration_backups/whatnot_sidecar_sqlite_mirror_before_postgres_enable_20260430_164807.sql`
   - Size: about 15 GB

2. Portable SQL copy (committed):
   - `whatnot-collector/data/strong_backups/session_cleanup_keep_18_20260430_180610/postgres_session_tables_data.sql`
   - Size: about 4.5 MB

Reason the 15 GB file is not committed:

- It exceeds practical repository push limits and would make cloning/pulling unstable.

Recommended handling for the 15 GB backup:

- Store in object storage or backup volume.
- Track SHA256 and location in an internal runbook.
- Keep the committed 4.5 MB SQL copy in git for portability.

## 6. Local Setup

From repository root:

1. `cd whatnot-collector`
2. `python3 -m venv .venv`
3. `source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. `cd dashboard-vite && npm install`

## 7. Start Services

From `whatnot-collector`:

- API server:
  - `source .venv/bin/activate`
  - `uvicorn app.main:app --host 0.0.0.0 --port 8088`

- Frontend:
  - `cd dashboard-vite`
  - `npm run dev`

## 8. Auth and Access

The dashboard uses cookie-based auth (`wn_session`, `wn_csrf`) and role-based authorization.

Relevant modules:

- `whatnot-collector/server/auth.py`
- `whatnot-collector/app/services/legacy_auth_admin_service.py`

## 9. Performance and Profiling

Profiler script:

- `whatnot-collector/tools/profile_dashboard_api.py`

Example:

- `./.venv/bin/python tools/profile_dashboard_api.py --base-url http://127.0.0.1:8088 --path /api/company/intelligence --rounds 2`

## 10. Operator Page Health Check

Main operator frontend route:

- `/operator`

Main related view source:

- `whatnot-collector/dashboard-vite/src/views/Operator.jsx`

Primary operator API dependencies include:

- `/api/stream_status`
- `/api/current_lot/products`
- `/api/session_stats`
- `/api/v2/sessions/current/stats`

## 11. GitLab Project Metadata

- Host: `code.cybertechnainc.com`
- Namespace owner: `sajeed.gulam`
- Project: `hjay9672-WN-portable`

## 12. Notes For Administrators

- Keep production secrets out of git.
- Use masked CI/CD variables for tokens and credentials.
- Avoid committing large binary dumps directly to git history.
