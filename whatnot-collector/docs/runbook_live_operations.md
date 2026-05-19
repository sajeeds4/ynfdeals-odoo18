# Live Operations Runbook

## Purpose
This is the practical live-stream checklist for operators and technical staff.

Use it:
- before the stream
- during the stream
- after the stream
- when something goes wrong mid-show

## Before Live

### 1. System readiness
Confirm:
- API server is running
- dashboard opens on all required devices
- barcode scanners are connected
- cookies/session for Whatnot are valid

### 2. Device layout
Recommended device roles:
- TV Display device
- Operator device
- Winner Scanner device
- optional Company/Admin device

### 3. Page readiness
Check:
- TV Display opens correctly
- Operator opens correctly
- Winner Scanner queue is empty before starting
- Company inventory is accessible
- Diagnostics opens without layout issues

### 4. Stream readiness
Before starting the live collector:
- no stale active session
- no stale winner queue that belongs to an old session
- no old demo TV tray if you want a clean start

### 5. Inventory readiness
Before the show:
- confirm key products exist
- barcode scans resolve correctly
- critical products have notes, image URL, and dupe/inspiration data if needed

### 6. Diagnostics readiness
Open Diagnostics and check:
- collector is stopped before fresh start
- no active warning flags that need attention
- no unresolved failed ingests from an old live session

## Starting Live

### 1. Start from Operator
Use the Operator page to start the collector for the company stream.

Do not:
- manually start random collector processes in the shell unless you are debugging

### 2. Confirm early live signals
After starting:
- stream status becomes running
- session appears as live
- current lot state updates
- chat/viewer/lot events begin appearing

### 3. First-lot caution
Treat the first lot as a soft validation phase.

Check:
- lot number looks real
- winner queue behavior makes sense
- Winner Scanner reacts as expected

## During Live

### TV flow
Use TV Scanner for:
- product preview only

TV flow should:
- show current product clearly
- keep queued preview products visible
- never affect sale truth directly

### Winner flow
Use Winner Scanner for:
- assigning sold products after winner data arrives

Normal flow:
1. Whatnot provides lot + winner + price
2. pending ticket appears
3. assistant scans sold product
4. confirm/auto-confirm behavior completes the sale

### Inventory discipline
During live:
- avoid editing identity fields
- avoid risky bulk changes
- avoid destructive product cleanup unless absolutely necessary

## What To Watch During Live

### Healthy signs
- current lot advances normally
- pending winner queue updates quickly
- confirmed winner rows reflect actual sold items
- Diagnostics shows no growing warning/failure pattern

### Warning signs
- pending queue stops moving
- same lot appears twice
- auction results show `$1` or numeric-only ghost rows
- winner sync failures appear
- collector health degrades

## Common Live Problems

### Winners lagging behind
Check:
- Diagnostics
- collector health
- whether raw event flow is still active
- whether Winner Scanner is showing stale page state

Immediate safe action:
- refresh Winner Scanner
- compare with Operator and Diagnostics

### Duplicate lots
Typical symptom:
- same lot appears with one real row and one `$1` provisional row

What it usually means:
- provisional winner-like events were ingested alongside confirmed truth

During live:
- trust confirmed Winner Scanner rows
- avoid blind mass deletion

### Collector stalls
Typical symptom:
- stream status looks alive but new winners stop appearing

Check:
- Diagnostics log section
- collector health timestamps
- whether lot/chat/viewer events are still updating

## Recovery During Live

### If a single wrong scanned item is assigned
Use:
- remove/delete item before confirm
- undo if already confirmed

### If a cancelled lot appears
Safe pattern:
- remove pending winner assignment for that lot
- remove bad auction result row
- keep other live data intact

### If duplicates appear
Safe pattern:
- preserve confirmed rows
- clean only the weaker provisional same-lot duplicates
- do not restart unless necessary

### If notes or inventory metadata look wrong
Do not try to restore large datasets mid-stream unless the issue blocks the show.

Prefer:
- continue stream
- document affected items
- repair after the stream

## When A Restart Is Justified

Restart only if:
- collector is truly stalled
- API is broken, not just one page
- winner flow is not recoverable without reloading logic

Before restart:
- understand what state is in DB already
- know whether current queue truth is preserved

## After Live

### 1. Stop collector cleanly
End the live collector through the normal app controls.

### 2. Review session outputs
Check:
- auction results
- sale orders
- pending winner leftovers
- failed ingests
- duplicates

### 3. Shipping/pick-list workflow
If using pick lists:
- upload labels/packing-slip files
- confirm matches

### 4. Inventory review
Check:
- low stock changes
- products deducted correctly
- unusual anomalies

### 5. Diagnostics review
After the show:
- inspect warnings and failures
- note recurring patterns for engineering follow-up

## Things To Avoid

- changing product barcodes mid-stream
- mass deleting historical products mid-stream
- restarting the API casually
- using TV flow as sale truth
- trusting Whatnot product names for product assignment

## Best Operational Principle
If there is ever a disagreement:

- confirmed winner-scanner row beats provisional winner row
- barcode-confirmed product beats noisy Whatnot product title
