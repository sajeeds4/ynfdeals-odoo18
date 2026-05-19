# Postgres Primary Cutover Plan

This document maps historical SQLite write surfaces, remaining guarded SQLite blockers, the validation rules for PostgreSQL-primary operation, and how to retire SQLite after PostgreSQL becomes stable.

The original operating model was:

- SQLite was the live source of truth
- PostgreSQL was a complete sidecar mirror
- Redis was intentionally limited to hot/cache/live-state data only

Current resumed state:

- PostgreSQL is the expected primary runtime for configured domains.
- SQLite runtime access is disabled by default through `ALLOW_SQLITE_RUNTIME=0`.
- collector SQLite fallback is disabled by default through `COLLECTOR_SQLITE_FALLBACK_ENABLED=0`.
- dual-write / reverse-shadow flags default off.
- write validation and events read validation remain enabled.
- sidecar commands and the standalone inventory verifier are retired from the normal validation loop; use the current validation commands listed below.

The remaining migration work is not domain promotion from scratch. It is validating Postgres-only operation, proving that guarded SQLite helpers are outside the normal runtime path, and removing or archiving the final SQLite dependency points. The current `server/company_db.py` focus is assignment-flow validation plus private SQLite helper residue around linked sale-order sync, financial restore, and recalculation compatibility paths.

## Resume Snapshot

Use this snapshot when picking up the cutover:

- `.env.example` sets every `DB_PRIMARY_DOMAIN_*` flag to `postgres`.
- `EVENTS_DB_READ_BACKEND=postgres`.
- `EVENTS_DB_VALIDATE_READS=1`.
- `ALLOW_SQLITE_RUNTIME=0`.
- `COLLECTOR_SQLITE_FALLBACK_ENABLED=0`.
- `DB_DUAL_WRITE_*` is explicitly off.
- `DB_VALIDATE_WRITE_*` is explicitly on.
- `server.inventory_cutover_verify` is no longer part of the standard validation command set.

Do not restart from Wave 1 unless a rollback decision explicitly changes these flags.

## Current Write Surface

This section is retained as historical context for where SQLite writes originally lived. In the resumed state, treat these as blocker inventory and verify each path is Postgres-native, guarded, or archive-only.

### Current assignment-flow detail

The assignment surface is Postgres-guarded for the current public runtime. Current Postgres-backed `company_pending` paths include list/get, queue, product assignment, item removal, item reservation, lot-number updates, status updates, confirmation, undo, delete, payment approval, and lot-item sync.

The no-SQLite-helper AST guard covers:

- `delete_pending_winner_assignment`
- `update_pending_winner_assignment_status`
- `confirm_pending_winner_assignment`
- `approve_payments_from_picklist_lots`
- `undo_confirm_pending_winner_assignment`

Private SQLite helper residue still exists in assignment-adjacent compatibility helpers, including `_sync_linked_sale_orders_for_assignment`, `_restore_assignment_financials_txn`, `_reopen_linked_sale_orders_for_assignment_txn`, and `_recalc_sale_order`. These helpers should be treated as archive-only candidates unless a later audit proves an active runtime caller.

The current cutover gate is validation of the Postgres assignment effects across `pending_winner_assignments`, `pending_winner_assignment_items`, `auction_results`, `company_lots`, `company_lot_items`, `sale_orders`, `sale_order_lines`, inventory application/reversal, buyer/session totals, and payment-review cancellation/approval state.

### 1. Core company and operations writes

The largest operational write surface currently lives in [company_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/company_db.py).

These writes originally hit SQLite:

- `app_settings`
- `customer_reviews`
- `employee_accounts`
- `employee_pos_tokens`
- `in_house_sales`
- `in_house_orders`
- `in_house_order_lines`
- `products`
- `product_categories`
- `inventory_movements`
- `inventory_audit_log`
- `customers`
- `company_sessions`
- `company_lots`
- `company_lot_items`
- `pending_winner_assignments`
- `pending_winner_assignment_items`
- `auction_results`
- `buyer_groups`
- `sale_orders`
- `sale_order_lines`
- `pick_lists`
- `pick_list_items`

