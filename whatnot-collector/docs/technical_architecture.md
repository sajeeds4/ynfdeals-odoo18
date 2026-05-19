# Technical Architecture Guide

## Purpose Of This Document
This document explains how the project is implemented at a technical level.

Use this file when you need to understand:

- runtime boundaries
- how data flows from Whatnot into the local app
- how the backend is structured
- which tables hold what
- where to debug specific failures
- which parts are safe to change and which are risky

This is the companion to:
- [intern_handbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/intern_handbook.md)

The intern handbook explains the product and workflows.
This file explains the implementation.

## System Topology
At runtime, the system is made of 3 active layers and 1 data layer.

### Layer 1: Collector
Path:
- [src/collector](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector)

Technology:
- Python
- Playwright

Role:
- open Whatnot pages
- observe the live DOM
- parse visible stream information
- emit raw event records into SQLite

### Layer 2: API / Business Logic
Path:
- [server](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server)

Technology:
- Python
- local HTTP server
- SQLite

Role:
- expose HTTP endpoints to the dashboard
- manage live-company session state
- convert raw events into business objects
- own workflows like:
  - inventory save/update
  - winner assignment
  - auction result deduping
  - sale order generation
  - diagnostics

### Layer 3: Dashboard
Path:
- [dashboard-vite](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite)

Technology:
- React
- Vite
- local browser storage

Role:
- multi-device operator UI
- polling-driven dashboard
- barcode workflow UI
- company management UI

### Layer 4: Data
Main DB:
- [whatnot.db](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/data/whatnot.db)

Runtime/support data:
- [whatnot-collector/data](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/data)

This layer stores:
- products
- sessions
- lots
- winner tickets
- raw collector events
- state JSON files
- logs
- backups

## Runtime Modes
The codebase has two collector families.

### Live Collector
Managed by:
- [server/collector_manager.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/collector_manager.py)

Purpose:
- collect data for the company’s own livestream
- bind that collector process to a company session

Important behavior:
- starting the live collector usually creates or refreshes a local `company_session`
- the process state is persisted in `collector_state.json`

### Spectator Collector
Also managed by:
- [server/collector_manager.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/collector_manager.py)

Purpose:
- monitor competitor streams
- usually multitab
- separate from the company live workflow

Important behavior:
- spectator state is separate from live collector state
- should not be confused with the company session flow

## Main Entry Points

### Collector Entry
- [src/collector/main.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/main.py)

This file:
- loads cookies
- launches Playwright
- opens Whatnot pages
- scrapes lot, winner, price, bidder, and viewer information
- inserts raw events into the event database

Key technical details visible in the file:
- price extraction helpers
- lot-number extraction helpers
- banner winner parsing
- sold-price parsing
- text sanitization

### API Entry
- [server/api.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/api.py)

This is the central backend file.

It contains:
- API routes
- ingestion helpers
- diagnostics endpoints
- inventory endpoints
- session endpoints
- winner-assignment endpoints
- auth endpoints
- system maintenance endpoints

### Frontend Entry
- [dashboard-vite/src/App.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/App.jsx)

This file:
- defines top-level routes
- manages auth bootstrap
- handles top navigation
- manages theme and local nav visibility
- switches between TV, Operator, Session, and Company areas

## Configuration Model
All configuration is centralized in:
- [server/config.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/config.py)

### Important settings

#### Server
- `HOST`
- `PORT`

#### Database
- `DB_PATH`

#### Collector
- `COLLECTOR_PYTHON`
- `COLLECTOR_SRC_PATH`
- `COLLECTOR_HEADLESS`
- `COLLECTOR_POLL_INTERVAL_MS`
- `COLLECTOR_COOKIES_PATH`
- `VIEWER_COUNT_SELECTOR`

#### State files
- `SHARED_SCAN_STATE_PATH`
- `COLLECTOR_STATE_PATH`
- `SPECTATOR_STATE_PATH`
- `PRIORITY_SPECTATOR_STATE_PATH`

#### Auth
- `DASHBOARD_AUTH_REQUIRED`
- `DASHBOARD_SESSION_COOKIE`
- `DASHBOARD_SESSION_TTL_SEC`
- `DASHBOARD_SESSION_IDLE_TTL_SEC`
- `DASHBOARD_CSRF_HEADER`
- `DASHBOARD_AUTH_USERS_PATH`

### Design note
This module loads `.env` directly and resolves paths relative to project root. That keeps the deployment local and portable.

## State Management

### File-based state
Managed in:
- [server/state.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/state.py)

This file manages JSON state files for:
- shared scan state
- live collector state
- spectator state
- priority spectator state

Important technical detail:
- shared scan state writes are guarded with a process lock and temporary-file replacement to reduce partial write corruption

