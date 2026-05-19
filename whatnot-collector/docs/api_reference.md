# API Reference

## Purpose
This document is a contributor-facing map of the local API.

It is not intended to list every single response field exhaustively. Instead, it explains:

- what endpoint groups exist
- what they are used for
- which pages depend on them
- which ones are operationally critical
- which ones are risky to change

Primary implementation:
- [server/api.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/api.py)

## Server Basics

### Base server
- local API served by `python -m server`
- typical base URL: `http://localhost:8088`

### Auth model
If dashboard auth is enabled:
- `GET /api/auth/config`
- `GET /api/auth/me`
- `POST /api/auth/login`
- `POST /api/auth/logout`

Important:
- mutating routes use CSRF protection when auth is enabled

## Endpoint Families

The API has grown into several functional groups:

1. auth and session bootstrap
2. live stream and collector control
3. operator live workflow
4. TV/OBS preview workflow
5. winner assignment workflow
6. company sessions and reporting
7. inventory and products
8. sale orders and customers
9. pick list / shipping tools
10. diagnostics and recovery
11. spectator / competitor monitoring
12. Odoo bridge helpers

## 1. Auth And Session Bootstrap

Used by:
- app startup
- login screen
- protected navigation

Common endpoints:
- `GET /api/auth/config`
- `GET /api/auth/me`
- `POST /api/auth/login`
- `POST /api/auth/logout`

Risk level:
- medium

Why:
- auth bugs can lock people out, but usually do not corrupt business data

## 2. Live Stream And Collector Control

Used by:
- main Operator page
- system control actions

Important endpoints:
- `GET /api/stream_status`
- `POST /api/stream_start`
- `POST /api/live_collector/start`
- `POST /api/live_collector/stop`

Related internals:
- `_handle_stream_start()`
- `live_collector_status()`
- `start_live_collector()`

What these do:
- start/stop the company live collector
- bind the collector to a company session
- expose running/stopped state

Risk level:
- very high

Why:
- wrong behavior here can break session continuity during a live stream

## 3. Operator Live Workflow

Used by:
- [Operator.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Operator.jsx)

Important endpoints:
- `GET /api/session_stats`
- `GET /api/current_lot/products`
- `POST /api/scan`
- `POST /api/lot/select`
- `POST /api/lot/remove`
- `POST /api/lot/release`
- `POST /api/lot/release/undo`
- `POST /api/lot/manual_number`

Related internals:
- `_handle_session_stats()`
- `_handle_lot_products()`
- `_handle_scan()`

What these do:
- manage the active working lot
- receive barcode scans
- show candidate tray state
- manage selected product in the current lot

Risk level:
- very high

Why:
- this is live workflow code
- mistakes here can confuse the lot currently being sold

## 4. TV / OBS Preview Workflow

Used by:
- [TvScanner.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/TvScanner.jsx)
- [LargeScreen.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/LargeScreen.jsx)

Important endpoints:
- `GET /api/obs/current`
- `POST /api/obs/demo_scan`
- `POST /api/obs/clear`

Related internals:
- `_handle_obs_current()`
- `_handle_obs_demo_scan()`
- `_get_demo_scan_tray()`
- `_append_demo_scan()`

What these do:
- support TV display rendering
- maintain preview tray / demo tray
- separate presentation flow from sale-truth flow

Risk level:
- low to medium

Why:
- these are important operationally but should not change sales truth

## 5. Winner Assignment Workflow

Used by:
- [WinnerScanner.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/WinnerScanner.jsx)

Important endpoints:
- `GET /api/winner_assignment/state`
- `POST /api/winner_assignment/scan`
- `POST /api/winner_assignment/confirm`
- `POST /api/winner_assignment/undo`
- `POST /api/winner_assignment/status`
- `POST /api/winner_assignment/remove_item`
- `POST /api/ingest_winner`

Related internals:
- `_handle_ingest_winner()`
- `_maybe_ingest_winner_event()`

What these do:
- create pending winner tickets
- scan sold products into tickets
- confirm assignments
- support undo and manual review flows

Risk level:
- highest

Why:
- this is where Whatnot winner data becomes sale truth
- duplicate handling and confirmation rules matter a lot

## 6. Company Sessions And Reporting

Used by:
- `Sessions`
- `Overview`
- `Auction Results`
- `Session Monitor`

Important endpoints commonly involved:
- `GET /api/company_sessions`
- `GET /api/session_report`
- `GET /api/auction_results`
- `GET /api/live_top_buyers`

