# Intern Handbook

## What This Project Is
This system is a local-network operations platform for running Whatnot livestream selling.

It is not just a scraper and it is not just a dashboard. It is a full live-selling stack that combines:

- a Playwright collector that watches Whatnot streams
- a local API server that turns raw events into usable business data
- a React dashboard used on multiple nearby devices
- inventory, sales, session, pick-list, and diagnostics tools

The project is optimized for a real selling environment where operators need fast feedback and low friction during a livestream.

## What Problem It Solves
During a live Whatnot show, the team needs to:

- detect lots and winners from the stream
- preview products on a TV display
- assign the correct sold product to the winning buyer
- update inventory safely
- review session outcomes later
- prepare shipping and sales records afterward

The project separates those responsibilities so the stream can stay operational even when Whatnot metadata is noisy.

## Core Product Philosophy
This system assumes:

- Whatnot is the source of truth for lot number, winner username, and sale price
- barcode scans are the source of truth for the actual product sold
- the TV display is presentation-only
- the winner scanner is sales-assignment-only
- confirmed winner-scanner rows are more trustworthy than raw provisional winner events

That separation is one of the most important ideas in the whole codebase.

## High-Level Architecture
There are 4 major layers:

1. Collector
- lives in `src/collector`
- opens Whatnot pages with Playwright
- captures raw events such as chat, lot updates, bids, viewers, and winners
- writes those events into SQLite

2. API Server
- lives in `server`
- exposes HTTP endpoints used by the dashboard
- stores and manages company sessions, inventory, winner assignments, sale orders, and diagnostics
- contains most of the business logic

3. Dashboard
- lives in `dashboard-vite`
- React/Vite frontend
- used from multiple devices:
  - TV display device
  - main operator device
  - winner scanner device
  - company/admin device

4. Local Data Stores
- SQLite files in `whatnot-collector/data`
- some persistent browser state in `localStorage` and `sessionStorage`
- optional Odoo source data for user/account context and related ops data

## Important Runtime Roles

### TV Display
Purpose:
- show products attractively during the stream

Rules:
- no sales truth
- no inventory deduction
- just presentation

Main pages:
- `TV Display`
- `TV Scanner`

### Main Operator
Purpose:
- manage live lots and current stream workflow

Rules:
- coordinates live session state
- sees current lot and stream health
- should not be overloaded with hidden background behavior

Main page:
- `Operator`

### Winner Scanner
Purpose:
- assign the sold barcode to the winner after Whatnot announces the result

Rules:
- use Whatnot only for:
  - lot number
  - winner username
  - price
- ignore noisy Whatnot product titles
- barcode scan is the actual product truth

Main page:
- `Winner Scanner`

### Company / Back Office
Purpose:
- inventory, auction results, sale orders, sessions, diagnostics, settings, pick lists

Main page:
- `ynfdeals` / `Company`

## Main User Flows

### 1. Live Stream Flow
Normal flow:

1. start live collector from Operator
2. stream starts generating raw Whatnot events
3. TV Scanner previews products for the audience
4. Whatnot emits winner data
5. Winner Scanner receives a pending winner ticket
6. operator scans the actual sold product
7. winner ticket is confirmed
8. session data and reporting update from that confirmed truth

### 2. TV Scanner Flow
TV Scanner exists for the streamer-facing visual presentation.

How it works:
- scan a product
- it goes into the TV tray
- the TV display shows the live product prominently
- queued products remain below
- the tray is capped, so old entries roll off automatically

Important:
- TV scans do not finalize a sale
- TV scans do not deduct inventory

### 3. Winner Scanner Flow
Winner Scanner exists for the assistant sitting next to the streamer.

How it works:
- Whatnot gives:
  - lot number
  - winner username
  - price
- the app creates a pending winner ticket
- assistant scans the sold product barcode
- product is assigned to that winner ticket
- ticket is confirmed
- confirmed row becomes the trusted sale record

Important:
- this is safer than trying to trust Whatnot’s product title
- it is also safer than scanning product before the winner is known

### 4. Inventory Flow
Inventory is the product source of truth for operations.

Used for:
- barcode lookup
- cost and retail
- notes and note layers
- gender
- image URLs
- dupe / inspiration data
- product status and stock

Important:
- historically linked products should not be blindly hard-deleted without understanding dependencies

### 5. Session / Results / Orders Flow
After or during the stream:

- `Sessions` shows live and historical session summaries
- `Auction Results` shows sold lots
- `Sale Orders` shows back-office order state
- `Pick List` supports shipping / label matching

## Codebase Map

### Collector Layer
Key files:

- [src/collector/main.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/main.py)
- [src/collector/multitab.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/multitab.py)
- [src/collector/db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/db.py)

Responsibilities:
- launch Playwright
- load cookies
- connect to raw collector DB
- parse banner / lot / sold-price / winner UI states
- insert raw events into the collector database

What interns should know:
- collector code is fragile because it depends on the Whatnot DOM
- small selector or timing changes can break winner capture
- this is one of the highest-risk parts of the project

### Server Layer
Key files:

- [server/api.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/api.py)
- [server/company_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/company_db.py)
- [server/collector_manager.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/collector_manager.py)
- [server/events_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/events_db.py)
- [server/auth.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/auth.py)
- [server/state.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/state.py)
- [server/config.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/config.py)

Responsibilities:
- API routes
- business rules
- database schema and migrations
- live collector process lifecycle
- auth, sessions, CSRF, rate-limiting
- diagnostics and repair tools

What interns should know:
- most workflow bugs are solved here, not in the collector
- most data-integrity bugs are solved here, not in the frontend
- this is the most important code to understand after the core user workflows

### Frontend Layer
Key files:

- [dashboard-vite/src/App.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/App.jsx)
- [dashboard-vite/src/views/Operator.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Operator.jsx)
- [dashboard-vite/src/views/WinnerScanner.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/WinnerScanner.jsx)
- [dashboard-vite/src/views/TvScanner.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/TvScanner.jsx)
- [dashboard-vite/src/views/LargeScreen.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/LargeScreen.jsx)
- [dashboard-vite/src/views/Company.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Company.jsx)
- [dashboard-vite/src/views/company/Inventory.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Inventory.jsx)
- [dashboard-vite/src/views/company/AuctionResults.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/AuctionResults.jsx)
- [dashboard-vite/src/views/company/SaleOrders.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/SaleOrders.jsx)
- [dashboard-vite/src/views/company/Diagnostics.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Diagnostics.jsx)

Responsibilities:
- render the operational tools
- poll or fetch data from the server
- save UI preferences in browser storage
- keep different device roles simple enough for live use

What interns should know:
- the frontend matters, but it should not become the source of truth
- anything critical to sale integrity should be enforced in the backend

## Key Domain Objects

### company_sessions
Represents a live selling session.

Examples:
- one Whatnot show
- one operating block of sales

Contains things like:
- show id
- start/end status
- revenue totals
- product totals

### company_lots
Represents local working lots within a company session.

Used for:
- current operator lot context
- selected products in a live lot
- release/reset behavior

### products
The inventory catalog.

Important fields:
- name
- sku
- barcode
- category
- brand
- gender
- cost
- retail price
- stock
- notes / description / script
- note layers
- image URL
- dupe / inspiration data

### pending_winner_assignments
The winner queue.

These tickets connect:
- Whatnot winner data
- scanned sold product data
- confirmation workflow

Statuses commonly include:
- pending
- assigned
- confirmed
- needs_review

### auction_results
The session result ledger for sold lots.

Important:
- confirmed winner-scanner rows are the trusted version
- provisional raw winner duplicates are not supposed to survive

### sale_orders / sale_order_lines
Back-office commercial records built from session outcomes.

### buyer_groups
Grouping for buyer/order handling after the live session.

## Data Storage

### Main operational DB
- [data/whatnot.db](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/data/whatnot.db)

This is where operational data lives:
- products
- sessions
- lots
- winner assignments
- auction results
- sale orders
- pick list data

### Raw collector DBs / state files
Located under:
- [whatnot-collector/data](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/data)

This area also contains:
- backups
- collector state JSON
- auth state
- log files
- helper exports

### Browser Storage
The app also uses:
- `localStorage`
- `sessionStorage`

Used for:
- theme
- nav visibility
- selected scanner behavior
- inventory filters
- temporary tab/device state

Important:
- browser storage is for UI convenience only
- database data is the real source of truth

## How The System Starts

### Backend
Start the API server from the project root:

```bash
python -m server
```

This serves the local API, typically on port `8088`.

### Frontend
From `dashboard-vite`:

```bash
npm install
npm run dev
```