### Browser state
Frontend uses:
- `localStorage`
- `sessionStorage`

Used for:
- theme
- selected tabs
- inventory filters
- winner scanner preferences
- current tab working state

Important:
- browser state improves UX
- browser state must not become business truth

## Authentication Architecture
Implemented in:
- [server/auth.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/auth.py)

### Features
- server-side sessions
- CSRF token issuance
- password hashing with Argon2 or scrypt compatibility
- optional TOTP / MFA
- lockout windows
- audit log
- persisted auth session store

### Important files produced
- `auth_audit.log`
- `auth_sessions.json`
- `auth_users.json`

### Technical note
Auth sessions are persisted, not purely in-memory. That matters for restart behavior.

## Collector Event Model
The collector emits raw stream events into SQLite.

Examples of raw event types:
- `lot_update`
- `auction_winner`
- `auction_state`
- `chat_message`
- `bid_update`
- `live_viewers`

The raw event query layer lives in:
- [server/events_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/events_db.py)

### What `events_db.py` does
- query raw stream events
- normalize usernames
- parse prices
- reconstruct sold-lot history
- maintain OCR/caption support tables
- compute audience and buyer insights
- infer or improve result quality when raw winner data is incomplete

### Why this layer matters
The raw stream is noisy. This layer is the first place where the app tries to make sense of that noise before the higher business workflows take over.

## Business Data Model
The main operational schema is managed in:
- [server/company_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/company_db.py)

Below are the most important entities.

### company_sessions
Purpose:
- represent a Whatnot show or selling session

Key ideas:
- status lifecycle like `draft`, `live`, `ended`
- aggregate totals for revenue, profit, and sold items

Used by:
- session overview
- session monitor
- company reporting

### company_lots
Purpose:
- represent local working lots inside a session

Key ideas:
- current lot context for operator workflow
- may not always match Whatnot lot identity perfectly if ingestion is weak

Used by:
- Operator
- current lot products
- release flow

### products
Purpose:
- inventory catalog and product metadata

Important fields:
- barcode
- SKU
- category
- brand
- gender
- cost
- retail price
- on-hand quantity
- notes
- description
- script
- note_top / note_mid / note_base
- media URL
- dupe/inspiration fields

### company_lot_items
Purpose:
- connect products to working lots

Used by:
- Operator candidate tray
- current lot display
- released/dropped item logic

### pending_winner_assignments
Purpose:
- queue of winner tickets awaiting product assignment or confirmation

Important statuses:
- `pending`
- `assigned`
- `confirmed`
- `needs_review`

Used by:
- Winner Scanner
- diagnostics
- auction result sync

### pending_winner_assignment_items
Purpose:
- allow one winner ticket to contain one or more scanned products

Used by:
- multi-product lot assignment
- pre-confirm delete/remove workflow

### auction_results
Purpose:
- session-facing sold-lot ledger

Important note:
- this table has historically been vulnerable to same-lot provisional duplicates
- confirmed winner-assignment truth should override weaker raw duplicates

### sale_orders / sale_order_lines
Purpose:
- commercial order representation after live sales

Used by:
- sales orders tab
- fulfillment and reporting workflows

### buyer_groups
Purpose:
- group related lots and sales per buyer for downstream processing

### customers
Purpose:
- customer/contact storage

### pick_lists and related tables
Purpose:
- shipping / packing-slip matching workflows

## Data Flow: End To End

### Flow A: Stream To Winner Queue
1. live collector opens stream
2. collector writes raw events
3. API queries event DB
4. backend attempts to interpret winner signals
5. pending winner ticket is created

Key risk points:
- missing lot number
- provisional winner event
- duplicate same-lot winner event

### Flow B: Winner Queue To Confirmed Sale
1. Winner Scanner loads pending ticket
2. operator scans sold product barcode
3. backend resolves product
4. assignment item row is created
5. ticket becomes `assigned`
6. ticket becomes `confirmed`
7. auction results and related session views should reflect that confirmed truth

Key risk points:
- wrong scanned item
- duplicate same-lot raw results still visible
- race between scan and confirm

### Flow C: TV Display
1. TV Scanner scans product
2. demo/live tray is updated
3. TV Display renders active product plus queued tiles

Important:
- presentation-only
- not a sales-truth path

### Flow D: Inventory Editing
1. Inventory UI edits a product
2. frontend posts to inventory update endpoint
3. backend updates product row
4. inventory response is read again
5. UI cache/browser state refreshes

Key risk points:
- missing field persistence in backend update path
- stale browser cache masking a successful save

## Frontend Structure

### Top-level routing
Defined in:
- [dashboard-vite/src/App.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/App.jsx)