These writes include:

- inserts for new sessions, lots, products, orders, reviews, and employee data
- updates for status transitions, lot-number corrections, financial recalculations, and inventory deltas
- deletes for session-tree cleanup and winner/lot cleanup

### 2. Event and ingestion writes

The live ingest surface currently lives in [events_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/events_db.py).

These writes originally hit SQLite:

- `streams`
- `events`
- `lots`
- `users`
- `resolved_lot_products`
- `failed_ingests`
- `stream_ocr_frames`
- `stream_caption_windows`

These are high-volume and append-heavy. They are the riskiest part of the migration.

### 3. Derived analytics and intelligence writes

The reconciliation and analytics refresh surface currently lives in [reconciler.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/reconciler.py) and [shop_scraper.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/shop_scraper.py).

These writes originally hit SQLite:

- `fact_buyers`
- `fact_buyer_streams`
- `fact_lots`
- `fact_products`
- `stream_health`
- `intelligence_signals`
- `competitor_shop_products`

These tables are derived or rebuildable. They should move later than the transactional business tables.

### 4. Direct API-side SQLite writes

There are still a few direct SQLite writes in [api.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/api.py) that bypass the `company_db` and `events_db` module boundaries.

Important examples:

- TikTok operator stream bootstrap inserts into `streams`
- Odoo sync/import flows insert directly into local company tables
- some dedupe and migration helpers open `sqlite3.connect(DB_PATH)` directly

Before PostgreSQL becomes primary for those domains, these direct writes should be pulled behind shared module APIs.

### 5. Auth is not in SQLite

Authentication is currently file-backed in [auth.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/auth.py), not in SQLite:

- `auth_users.json`
- session store
- auth audit log

This should be treated as a separate migration later if we decide to move auth/session persistence into PostgreSQL or Redis.

## Recommended Promotion Order

Historical note: the wave plan below explains how the cutover was staged. The active work now is Postgres-only validation and SQLite blocker retirement.

The safest approach is to move the low-risk, low-throughput, well-bounded domains first.

### Wave 1. Lowest-risk business domains

Switch first:

- `app_settings`
- `customer_reviews`
- `employee_accounts`
- `employee_pos_tokens`
- `in_house_sales`
- `in_house_orders`
- `in_house_order_lines`

Why:

- low write volume
- small relational surface
- minimal live-stream coupling
- easy to validate by row and by summary

This wave gives us real production experience with PostgreSQL-primary writes without putting live auction flows at risk.

### Wave 2. Inventory domain

Switch next:

- `products`
- `product_categories`
- `inventory_movements`
- `inventory_audit_log`

Why:

- high business value
- moderate complexity
- mostly synchronous app-driven writes
- validation is possible through product quantities, movement totals, and audit logs

This wave matters because inventory is central to Whatnot, TikTok Live, TikTok Shop, and internal employee sales.

Current rollout note:

- `products` can move to Postgres primary first
- `inventory_audit_log` can move alongside product writes
- `inventory_movements` should remain dual-write and validation-ready until the company transactional core moves off SQLite, because stock movements still happen inside SQLite-owned winner-assignment and auction confirmation transactions
- inside Wave 3, the safest first slice is now proven for:
  - `customers`
  - `company_sessions`
  - `company_lots`
- `pending_winner_assignments`
- `pending_winner_assignment_items`
- `auction_results`
- those slices now run with:
  - true `Postgres primary + SQLite reverse shadow` for pure pending-assignment writes
  - true `Postgres primary + SQLite reverse shadow` for direct `auction_results` create/update writes
  - SQLite-owned mirrored transitions for confirm / payment-review style flows that still touch non-promoted `sale_orders` and inventory movement logic
- `company_lots` validation currently covers:
  - lots per session parity
  - recent lot create/update/delete parity
  - sequence/order integrity within a session
  - linked session consistency