### Collector
The live collector is usually started from the Operator UI, not manually from the shell.

That matters because the UI-based start also:
- binds the collector to the current company session
- writes process state
- updates status endpoints correctly

## Authentication
Authentication helpers live in:
- [server/auth.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/auth.py)

Important points:
- server-side sessions
- CSRF protection
- password hashing
- optional TOTP/MFA support
- idle and absolute session expiry
- rate limiting / lockouts

Intern rule:
- do not weaken auth or session safety just to “make something easier”

## Diagnostics
Diagnostics is meant to be the system control tower.

It currently covers:
- API health
- collector status
- failed ingests
- duplicate-lot detection
- DB health
- log errors
- timeline / recovery tools

Main UI:
- [dashboard-vite/src/views/company/Diagnostics.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Diagnostics.jsx)

Important operational use:
- if data looks wrong, check Diagnostics before assuming the UI is lying

## Known High-Risk Areas

### 1. Winner ingestion
Risk:
- Whatnot can emit provisional winner-like events
- duplicates can appear if same-lot weaker rows are not suppressed

Rule:
- confirmed winner-scanner sale is stronger than provisional raw winner data

### 2. Collector DOM parsing
Risk:
- selector drift
- timing drift
- Cloudflare challenges
- page navigation during scrape

Symptoms:
- missing winners
- missing lot numbers
- stale collector state

### 3. Inventory editing
Risk:
- rich product fields disappearing if update paths drop fields
- accidental destructive deletes on historically linked products

Rule:
- never touch product names, SKUs, or barcodes casually
- be very careful when doing bulk edits or restores

### 4. Live session continuity
Risk:
- collector stop/restart mismatch
- stale session ids
- stale stream URLs
- duplicate results if old events replay into new sessions

### 5. Browser-only state
Risk:
- frontend looks like it saved something, but DB did not
- stale storage causing confusing page state

Rule:
- always verify whether a problem is in:
  - browser state
  - API payload
  - database row

## Common Debugging Questions

### “Why is a winner missing?”
Check:
- collector health
- raw winner event presence
- lot number presence
- `pending_winner_assignments`
- diagnostics duplicate/failure warnings

### “Why is the wrong product showing?”
Check:
- TV scanner tray
- winner scanner confirmation state
- whether the issue is display-only or sale-truth

### “Why did notes disappear?”
Check:
- DB row directly
- API update path
- whether the issue is old lost data or new failed save logic

### “Why do we have duplicate lots?”
Check:
- provisional winner rows
- same-lot weaker events
- whether a confirmed row already exists for that lot

## Safe Change Rules For Interns

### Do not casually modify:
- barcode values
- SKU values
- product names
- sale prices for historical rows
- confirmed winner rows during live operations

### Before changing live-critical code:
understand whether it affects:
- collector parsing
- session integrity
- winner assignment flow
- inventory deduction
- auction result deduping

### Prefer backend fixes over frontend hacks for:
- duplicate suppression
- data integrity
- confirmation logic
- destructive action safety

### Prefer frontend fixes for:
- layout problems
- readability
- workflow clarity
- accidental confusing UI state

## Recommended First Reading Order For Interns

1. [README.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/README.md)
2. this file
3. [docs/perfume_stream_playbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/perfume_stream_playbook.md)
4. [server/api.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/api.py)
5. [server/company_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/company_db.py)
6. [dashboard-vite/src/views/Operator.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Operator.jsx)
7. [dashboard-vite/src/views/WinnerScanner.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/WinnerScanner.jsx)
8. [dashboard-vite/src/views/company/Inventory.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Inventory.jsx)
9. [dashboard-vite/src/views/company/Diagnostics.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Diagnostics.jsx)

## Good First Tasks For Interns

Best beginner-safe tasks:
- UI polish on non-live company pages
- diagnostics display improvements
- documentation and workflow clarifications
- filter/save-view improvements in inventory
- responsive layout fixes
- non-destructive admin tooling

Higher-risk tasks that need supervision:
- collector parsing
- winner ingestion
- session start/stop logic
- auction-result deduping
- inventory deduction logic
- sale order creation logic

## Final Mental Model
If you remember only one thing, remember this:

- collector gathers noisy stream signals
- backend turns them into operational truth
- barcode scans determine the actual sold product
- confirmed winner scanner rows are the most trustworthy live sale record

Everything else in the system exists to support that safely.
