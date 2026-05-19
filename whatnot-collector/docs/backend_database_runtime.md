# Backend Database Runtime

The dashboard runs on a Python FastAPI backend with PostgreSQL as the expected primary runtime for configured domains. SQLite is no longer the normal runtime database; keep it as an archive/manual comparison source only when an operator deliberately enables a compatibility check.

## Current Safe Default

- FastAPI serves the API and dashboard.
- `.env.example` sets the configured `DB_PRIMARY_DOMAIN_*` flags to `postgres`.
- `ALLOW_SQLITE_RUNTIME=0` disables runtime SQLite access by default.
- `COLLECTOR_SQLITE_FALLBACK_ENABLED=0` disables collector SQLite fallback by default.
- Dual-write / reverse-shadow flags are off by default.
- Validation flags remain enabled so Postgres-primary domains can still report mismatches.

## Status Endpoint

Use this endpoint before changing database flags:

```text
GET /api/v2/diagnostics/database
```

It reports:

- SQLite retired status without opening the SQLite file in the default runtime.
- PostgreSQL driver, DSN, connection, and schema readiness.
- Primary backend per business domain.
- Dual-write and validation flags.
- Fail-closed state when PostgreSQL or a configured domain is incomplete.

## Safe Migration Order

The historical domain-by-domain order is documented in [postgres_primary_cutover_plan.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/postgres_primary_cutover_plan.md). The current work is not restarting that promotion sequence; it is validating Postgres-only operation and proving any remaining SQLite helpers are fail-closed, archive-only, or removed.

Current checks should focus on:

1. Verify `/api/v2/diagnostics/database` shows PostgreSQL connected and schema-ready.
2. Confirm all configured domains report `postgres` primary unless a rollback is intentional.
3. Confirm production workers do not set `ALLOW_SQLITE_RUNTIME=1`.
4. Confirm collector runs without `DB_PATH` when PostgreSQL is available.
5. Inspect cutover mismatch logs after running the current verifier modules.
6. Classify any remaining SQLite helper surface as guarded archive/manual comparison code or remove it.

## Example Environment Flags

Default runtime posture:

```bash
POSTGRES_SIDECAR_ENABLED=1
DB_PRIMARY_DOMAIN_SETTINGS=postgres
DB_PRIMARY_DOMAIN_REVIEWS=postgres
DB_PRIMARY_DOMAIN_EMPLOYEES=postgres
DB_PRIMARY_DOMAIN_IN_HOUSE=postgres
DB_PRIMARY_DOMAIN_INVENTORY=postgres
DB_PRIMARY_DOMAIN_COMPANY=postgres
DB_PRIMARY_DOMAIN_EVENTS=postgres
DB_PRIMARY_DOMAIN_ANALYTICS=postgres
EVENTS_DB_READ_BACKEND=postgres
EVENTS_DB_VALIDATE_READS=1
COLLECTOR_SQLITE_FALLBACK_ENABLED=0
ALLOW_SQLITE_RUNTIME=0
```

## Rule

Do not re-enable SQLite as a runtime fallback to hide PostgreSQL failures. A failed PostgreSQL dependency should fail closed, surface in diagnostics, and be fixed or explicitly rolled back with a documented operator decision.