Main routes:
- `/` -> TV Display
- `/operator`
- `/operator/tv-scanner`
- `/operator/winner-scanner`
- `/session`
- `/company`

Optional/hidden routes also exist for:
- spectator
- analytics
- competitors
- history
- dashboard
- users

Visibility is controlled by local state, not a server feature flag system.

### Operator area
Important file:
- [dashboard-vite/src/views/Operator.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Operator.jsx)

Key technical behavior:
- polls session stats frequently
- polls stream status
- polls current lot products
- captures barcode input globally in scan mode
- supports stream start/stop and lot actions

### Company area
Important file:
- [dashboard-vite/src/views/Company.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Company.jsx)

This acts like a sub-application with tabs for:
- overview
- sessions
- auction results
- orders
- inventory
- prep
- customers
- pick list
- AI intelligence
- graphs
- diagnostics
- settings

Technical note:
- several tabs are lazily or conditionally shown
- page state is often preserved to improve speed on a local network

## Diagnostics Architecture
Diagnostics UI:
- [dashboard-vite/src/views/company/Diagnostics.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Diagnostics.jsx)

Server support:
- [server/api.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/api.py)

What diagnostics aggregates:
- collector process state
- DB health
- failed ingests
- duplicate-lot warnings
- log tail data
- queue health
- recovery actions

This page is operationally important because it is the fastest place to answer:
- is the collector alive?
- are lots duplicating?
- are failed ingests building up?
- is the DB healthy?

## Failure Modes And Where To Debug Them

### Missing winner
Start with:
- collector log
- diagnostics
- raw `auction_winner` events
- `events_db.py` reconstruction logic
- `pending_winner_assignments`

### Duplicate lot in auction results
Start with:
- `pending_winner_assignments`
- `auction_results`
- dedupe logic in backend
- whether a weaker raw event re-created a same-lot row

### Notes saved but disappear
Start with:
- product row in DB
- inventory update endpoint
- inventory UI cache/session state

### Stream status looks stale
Start with:
- `collector_state.json`
- `load_collector_state()` and `save_collector_state()`
- live collector process status

### TV display looks wrong but sales are correct
Start with:
- TV tray state
- `LargeScreen.jsx`
- `TvScanner.jsx`
- demo tray vs live lot mode

## Performance Characteristics
This app is built for local network use.

That means it relies heavily on:
- short polling intervals
- browser-side storage
- warm local API access

Most important speed decisions in the current architecture:
- multiple pages poll independently
- cache and browser storage are used to reduce blank-state reloads
- some views preserve mounted state to feel more instant

Potential future performance improvements:
- WebSocket or SSE for live pages
- stronger request deduping
- smaller diagnostics and results payloads

## Deployment Assumptions
The project assumes:
- local network usage
- a machine capable of running Playwright
- local SQLite availability
- local file-system access for logs and backups

It is not structured like a cloud-native multi-service deployment. It is closer to a portable local operations appliance.

## Safe Change Zones

### Safer areas for new contributors
- docs
- company page layout
- diagnostics presentation
- inventory filters and UX
- non-critical styling
- local browser storage UX

### Risky areas
- collector parsing
- winner ingestion
- auction result deduping
- live collector restart logic
- inventory update persistence
- delete/archive behavior with foreign keys

## Technical Rules For Contributors

### Rule 1
Do not make the frontend the source of truth for business state.

### Rule 2
If a sale-integrity bug exists, inspect the backend and DB before patching the UI.

### Rule 3
If a Whatnot-derived field is noisy, do not trust it blindly. Prefer explicit barcode-confirmed truth.

### Rule 4
When changing live workflows, think in terms of:
- provisional signal
- confirmed assignment
- durable stored truth

### Rule 5
When touching destructive behavior, understand foreign-key relationships first.

## Recommended Technical Reading Order

1. [server/config.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/config.py)
2. [server/state.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/state.py)
3. [src/collector/main.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/main.py)
4. [server/events_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/events_db.py)
5. [server/company_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/company_db.py)
6. [server/api.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/api.py)
7. [dashboard-vite/src/App.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/App.jsx)
8. [dashboard-vite/src/views/Operator.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Operator.jsx)
9. [dashboard-vite/src/views/WinnerScanner.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/WinnerScanner.jsx)
10. [dashboard-vite/src/views/company/Diagnostics.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Diagnostics.jsx)

## Summary
The technical heart of the project is:

- Playwright collector for raw stream events
- Python API/business layer for truth-making and workflow safety
- React dashboard for multi-device operations
- SQLite-backed persistence with extensive backups and runtime state files

If you understand how raw events become confirmed winner-scanner sales, you understand the most important technical backbone of the system.
