# Sidecar Mirror Guide

This project now supports a safe sidecar migration path:

- SQLite remains the live source of truth
- PostgreSQL is the full relational mirror
- Redis is the hot-state/cache/live-coordination mirror

Nothing in the live auction flow needs to change while the sidecars run.

## PostgreSQL Coverage

PostgreSQL mirrors the full SQLite database into:

- database: `whatnot_sidecar`
- schema: `sqlite_mirror`

This includes all SQLite tables currently present in the live DB, including:

- operational company tables
  - `company_sessions`
  - `company_lots`
  - `company_lot_items`
  - `pending_winner_assignments`
  - `pending_winner_assignment_items`
  - `auction_results`
  - `sale_orders`
  - `sale_order_lines`
  - `buyer_groups`
  - `customers`
  - `pick_lists`
  - `pick_list_items`
- inventory tables
  - `products`
  - `product_categories`
  - `inventory_movements`
  - `inventory_audit_log`
- employee/internal sales tables
  - `employee_accounts`
  - `employee_pos_tokens`
  - `in_house_sales`
  - `in_house_orders`
  - `in_house_order_lines`
- event and analytics tables
  - `events`
  - `lots`
  - `streams`
  - `users`
  - `stream_ocr_frames`
  - `stream_caption_windows`
  - `stream_health`
  - `fact_buyers`
  - `fact_buyer_streams`
  - `fact_lots`
  - `fact_products`
  - `intelligence_signals`
- competitor/shop intelligence tables
  - `competitor_listings`
  - `competitor_shop_products`
- review/settings/support tables
  - `customer_reviews`
  - `app_settings`
  - `failed_ingests`
  - and any additional SQLite user tables discovered during sync

## Redis Scope

Redis is intentionally **not** used as a second relational database.

Redis is limited to hot/cache/live-state data only:

- hot session state
  - `wnlive:sync:sessions:<account>`
  - `wnlive:sync:session:<session_id>`
- pending winners
  - `wnlive:sync:pending_winners:<session_id>`
- auction results
  - `wnlive:sync:auction_results:<session_id>`
- overview/dashboard summaries
  - `wnlive:sync:overview_summary`
- inventory summary cache
  - `wnlive:sync:inventory_summary`
- queue/job state
  - `wnlive:sync:job_state`
- locks / live coordination state
  - `wnlive:sync:locks_state`
  - `wnlive:sync:collector_state`
  - `wnlive:sync:shared_scan_state`

This keeps Redis fast, disposable, and operationally safe.

## Verification

### Quick parity report

Run:

```bash
cd whatnot-collector
.venv/bin/python -m server.sidecar_verify
```

This compares SQLite vs Postgres table counts for all mirrored tables.

### API parity report

Authenticated endpoint:

```text
/api/sidecar/parity_report
```

Optional subset:

```text
/api/sidecar/parity_report?table=products&table=sale_orders
```

### Postgres sync state

```sql
SELECT table_name, row_count, last_mode
FROM sqlite_mirror._mirror_sync_state
ORDER BY table_name;
```

## Safe rollout model

1. SQLite stays live
2. Postgres mirrors everything
3. Redis caches only hot state
4. Read-only endpoints can move first
5. Write paths stay on SQLite until explicitly migrated