- `company_pending` validation currently covers:
  - assignment row parity
  - assignment item parity
  - orphan item consistency
  - linked session consistency
  - linked lot consistency
- `company_results` validation currently covers:
  - count parity by session and lot
  - revenue / cost / profit totals by session
  - winner username parity
  - linked customer / session / lot consistency
  - duplicate `source_event_id` protection
  - recent result create / update / delete parity
- next up, and intentionally not yet promoted, are:
  - `sale_orders`
  - `inventory_movements`

### Wave 3. Core company transaction domain

Switch after inventory stabilizes:

- `customers`
- `company_sessions`
- `company_lots`
- `company_lot_items`
- `pending_winner_assignments`
- `pending_winner_assignment_items`
- `auction_results`
- `buyer_groups`
- `sale_orders`
- `sale_order_lines`
- `pick_lists`
- `pick_list_items`

Why:

- this is the operational heart of the app
- a mistake here would affect sessions, winner scanning, profit calculations, inventory, pick lists, and customer history
- this wave needs the strongest validation and rollback plan

### Wave 4. Event ingest domain

Switch only after the transactional domain is stable:

- `streams`
- `events`
- `lots`
- `users`
- `stream_ocr_frames`
- `stream_caption_windows`
- `failed_ingests`
- `resolved_lot_products`

Why:

- highest write volume
- live collector risk
- collector reliability is more important than elegance during migration

### Wave 5. Derived analytics and competitor pipelines

Switch last:

- `fact_buyers`
- `fact_buyer_streams`
- `fact_lots`
- `fact_products`
- `stream_health`
- `intelligence_signals`
- `competitor_listings`
- `competitor_shop_products`

Why:

- derived data can be rebuilt
- these are good candidates for PostgreSQL-primary worker jobs
- they do not need to lead the cutover

## Primary and Dual-Write Strategy

### Key rule

Do not cut over by database file. Cut over by domain.

That is why the runtime now has domain-specific control flags in [config.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/config.py):

- `DB_PRIMARY_DOMAIN_SETTINGS`
- `DB_PRIMARY_DOMAIN_REVIEWS`
- `DB_PRIMARY_DOMAIN_EMPLOYEES`
- `DB_PRIMARY_DOMAIN_IN_HOUSE`
- `DB_PRIMARY_DOMAIN_INVENTORY`
- `DB_PRIMARY_DOMAIN_COMPANY`
- `DB_PRIMARY_DOMAIN_EVENTS`
- `DB_PRIMARY_DOMAIN_ANALYTICS`

And companion flags:

- `DB_DUAL_WRITE_*`
- `DB_VALIDATE_WRITE_*`

### Historical domain promotion stages

These stages describe how the cutover was designed and remain useful for rollback reasoning. They are not the default runtime posture in the current resumed state.

#### Stage A. Mirror only

- SQLite remained primary for writes
- PostgreSQL mirror was continuously refreshed
- parity reports must stay clean

#### Stage B. Dual-write with SQLite primary

- app wrote SQLite first
- same operation was also written to PostgreSQL
- mismatches are logged

This stage is useful if we need confidence in the PostgreSQL write path before trusting it as primary.

#### Stage C. Dual-write with PostgreSQL primary

- app writes PostgreSQL first
- SQLite becomes a shadow writer
- read-after-write validation compares key fields

At this point PostgreSQL is operationally primary, but SQLite still protects rollback.

#### Stage D. PostgreSQL primary, SQLite read-only shadow

- app reads and writes PostgreSQL
- SQLite is no longer written for that domain
- SQLite snapshot retained for rollback and historical verification

## Validation Rules During Cutover

### 1. Row parity

The retired sidecar verifier and standalone inventory verifier are no longer the primary checks. Use the current domain/runtime verifier modules.

Use:

```bash
python3 -m server.company_cutover_verify
python3 -m server.ingest_streams_verify
python3 -m server.ingest_events_verify
python3 -m server.ingest_failed_verify
python3 -m server.ingest_users_verify
python3 -m server.ingest_lots_verify
python3 -m server.ingest_stream_merge_verify
```

