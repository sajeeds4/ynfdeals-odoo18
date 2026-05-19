# Main Runtime Complete

This milestone means the main operational runtime is now centered on:

- `FastAPI` as the primary public runtime
- `Redis` for runtime observability, locks, cache/state, and Celery coordination
- `Celery` for real background work
- `Postgres` as the primary operational data path for the main runtime

It also means the compatibility bridge is no longer on the core operational path.

## In Scope For Completion

The following runtime surface is now native enough to treat the main runtime as complete:

- core live read paths
- core live runtime mutation paths
- core admin/business read paths
- safe admin/business mutation paths
- non-bulk sale-order and auction-result mutation paths
- inventory product update/delete
- high-value analytics endpoints:
  - `/api/analytics/overview`
  - `/api/analytics/market_pulse`
  - `/api/company/intelligence`
  - `/api/alerts`
  - `/api/alerts/settings`
  - `/api/analytics/trends`
  - `/api/analytics/businesses`
- high-value competitor/shop subset:
  - `/api/spectator/listings`
  - `/api/analytics/competitor_prices`

## Deferred Bridge-Backed Tracks

The following legacy surface is intentionally deferred and does not block declaring the main runtime complete.

### Analytics

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

### Competitor / Shop

- `/api/competitors/title_quality`
- `/api/competitors/detection_feed`
- `/api/analytics/shop_products`
- `/api/analytics/shop_scrape_status`
- `/api/analytics/scrape_shop`

### TikTok

- `/api/tiktok_extractor/lot_state`
- `/api/tiktok_operator/config`
- `/api/tiktok_shop_orders/create`
- `/api/tiktok_live_orders/create`
- `/api/tiktok_shop_orders/import_csv`
- `/api/tiktok_live_picklist`

### Export / Report

- `/api/export/auction_results.csv`
- `/api/export/orders.csv`
- `/api/export/reports.csv`
- `/api/export/users.csv`

### Low-Frequency Admin / Ops

- auth/admin legacy endpoints still not ported
- employee login admin endpoints
- `/api/upload_cookies`
- `/api/customers/reviews/sync`
- `/api/company/sync_from_odoo`
- sidecar/reporting ops endpoints
- picklist/internal POS/in-house ops endpoints
- OBS/demo/support endpoints not required for the main runtime declaration

## Stabilization Checklist

Use this after the main runtime completion milestone. This is a stabilization checklist, not a migration checklist.

### FastAPI Runtime Health

- [ ] `/healthz` returns `200`
- [ ] `/api/v2/health` returns `200`
- [ ] native compatibility routes respond without falling through to the bridge for core runtime traffic
- [ ] no unexpected `5xx` growth on live operational endpoints
- [ ] startup and shutdown are clean

### Redis Usage / Metrics

- [ ] Redis ping is healthy in runtime diagnostics
- [ ] request metrics are being recorded
- [ ] bridge-hit metrics are being recorded
- [ ] runtime state snapshots are updating
- [ ] short-TTL cache reads are present for expensive core analytics endpoints
- [ ] Redis failures do not break request handling or task execution

### Celery Queue / Worker Health

- [ ] worker inspection is healthy in runtime diagnostics
- [ ] queue depths are visible
- [ ] default queue is healthy
- [ ] analytics queue is healthy
- [ ] ingest/support queue is healthy
- [ ] tracked task state is updating
- [ ] task metrics are updating for `completed`, `failed`, `skipped`, and `fallback`
- [ ] lock-based task execution is not causing stuck or duplicate work

### Bridge-Hit Monitoring

- [ ] bridge-hit metrics exist in diagnostics
- [ ] bridge hits are not occurring on core runtime endpoints
- [ ] any remaining bridge hits map only to explicitly deferred tracks
- [ ] no unexpected bridge growth appears during normal live operations

### Request Latency / Error Monitoring

- [ ] request metrics show healthy response times for core routes
- [ ] no recurring high-latency spikes on analytics overview, market pulse, company intelligence, alerts, spectator listings, or competitor prices
- [ ] no recurring `5xx` errors on core runtime endpoints
- [ ] no evidence of retry loops or fallback thrash

## Declaration Rule

We can continue to say the main runtime is complete as long as:

- the core operational path remains native
- the bridge is only serving explicitly deferred tracks
- FastAPI, Redis, and Celery remain healthy in runtime diagnostics
- stabilization checks stay green under real usage

## Out Of Scope

Do not widen into these unless chosen intentionally:

- deferred analytics
- deferred competitor/shop
- TikTok
- export/report endpoints
- low-frequency admin operations
