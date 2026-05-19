# Migration Progress Tracker

Use this as the single running tracker for the runtime migration.

## Overall Status

- Main runtime: `Complete`
- SQLite-to-Postgres cutover: `Resumed Postgres-only validation`
- Stabilization phase: `Active`
- Deferred tracks: `Postgres-backed where implemented; SQLite blockers remain where listed below`

## Resumed Cutover State

Current expected runtime posture:

- `.env.example` is Postgres-primary for all configured domains:
  - `DB_PRIMARY_DOMAIN_SETTINGS=postgres`
  - `DB_PRIMARY_DOMAIN_REVIEWS=postgres`
  - `DB_PRIMARY_DOMAIN_EMPLOYEES=postgres`
  - `DB_PRIMARY_DOMAIN_IN_HOUSE=postgres`
  - `DB_PRIMARY_DOMAIN_INVENTORY=postgres`
  - `DB_PRIMARY_DOMAIN_COMPANY=postgres`
  - `DB_PRIMARY_DOMAIN_EVENTS=postgres`
  - `DB_PRIMARY_DOMAIN_ANALYTICS=postgres`
- granular inventory, company, and ingest cutover flags are also Postgres-primary in `.env.example`
- event reads are Postgres-backed with validation enabled:
  - `EVENTS_DB_READ_BACKEND=postgres`
  - `EVENTS_DB_VALIDATE_READS=1`
- SQLite runtime use is disabled unless a worker deliberately opts into a manual compatibility check:
  - `ALLOW_SQLITE_RUNTIME=0`
  - `COLLECTOR_SQLITE_FALLBACK_ENABLED=0`
- reverse-shadow / dual-write is off by default:
  - `DB_DUAL_WRITE_* = 0`
- write/read validation remains on:
  - `DB_VALIDATE_WRITE_* = 1`
- the standalone inventory verifier is retired from the normal validation loop; inventory confidence now comes through the active company/runtime checks plus mismatch-log review

This is no longer the original mirror-first plan. Treat SQLite as a retired runtime dependency and a manual comparison/archive source only.

## Completed

### Core Runtime

- [x] FastAPI is the primary public runtime
- [x] Compatibility bridge removed from the core operational path
- [x] Redis is active for runtime observability
- [x] Redis is active for locks / runtime state
- [x] Celery is active for real background work
- [x] Postgres-backed main operational runtime is in place

### Core Native FastAPI Surface

- [x] Core live read paths
- [x] Core live runtime mutation paths
- [x] Safe admin/business mutation paths
- [x] Non-bulk sale-order / auction-result mutation paths
- [x] Inventory product update/delete
- [x] High-value analytics endpoints
- [x] High-value competitor/shop subset

## Active Phase

### Stabilization

- [ ] FastAPI runtime health review
- [ ] Redis metrics / runtime state review
- [ ] Celery queue / worker health review
- [ ] Bridge-hit review
- [ ] Request latency / error review
- [ ] Postgres-only cutover validation review
- [ ] Confirm no production process requires `ALLOW_SQLITE_RUNTIME=1`
- [ ] Confirm no collector run uses `DB_PATH` when Postgres is available

### Current Assignment-Flow Status

The pending winner assignment public transaction flow in `server/company_db.py` is now Postgres-guarded in the current checkout.

Current code-state split:

- Postgres-backed / guarded `company_pending` paths exist for list/get, queue, product assignment, item removal, item reservation, lot-number updates, status updates, confirmation, undo, delete, payment approval, and lot-item sync.
- AST guard coverage now includes high-priority public company functions across sessions, products, pending assignments, sale orders, purchase orders, bargain sessions, and inventory-facing transaction helpers. The pending/payment subset includes:
  - `delete_pending_winner_assignment`
  - `update_pending_winner_assignment_status`
  - `confirm_pending_winner_assignment`
  - `approve_payments_from_picklist_lots`
  - `undo_confirm_pending_winner_assignment`
- Private SQLite helper residue remains in assignment-adjacent compatibility helpers, including `_sync_linked_sale_orders_for_assignment`, `_restore_assignment_financials_txn`, `_reopen_linked_sale_orders_for_assignment_txn`, and `_recalc_sale_order`.
- The remaining assignment work is validation and archive classification for linked sale orders, sale order lines, auction results, lot items, inventory application/reversal, and session/order recalculation effects.

Reference:
- [main_runtime_complete.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/main_runtime_complete.md)

## Deferred Tracks

These tracks are deferred from core runtime completion, but they still matter for SQLite retirement. Before sign-off, verify each deferred path either uses Postgres natively or is explicitly outside runtime scope.

### Analytics Track
Status: `Deferred`

Remaining endpoints:
- `/api/facts/lots`
- `/api/facts/buyers`
- `/api/facts/products`
- `/api/intelligence/live`
- `/api/analytics/chat_signals`
- `/api/analytics/timing`
- `/api/analytics/products_intel`
- `/api/users/cross_stream`
- `/api/users/audience`
- `/api/users/profile`
- `/api/users/target_buyers`
- `/api/product_profit`

### Competitor / Shop Track
Status: `Deferred`

Remaining endpoints:
- `/api/competitors/title_quality`
- `/api/competitors/detection_feed`
- `/api/analytics/shop_products`
- `/api/analytics/shop_scrape_status`
- `/api/analytics/scrape_shop`

### TikTok Track
Status: `Deferred`

