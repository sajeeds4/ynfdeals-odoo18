# Recovery Playbook

## Purpose
This playbook is for repairing operational data without making a messy situation worse.

Use it when:
- a live collector stops or drifts
- lots are duplicated
- a wrong winner was inserted
- a payment is cancelled after the show
- inventory no longer matches the sale truth
- a pick list or label import created bad rows

The recovery rule for this project is simple:
- preserve trusted truth
- remove weak or duplicate truth
- sync the fix everywhere

Trusted truth usually means:
- a confirmed winner assignment with barcode-backed product scan
- a manually reviewed auction result
- a label-confirmed shipment
- an intentionally cancelled order

## Recovery Order Of Operations
When something is wrong, work in this order:

1. Identify the session.
2. Identify whether the bad row is pending, assigned, confirmed, cancelled, or already in sale orders.
3. Decide which record is the source of truth.
4. Backup before destructive cleanup.
5. Fix the highest-trust record first.
6. Verify downstream sync:
   - auction results
   - sale orders
   - customers
   - inventory
   - pick list
   - dashboard metrics

## Before You Change Anything
Always capture:
- session id
- lot number(s)
- winner username
- sale price
- current status
- whether a sale order already exists
- whether inventory was already deducted

Recommended quick checks:
- `Auction Results`
- `Winner Scanner`
- `Sales Orders`
- `Inventory`
- `Customers`
- `Pick List`

If the stream is still live, prefer the least disruptive fix possible.

## Scenario 1: Duplicate Pending Lots
Symptoms:
- same winner appears multiple times within seconds
- same price appears multiple times
- pending queue keeps growing while the popup is still visible

Safe action:
1. Keep the row that matches the true live lot.
2. Delete the stale duplicates.
3. If TikTok is drifting, reset the current lot pointer in Operator.
4. Verify the queue only contains the valid row.

After cleanup, confirm:
- duplicate pending rows are gone
- there is no duplicate auction result for the same winner/price
- the next winner comes in once

## Scenario 2: Wrong Lot Number During Live
Symptoms:
- first live lot begins at the wrong number
- OCR jumps ahead
- lots are created from old sequence state instead of the auction card

Safe action:
1. Correct the live lot in Winner Scanner if the row already exists.
2. Update the TikTok current lot control in Operator to the next real lot.
3. Delete any obviously wrong pending rows created from the bad sequence.
4. Continue from the corrected live lot number instead of trying to preserve bad earlier numbering.

Important note:
- do not try to keep every bad early lot if the session is already drifting
- reset and continue cleanly

## Scenario 3: Wrong Winner But Right Lot
Symptoms:
- lot number is correct
- winner OCR is wrong or duplicated

Safe action:
1. Open the affected row in Winner Scanner or Auction Results.
2. Correct the winner username.
3. Verify customer linkage updates.
4. Verify no duplicate lot exists for the corrected winner.

If the wrong winner has already created a sale order:
1. fix the auction result first
2. confirm the sale order reflects the change
3. verify customer history

## Scenario 4: Payment Cancelled After The Show
Symptoms:
- Whatnot payment failed later
- order existed for hours or months and then becomes invalid
- labels do not include the lot

Business rule:
- cancelled means zero revenue, zero fees, zero profit contribution
- cancelled means product goes back into inventory
- cancelled must sync everywhere even for old sessions

Safe action:
1. Mark the lot as `payment_cancelled` or equivalent cancellation status.
2. Re-open inventory for the assigned product(s).
3. Confirm sale order status changes to cancelled.
4. Verify the session metrics shrink.
5. Verify customer history still shows the order appropriately as cancelled.

What to verify:
- auction results no longer count the row financially
- sale orders no longer count it as booked revenue
- inventory quantity is restored
- pick list no longer treats it as a valid shipment

## Scenario 5: Labels Missing A Lot
For Whatnot packing slips and labels:
- if a lot from that session is not present in the uploaded label file, treat it as cancelled unless manually overridden later

Safe action:
1. Compare session lots against imported labels.
2. Mark missing lots as cancelled or payment review.
3. Restore inventory for those lots.
4. Keep notes explaining why the lot was cancelled.

If a label later appears or payment later succeeds:
1. restore the lot to confirmed
2. re-apply inventory deduction if needed
3. restore downstream sale-order truth

## Scenario 6: Wrong Product Assigned
Symptoms:
- winner is correct
- product barcode was scanned wrong
- inventory for the wrong SKU was deducted

Safe action:
1. Open the winner assignment.
2. Remove the bad product line.
3. Confirm inventory restores for the removed product.
4. Scan or assign the correct product.
5. Confirm the new product deducts correctly.

Verify:
- auction result product display
- sale order line
- inventory on-hand
- pick list product text

## Scenario 7: Pick List / Label Import Created Bad Rows
Symptoms:
- duplicate lots with zero-dollar rows
- giveaway slips turned into fake order rows
- wrong buyer linked to a real lot number

Safe action:
1. Remove imported rows that came from giveaway or non-sale pages.
2. Keep the real auction-backed lot rows.
3. Rebuild or re-import the pick list if necessary.

Specific rules:
- giveaway pages must be ignored
- zero-dollar giveaway labels should not become sale truth
- label matching should not override trusted confirmed auction truth blindly

## Scenario 8: Collector Or Browser Pipe Failure
Symptoms:
- collector stops ingesting
- browser session dies
- queue stops moving while the live stream continues

Safe action during live:
1. Confirm whether the collector process is actually stopped.
2. Restart only the affected process if possible.
3. Avoid broad restarts unless necessary.
4. Resume from the current live lot, not the stale remembered one.

After restart:
- verify session id
- verify current lot
- verify first new winner lands correctly

## Inventory Recovery Checklist
Any time you change a lot with assigned products, verify inventory:

1. Was the product already deducted?
2. Should this action restore stock or consume stock?
3. Is the product now shown correctly in the winner assignment?
4. Is the inventory warning state still correct?

Common recovery outcomes:
- cancelled lot -> restore stock
- deleted pending duplicate without confirmed product -> no stock change
- corrected product assignment -> restore wrong SKU, deduct right SKU
- restored confirmed sale -> deduct stock again if it had been added back

## Session Recovery Checklist
After any major cleanup, verify the session itself:
- session revenue
- session fees
- session profit
- lots sold
- products sold
- cancelled impact

If the numbers look wrong, check:
- duplicate auction results
- cancelled sale orders still counted as active
- restored inventory without restored sale status

## Suggested Backup Pattern
Before destructive cleanup:
- copy the database file
- note the affected session id
- note the affected lot ids
- screenshot the current UI state if the issue is visible there

Suggested naming:
- `whatnot.db.backup.before_session_65_lot_cleanup`

## Final Verification After Any Recovery
Before calling the recovery complete, confirm:
- pending queue looks right
- confirmed rows are correct
- no duplicate lot exists
- customer history is correct
- inventory matches expected stock
- pick list and sale orders reflect the same truth
- dashboard totals changed in the expected direction

If one page still disagrees:
- the recovery is not complete yet
- trace the issue from the highest-trust record outward