### 2. Aggregate parity

For each promoted domain, add business checks beyond row counts.

Examples:

- settings:
  - key/value equality for all active settings
- reviews:
  - total count
  - matched count
  - replied count
- employees/in-house:
  - total employee count
  - pending order count
  - approved value
  - in-house sales count and subtotal
- inventory:
  - product count
  - total stock value
  - low stock count
  - movement totals by product
- company transactions:
  - session count
  - auction result count
  - order count
  - revenue
  - profit
  - pending winners count

### 3. Read-after-write validation

For each write in a promoted domain:

- write primary target
- write secondary shadow target if dual-write enabled
- fetch resulting record from both stores
- compare:
  - id
  - status
  - timestamps if deterministic enough
  - critical business fields

If validation fails:

- log mismatch with payload and identifiers
- mark domain health degraded
- do not silently ignore it

### 4. Mismatch logging

We should keep a structured mismatch log for cutover work.

Recommended fields:

- `domain`
- `operation`
- `entity_type`
- `entity_id`
- `primary_backend`
- `secondary_backend`
- `request_payload_hash`
- `primary_result`
- `secondary_result`
- `created_at`

This can start as a file log and later become a dedicated Postgres table.

## SQLite Retirement Plan

SQLite should be retired only after PostgreSQL has already been primary and stable per domain.

### Phase 1. PostgreSQL-primary by domain

- promote a domain to PostgreSQL primary
- keep SQLite dual-write enabled for that domain
- keep parity and aggregate checks running

### Phase 2. PostgreSQL-primary reads

- move reads for that domain to PostgreSQL
- keep SQLite shadow writes for rollback confidence

### Phase 3. Freeze SQLite writes

- turn off SQLite shadow writes for the stable domain
- leave SQLite snapshot in place as read-only historical rollback source

### Phase 4. Final SQLite archive

After all domains are stable:

- stop all runtime dependence on SQLite
- archive final SQLite DB snapshot
- keep export and restore procedures documented

## Recommended Immediate Next Step

The best next engineering step in the resumed Postgres-only cutover is:

1. run the current cutover verifier modules against the live Postgres runtime
2. inspect `data/postgres_cutover_mismatches.jsonl` for new mismatch growth
3. confirm production processes do not set `ALLOW_SQLITE_RUNTIME=1`
4. confirm collector starts with no SQLite DB path when Postgres is available
5. validate linked sale-order, inventory, auction-result, lot-item, buyer/session total, and payment-review effects for the Postgres assignment flows
6. classify private SQLite helper residue as archive-only or remove it after proving no runtime caller needs it
7. classify broad deferred domains as Postgres-native, guarded archive-only, or removed
8. convert remaining guarded SQLite helper surfaces into archive-only tooling or remove them after sign-off

Concrete blocker surfaces to clear before final SQLite archive:

- `server/company_db.py`: private assignment financial restore, linked sale-order sync, legacy recalculation helpers, inventory/order compatibility helpers, and any remaining SQLite helper residue not proven archive-only
- `server/events_db.py`: remaining compatibility payload labels and manual paths are fail-closed; no direct `sqlite3` import/connect remains
- `src/collector/db.py`: explicit DB paths are rejected and `connect(None)` requires confirmed Postgres mode
- `server/shop_scraper.py`: public runtime rejects `db_path`; no direct SQLite helper remains in the active shop product path
- `server/analytics.py` and `server/reconciler.py`: retired SQLite compatibility paths
- legacy root scripts/tools: direct SQLite scripts are retired or moved to Postgres; repo-wide AST guard should remain clean for `sqlite3` imports/connects
- broad deferred domains: export/report, TikTok, auth/admin, integrations, and low-frequency admin flows
- `server/postgres_sidecar.py` and `server/sidecar_runner.py`: retired sidecar entrypoints
