# Testing Guide

## Purpose
This guide defines the minimum testing standard before shipping changes in this project.

The app is not a normal CRUD dashboard. A small code change can break:
- live winner ingestion
- auction result math
- sale-order sync
- inventory deduction
- pick list generation
- customer history

Because of that, testing must follow the business flow, not just individual screens.

## Core Testing Rule
Whenever possible, test in this order:

1. backend behavior
2. API response
3. UI render
4. workflow side-effects
5. hard refresh and persistence

If a change touches live workflows, test both:
- immediate behavior
- persisted behavior after refresh/restart

## Baseline Smoke Test
Run this after any meaningful change:

1. App loads without blank screen.
2. Key pages render:
   - Operator
   - Winner Scanner
   - Auction Results
   - Sales Orders
   - Inventory
   - Customers
   - Pick List
3. API server starts cleanly.
4. Frontend build passes.
5. Python compile passes.

## Frontend Testing
For UI changes, verify:
- page loads without crash
- no blank screen
- no console-breaking render loop
- inputs still save
- layout works at 100% zoom
- main controls remain visible on common laptop widths

Also check:
- long names do not break tables/cards
- compact dropdowns still remain usable
- printed views do not inherit broken screen layout

### Responsive Checks
At minimum inspect:
- desktop browser
- smaller laptop width
- mobile layout for internal POS

## Backend Testing
For server changes, test:
- `python3 -m py_compile`
- affected API endpoints with real requests
- database writes and reads
- no accidental crashes from request-handler scope changes

If you touch:
- `company_db.py`
- `api.py`
- collector logic

then verify both:
- happy path
- invalid input path

## Inventory Testing
Any inventory-affecting change must verify:

1. Product starts with known stock.
2. Sale or assignment reduces stock when expected.
3. Cancellation restores stock when expected.
4. Wrong product removal restores the removed SKU.
5. UI warning states update:
   - normal
   - low stock
   - out of stock

### Inventory Regression Cases
Always test:
- normal confirmed sale
- cancelled payment
- restored cancelled sale
- edited assigned product
- in-house sale approval
- TikTok shop import deduction

## Winner Flow Testing
If you change anything around Whatnot or TikTok winner flow, test:

1. pending ticket creation
2. product assignment
3. confirm
4. delete
5. cancel payment
6. restore confirmed sale
7. hard refresh

### TikTok-Specific Tests
Because TikTok OCR is noisy, also verify:
- lot extracted only from auction bar
- chat badges do not become lot numbers
- same popup does not create repeated winners
- manual current-lot override works
- correcting a lot does not leave the next lot drifting

### Whatnot-Specific Tests
Verify:
- collector start/stop state is reflected in Operator
- winner assignment queue stays stable
- label import does not create giveaway fake rows
- missing label lots are handled correctly

## Sales Order Testing
When sale-order logic changes, verify:
- confirmed orders appear in Sales Orders
- cancelled orders stop counting toward booked revenue
- lot numbers stay visible where expected
- customer link still works
- session filter still isolates correct orders

Test both:
- Whatnot sale orders
- TikTok live sale orders
- TikTok shop sales
- in-house sales

## Auction Results Testing
Auction Results is a control surface, so test:
- edit lot
- edit winner
- edit price
- payment review
- cancel payment
- restore confirmed sale
- re-open for rescan

After each action verify:
- sale orders
- inventory
- customers
- session metrics

## Customer Testing
If customer logic changes, verify:
- username click opens real detail
- sale history is present
- TikTok Shop customers link correctly
- review page does not 404
- customer with no orders is filtered correctly if that rule is expected

## Pick List Testing
If label import or pick list code changes, verify:
- PDF upload succeeds
- giveaway pages are ignored
- lot matching is sane
- repeated products aggregate correctly in bulk pull summary
- A4 print layout is readable
- separate print buttons work:
  - pick list
  - grab list
  - both

## Internal POS / In-House Testing
For in-house POS changes, verify:
- QR/token link opens
- employee identity resolves
- search works
- barcode lookup works
- submit creates pending approval
- approving creates final in-house sale
- inventory deducts only on approval

## Live Session Caution
Avoid risky collector or DB-logic testing during an important live show unless the fix is urgent.

If a live fix is unavoidable:
- prefer narrow fixes
- verify only the affected path
- do not mix unrelated refactors

## Recommended Commands
Useful baseline checks:

```bash
python3 -m py_compile whatnot-collector/server/api.py whatnot-collector/server/company_db.py
```

```bash
cd whatnot-collector/dashboard-vite && npm run build
```

```bash
cd whatnot-collector && python3 -m unittest
```

## Release Checklist
Before pushing:
- compile passes
- build passes
- affected workflow tested manually
- no blank screen
- no obvious DB sync regression
- no broken print view
- no broken operator live controls
