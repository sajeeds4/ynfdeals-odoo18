# Contribution Safety Guide

## Purpose
This document explains how to make changes safely in this project.

The system supports real livestream selling, so not all changes have the same risk level. A small bug in the wrong place can create:

- wrong winner assignments
- duplicate lots
- broken inventory history
- misleading reporting
- live-stream chaos

This guide exists so interns and new contributors know how to move safely.

## First Rule
Before changing code, decide which category your change falls into:

1. presentation-only
2. workflow UX
3. business logic
4. live collector behavior
5. historical data correction

The higher the category number, the more careful you need to be.

## Safe Change Zones

### Usually safe
- styling
- layout
- spacing
- responsive fixes
- copy text
- diagnostics presentation
- non-destructive filters/search UI
- documentation

### Usually medium risk
- company reporting views
- inventory table UX
- export options
- browser storage behavior
- settings toggles

### High risk
- winner ingestion
- current lot logic
- auction result generation
- inventory save/update paths
- archive/delete behavior
- sale order generation
- pick list matching

### Highest risk
- collector parsing
- stream start/stop/restart behavior
- lot-number synchronization
- winner deduping
- auto-confirm logic
- anything that writes sale truth automatically

## Golden Rules

### Rule 1: Never trust the UI alone
If something looks wrong:
- check DB
- check API response
- check logs

Do not assume the UI is the real source of truth.

### Rule 2: Never casually change these product fields
- name
- barcode
- SKU

These are identity anchors used throughout the system.

### Rule 3: Never make a temporary frontend workaround for a backend integrity problem
Examples:
- duplicate lots
- missing winner logic
- wrong confirmation behavior

Those should usually be solved in backend logic, not hidden in the UI.

### Rule 4: Presentation flow and sale flow are different
- TV flow is display-only
- Winner Scanner flow is sale-truth

Do not blur them together.

### Rule 5: Confirmed winner-scanner rows are stronger than provisional raw rows
If raw Whatnot signals disagree with confirmed barcode-assigned sales:
- confirmed sale should win

## What To Check Before Editing

### If changing collector code
Check:
- Whatnot selectors
- timing behavior
- Cloudflare/reload behavior
- lot number extraction
- winner extraction
- sold-price extraction

Why:
- collector bugs are subtle and often stream-specific

### If changing winner assignment
Check:
- pending ticket creation
- assigned ticket behavior
- confirmed ticket behavior
- undo/remove behavior
- same-lot duplicate behavior

Why:
- this is where sales truth is formed

### If changing inventory save logic
Check:
- whether rich fields are preserved
- whether blank fields overwrite existing content
- whether historical references exist
- whether delete should archive instead

### If changing reporting
Check:
- whether rows are raw provisional rows or confirmed rows
- whether totals are session-scoped correctly
- whether duplicates are being suppressed

## How To Test Safely

### For UI-only changes
Test:
- page loads
- dark/light theme
- responsive layout
- no overflow

### For inventory changes
Test:
- edit one field
- save
- hard refresh
- confirm DB/API still reflect the saved value

### For winner workflow changes
Test:
- pending ticket appears
- scan assigns item
- confirm succeeds
- undo works
- duplicate same-lot provisional rows do not survive

### For live session changes
Test:
- fresh session start
- current lot behavior
- winner queue movement
- restart/stop state
- stale state cleanup

## Data Safety Rules

### Always back up before destructive fixes
When touching:
- deletes
- batch cleanup
- recovery scripts
- session pruning
- duplicate removal

Make a DB backup first.

### Prefer fill-only recovery over overwrite
When restoring product details from backups:
- fill blank fields only when possible
- do not overwrite current barcodes, names, or SKUs

### Understand foreign keys before delete logic
Products may be referenced by:
- company lot items
- sale order lines
- inventory movements
- winner assignment items

Never assume a hard delete is safe.

## Live Stream Rules

### During a live session
Avoid:
- unnecessary server restarts
- large schema changes
- deep refactors
- collector changes

Prefer:
- targeted cleanup
- small UI fixes
- DB corrections only when clearly understood

### If duplicates appear during live
Do:
- confirm whether they are provisional same-lot rows
- preserve confirmed winner-scanner truth
- clean symptoms carefully if needed

Do not:
- guess blindly
- mass delete unrelated rows

## Debugging Order
When something breaks, use this order:

1. Diagnostics page
2. API response
3. DB row
4. logs
5. frontend rendering

This order prevents a lot of wrong assumptions.

## Good First Tasks For Interns

Best starter work:
- documentation
- diagnostics layout
- inventory filters
- settings UX
- export improvements
- table usability
- theme polish

## Tasks That Need Review Before Merge

- anything in `src/collector`
- winner ingestion logic
- session start/stop logic
- duplicate suppression logic
- inventory save/update backend code
- destructive cleanup scripts

## Code Review Expectations

Before asking for review, answer:

1. what workflow does this change touch?
2. could it affect live sales truth?
3. could it create duplicates?
4. could it destroy history?
5. how did I verify it?

If you cannot answer those, the change probably is not ready.

## Final Safety Principle
The safest mindset for this project is:

- raw stream data is noisy
- backend truth must be deliberate
- UI should help operators, not invent business truth
- destructive actions must be reversible or well understood

If you keep those 4 ideas in mind, you will avoid most costly mistakes.
