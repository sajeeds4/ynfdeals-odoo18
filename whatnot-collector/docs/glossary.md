# Glossary

## lot
A single live auction sale unit, usually tied to a visible lot number in a session.

## session
A company-managed live selling block for Whatnot or TikTok. Sessions group lots, winners, revenue, profit, and post-live workflows.

## pending winner
A winner ticket that has been created from collector or OCR data but has not yet been fully assigned to a real sold product.

## assigned
A winner ticket that has one or more products attached but is not fully finalized yet.

## confirmed
A winner ticket or result that has been accepted as trusted sale truth. Confirmed rows should drive downstream data such as sale orders, inventory, and customer history.

## needs review
A holding state used when the lot exists but the data is suspicious, incomplete, or not safe to finalize automatically.

## payment review
A holding state used when the sale may still be real, but payment confirmation is uncertain and the row should not be blindly trusted financially.

## payment cancelled
A state meaning the order should no longer count financially. Revenue, fees, and profit should be removed, and inventory should return.

## auction result
The session-level operational record of a sold lot. This is where lot, winner, price, cost, fees, and downstream sale truth meet.

## sale order
A downstream order record created from confirmed sales. Sale orders are used for fulfillment, customer history, and reporting.

## sale order line
An individual product row inside a sale order.

## pick list
A fulfillment list used after the show to gather sold items by buyer or shipment.

## bulk pull summary
A grouped version of the pick list that shows repeated products aggregated by quantity so a picker can grab multiple units at once.

## buyer group
A grouped post-live view of lots belonging to the same buyer.

## candidate
A provisional product scanned or selected in the current lot context before the lot is finalized.

## release
An operator action that advances or clears the current lot context.

## inventory deduction
The stock reduction that happens when a sale becomes real enough to count against inventory.

## inventory restore
The stock increase that happens when a confirmed or deducted sale is cancelled, deleted, or corrected.

## label confirmation
Using uploaded packing slip or shipping label PDFs as fulfillment/payment truth for Whatnot post-live validation.

## giveaway page
A label or packing-slip page that represents a free item, giveaway, or zero-dollar shipment and should not become sale truth.

## TikTok Shop
Normal TikTok marketplace/shop orders. These are different from live OCR-detected TikTok auction wins.

## TikTok LIVE Auctions
Live-stream auction results collected from the TikTok OCR workflow.

## internal POS
The employee mobile ordering flow where an in-house cart is submitted for manager approval before becoming a final sale.

## employee account
A canonical in-house identity used to group multiple employee purchases under one person.

## current lot pointer
The live lot number the operator or extractor expects next, especially important in TikTok OCR recovery.

## popup lock
A detection safeguard that suppresses repeated winner-popup frames so the same winner does not get inserted multiple times.

## anomaly hold
A detection safeguard that prevents suspicious OCR jumps or duplicated winner events from becoming trusted lots immediately.