Related internals:
- reporting helpers in `api.py`
- aggregation functions in `company_db.py`

What these do:
- list sessions
- summarize revenue/profit
- show sold lots
- surface session-level KPIs

Risk level:
- medium to high

Why:
- reporting changes can distort the business view even if live operations continue

## 7. Inventory And Products

Used by:
- [Inventory.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Inventory.jsx)

Important endpoints:
- `GET /api/inventory`
- `GET /api/inventory/categories`
- `POST /api/inventory/product/update`
- `POST /api/inventory/product/delete`
- `POST /api/inventory/bulk_update`
- `POST /api/inventory/bulk_archive`
- `POST /api/inventory/bulk_delete`
- `POST /api/inventory/export`

What these do:
- load inventory
- edit and bulk edit products
- archive/delete products
- export inventory

Risk level:
- high

Why:
- bad changes here can wipe metadata or harm historical references

## 8. Sale Orders And Customers

Used by:
- `Sales Orders`
- customer views

Important endpoints:
- `GET /api/sale_orders`
- `POST /api/sale_orders/update`
- `GET /api/customers`
- `POST /api/customers/update`

What these do:
- support post-stream order administration
- manage delivery status and customer information

Risk level:
- medium

## 9. Pick List / Shipping Tools

Used by:
- `Pick List`

Important endpoints:
- `POST /api/picklist/upload`
- `GET /api/picklists`
- `POST /api/picklist/delete`

Related internals:
- `_handle_picklist_upload()`

Risk level:
- medium

Why:
- mostly back-office, but mistakes can affect shipping prep

## 10. Diagnostics And Recovery

Used by:
- [Diagnostics.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Diagnostics.jsx)

Important endpoints:
- `GET /api/system/diagnostics`
- `GET /api/failed_ingests`
- `POST /api/failed_ingests/retry`
- `POST /api/failed_ingests/dismiss`
- `GET /api/collector/health`

What these do:
- expose health summaries
- expose log and DB health information
- provide some recovery actions

Risk level:
- low to medium

Why:
- helpful operational tooling, but less likely to create core sale corruption on its own

## 11. Spectator / Competitor Monitoring

Used by:
- spectator/competitor tools

Important endpoints:
- `GET /api/spectator/status`
- `POST /api/spectator/start`
- `POST /api/spectator/stop`
- `POST /api/priority_spectator/start`
- `POST /api/priority_spectator/stop`

What these do:
- manage competitor monitoring collectors

Risk level:
- medium

Why:
- separate from live selling, but can create noisy state or resource pressure

## 12. Odoo Bridge

Used by:
- some company/admin tooling

Relevant helpers in `api.py`:
- `odoo_search_read()`
- `odoo_call()`
- `odoo_write()`

Risk level:
- medium

Why:
- bridge logic can affect external business systems if used incorrectly

## Critical Internal Helpers In `api.py`

These are not endpoints, but they are very important:

### `_maybe_ingest_winner_event(...)`
Purpose:
- decide whether a raw winner event should become a company-side winner ticket or auction result

Why it matters:
- many duplicate and wrong-winner bugs are rooted here

### `_sync_live_lot_number(...)`
Purpose:
- keep local lot context aligned with Whatnot lot number

### `_process_event_side_effects(...)`
Purpose:
- apply business-side reactions when new raw events arrive

### `_dedupe_auction_result_rows(...)`
Purpose:
- suppress duplicate result rows when rendering/reporting

## How To Read The API Code

Recommended order:

1. helper functions at the top of `api.py`
2. stream/session resolution helpers
3. winner ingestion helpers
4. `do_GET`
5. `do_POST`
6. route-specific `_handle_*` helpers near the bottom

This file is large, so reading it endpoint-by-endpoint is better than trying to absorb everything at once.

## Change Risk By Endpoint Group

### Highest risk
- stream start/stop
- winner assignment
- ingest winner
- current lot scanning
- inventory destructive actions

### Medium risk
- reporting
- sale orders
- pick lists
- customers

### Lower risk
- diagnostics display
- non-mutating health endpoints
- TV preview endpoints

## API Design Notes

### The API is local-first
This app is designed for local network use, so the API favors:
- speed
- operational simplicity
- short polling intervals

### The API mixes raw and business data
Some endpoints expose:
- raw or near-raw live state

Others expose:
- cleaned business truth

Interns need to be careful not to confuse those two layers.

### Business truth should win over provisional signals
When conflicts appear:
- confirmed winner-scanner sale should beat provisional raw winner rows

That principle should guide future fixes.
