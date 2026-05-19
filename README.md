# HJAY9672-WN Portable Repository

## Overview

This repository contains the YNF Deals livestream operations stack:

- API runtimes (`whatnot-collector/server` and `whatnot-collector/app`)
- React dashboard (`whatnot-collector/dashboard-vite`)
- Data tooling, migration scripts, and operational utilities

## Main Runtime Port

The team typically runs the main app on:

- `http://127.0.0.1:8088`

## Documentation

- Full project documentation for GitLab mirror, setup, architecture, and PostgreSQL copy handling:
	- `GITLAB_FULL_DOCUMENTATION.md`

- Runtime-specific documentation:
	- `whatnot-collector/README.md`
	- `whatnot-collector/docs/`

## PostgreSQL Copy

- Lightweight SQL artifacts committed for repository portability:
	- `whatnot-collector/data/strong_backups/session_cleanup_keep_18_20260430_180610/postgres_session_tables_data.sql` (placeholder)
	- `whatnot-collector/data/strong_backups/session_cleanup_keep_18_20260430_180610/postgres_session_tables_schema.sql`
	- `whatnot-collector/data/strong_backups/session_cleanup_keep_18_20260430_180610/postgres_session_tables_demo.sql`

- Very large historical SQL archive (15 GB) is intentionally not committed due repository size constraints.

## Post-Clone PostgreSQL Setup

From `whatnot-collector`, run:

- `./scripts/bootstrap_postgres_clone.sh`

This is the supported one-command bootstrap for local Postgres after clone.