Remaining endpoints:
- `/api/tiktok_extractor/lot_state`
- `/api/tiktok_operator/config`
- `/api/tiktok_shop_orders/create`
- `/api/tiktok_live_orders/create`
- `/api/tiktok_shop_orders/import_csv`
- `/api/tiktok_live_picklist`

### Export / Report Track
Status: `Deferred`

Remaining endpoints:
- `/api/export/auction_results.csv`
- `/api/export/orders.csv`
- `/api/export/reports.csv`
- `/api/export/users.csv`

### Auth / Admin Track
Status: `Deferred`

Remaining endpoints / areas:
- auth config / me / lookup / sessions / users
- auth login / logout / password / MFA
- employee login admin routes
- upload cookies
- review sync
- Odoo sync
- low-frequency admin ops

## Suggested Order If We Resume Migration

The migration is already resumed in Postgres-only mode. Use this order for remaining SQLite blocker removal:

1. Validate the pending winner assignment linked sale-order, inventory, auction-result, lot-item, and session/order recalculation effects under Postgres-only runtime.
2. Confirm company transaction tables: `sale_orders`, `sale_order_lines`, `buyer_groups`, `pick_lists`, and `pick_list_items`.
3. Classify private company SQLite helper residue as archive-only or remove it.
4. Confirm event/ingest blockers: manual SQLite compatibility functions and collector DB fallback behavior.
5. Confirm analytics/shop blockers: rebuildable SQLite-derived tables and shop scraper bootstrap paths.
6. Confirm broad deferred domains: export/report, TikTok, auth/admin, integrations, and any direct SQLite reads or helpers that still require `ALLOW_SQLITE_RUNTIME=1`.

## Concrete Remaining SQLite Blockers

- `server/company_db.py`
  - no `_connect()` or `_sqlite_*` public runtime helpers were present in the current AST check
  - pending winner assignment status/confirm/undo/delete/payment-approval public functions are covered by the no-SQLite-helper AST guard
  - private SQLite helper residue remains around assignment financial restore, linked sale-order sync, in-house/order totals, purchase-order totals, and legacy recalculation helpers
  - sale order / inventory movement compatibility helpers still need final archive-only classification or removal
- `server/events_db.py`
  - `db_path` and manual compatibility entrypoints now fail closed with `events_db_sqlite_runtime_retired`
  - no direct `sqlite3` import/connect remains in the module
  - remaining `sqlite_*` variable names are compatibility payload labels, not active SQLite connections
- `src/collector/db.py`
  - `connect(None)` now requires `postgres_mode=True`; otherwise it raises `collector_postgres_runtime_required`
  - explicit DB paths raise `collector_sqlite_runtime_retired`
  - no direct `sqlite3` import/connect remains in live collector code
- `server/shop_scraper.py`
  - public runtime rejects `db_path` and no `_sqlite_get_shop_products` helper remains
- `server/analytics.py` and `server/reconciler.py`
  - SQLite runtime paths are retired by default but still present as guarded compatibility paths
- `server/postgres_sidecar.py` and `server/sidecar_runner.py`
  - sidecar runtime is retired and raises `sqlite_sidecar_retired`
- Legacy scripts and tools
  - repo-wide AST scan now reports no `sqlite3` imports or `sqlite3.connect` calls outside ignored environments
  - root SQLite scripts fail closed, and tools that still matter have been moved to Postgres or retired
- Broad API/domain areas
  - export/report, TikTok, auth/admin, integrations, and low-frequency admin paths still need final pass/fail classification as Postgres-native, guarded archive-only, or removed

## Validation Commands

Run these from the repository root.

Postgres-only validation:

```bash
python3 -m server.company_cutover_verify
python3 -m server.ingest_streams_verify
python3 -m server.ingest_events_verify
python3 -m server.ingest_failed_verify
python3 -m server.ingest_users_verify
python3 -m server.ingest_lots_verify
python3 -m server.ingest_stream_merge_verify
tail -n 100 data/postgres_cutover_mismatches.jsonl
```

Manual SQLite comparison, only when deliberately validating an archive or rollback source:

```bash
ALLOW_SQLITE_RUNTIME=1 python3 -m server.company_cutover_verify
```

Fast sanity check after backend/test inventory edits:

```bash
python3 -m compileall server src/collector app/tests
git diff --check -- docs/migration_progress_tracker.md docs/postgres_primary_cutover_plan.md docs/backend_database_runtime.md
```

## Session Notes

Use this section for short updates.

### Latest

- Latest guard pass found high-priority company public functions covered by a no-SQLite-helper AST guard; pending winner assignment status/confirm/undo/delete/payment-approval public functions are part of that coverage, and remaining assignment-adjacent SQLite residue is private helper compatibility code
- Validation commands are narrowed to the current verifier set plus `git diff --check` on the two owned docs for this pass
- Broad domains still need final classification: export/report, TikTok, auth/admin, integrations, and low-frequency admin flows
- Standalone inventory verifier is retired from the normal validation command set
- Worker 6 docs/config pass updated the tracker for resumed Postgres-only cutover state
- Remaining SQLite blockers are now listed as concrete guarded runtime/helper surfaces
- Validation commands now use the current cutover verifier modules instead of retired sidecar verifier modules
- Main runtime declared complete
- Remaining bridge-backed surface is deferred only
- Current mode is stabilization, not broad migration
- `/api/analytics/trends` and `/api/analytics/businesses` migrated natively
- Runtime diagnostics now include request, bridge, and task summaries
