# Troubleshooting Guide

## Purpose
This file maps common symptoms to:

- likely causes
- where to inspect
- safest next action

## 1. Winner Scanner Is Empty But Stream Is Live

### Likely causes
- collector is not ingesting winners
- pending winner queue is stale
- page is showing stale client state
- winner event arrived without enough data

### Check
- Diagnostics page
- `GET /api/system/diagnostics`
- `GET /api/winner_assignment/state`
- `GET /api/session_stats`

### Safe next action
- refresh Winner Scanner
- compare latest winner in Operator/session stats vs pending queue

## 2. Same Lot Appears Twice In Auction Results

### Likely causes
- provisional raw winner row plus final confirmed row
- same-lot weaker event got ingested later
- dedupe logic failed or stale rows reappeared

### Check
- `pending_winner_assignments`
- `auction_results`
- Diagnostics duplicate detector

### Safe next action
- preserve confirmed row
- remove only weaker same-lot provisional rows

## 3. Product Notes Saved But Vanish After Refresh

### Likely causes
- backend update path dropped fields
- browser cache or session state is stale
- older data had already been lost

### Check
- product row in DB
- inventory update endpoint behavior
- current API inventory response

### Safe next action
- confirm DB truth first
- do not assume the UI is lying or telling the truth until checked

## 4. TV Display Shows Wrong Product

### Likely causes
- demo tray/live tray confusion
- stale preview state
- TV scan path and sale path mixed mentally

### Check
- `GET /api/obs/current`
- TV Scanner state
- whether current issue is only display-related

### Safe next action
- verify whether sale records are correct before taking action

## 5. Inventory Looks Empty

### Likely causes
- page filter state stuck
- stale session/browser storage
- API response good but UI state bad

### Check
- `GET /api/inventory`
- Inventory filters
- browser session state

### Safe next action
- refresh Inventory
- clear stale filter state if needed

## 6. Collector Shows Running But Data Stops Moving

### Likely causes
- page navigated mid-tick
- browser process unhealthy
- Cloudflare challenge
- collector worker stale

### Check
- Diagnostics log section
- collector health timestamps
- recent event timestamps

### Safe next action
- confirm if all event types stalled or only winners stalled
- restart only if truly necessary

## 7. Wrong Product Was Scanned In Winner Scanner

### Likely causes
- operator scan mistake

### Check
- assignment item rows
- whether the lot has already been confirmed

### Safe next action
- remove item before confirm
- use undo if already confirmed

## 8. Cancelled Lot Appears In Results

### Likely causes
- provisional or bad row persisted
- cancelled lot was not cleared from queue/results

### Check
- pending winner assignment for that lot
- auction result row for that lot

### Safe next action
- remove only that lot’s bad rows
- keep confirmed valid rows intact

## 9. Sale Orders Do Not Match Auction Results

### Likely causes
- sale order generation lag
- manual edits
- confirmed sale never became a sale order

### Check
- `auction_results`
- `sale_orders`
- `sale_order_lines`
- `buyer_groups`

### Safe next action
- figure out whether the mismatch is reporting-only or fulfillment-critical

## 10. Diagnostics Page Goes Off Screen

### Likely causes
- layout stretch
- overflow clipping
- panels forcing oversized row heights

### Check
- page wrapper overflow
- diagnostics grid layout

### Safe next action
- fix layout only
- do not touch business logic for a display issue
