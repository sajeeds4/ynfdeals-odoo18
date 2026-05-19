# Inventory Data Guide

## Purpose
This document explains how inventory data is represented, what the important product fields mean, and which fields should be treated as operationally sensitive.

Inventory in this project is not just a static catalog. It drives:
- live selling decisions
- low-stock warnings
- sale-order cost math
- pick list preparation
- in-house sales
- TikTok Shop deductions
- cancellation recovery

## Main Table
Primary product and stock data lives in:
- `products`

Other operational tables that affect inventory truth include:
- `pending_winner_assignments`
- `auction_results`
- `sale_orders`
- `sale_order_lines`
- in-house sales tables
- TikTok shop sales linkage

## Product Identity Fields
These fields identify a product and should not be changed casually:
- `name`
- `sku`
- `barcode`

### Why they matter
- barcode is the safest assignment anchor during Winner Scanner use
- SKU often drives import matching
- product name is widely used in UI and printouts, but is weaker than barcode for identity

### Safe rule
If recovering or importing data:
- match by barcode first
- match by SKU second
- use product name last

## Stock Fields
Important stock-related fields:
- `on_hand_qty`
- `low_stock_threshold`
- `storage_bin`
- `product_type`

### on_hand_qty
The current stock count visible to the business.

This should reflect:
- confirmed sales
- approved internal sales
- TikTok shop deductions
- restored stock from cancellations

It should not permanently reflect:
- stale pending duplicates
- unapproved employee draft carts
- giveaway label noise

### low_stock_threshold
The value at which the UI should start warning operators.

Operational meaning:
- once `on_hand_qty <= low_stock_threshold`, the product should visibly enter warning state

If your working rule is “red at 3 or below,” then threshold should be set to `3` for those products.

### storage_bin
Used for:
- picking efficiency
- future walk-order sorting
- warehouse shelf location

This field becomes more valuable once pick lists are sorted by physical route.

## Commercial Fields
Important financial fields:
- `cost_price`
- `retail_price`

### cost_price
Used in:
- auction profit math
- TikTok and Whatnot margin estimates
- in-house sale profit calculation

If cost is wrong, profit is wrong everywhere.

### retail_price
Used mainly as reference pricing.

Important note:
- live sale price and marketplace sale price may differ from product retail
- do not assume retail price is the actual sold price

## Product Info Fields
Common descriptive fields:
- `brand`
- `gender`
- `supplier_name`
- `image_path`
- `image_url`
- category/classification fields

These are important for:
- search
- visual presentation
- product edit pages
- AI/product-assistant context

## Rich Content Fields
These fields are content-heavy and often require recovery or research:
- `description`
- `notes`
- `script`
- `note_top`
- `note_mid`
- `note_base`
- inspired-by / dupe / similar-to fields

These are not inventory-count fields, but they matter operationally because they affect:
- TV display storytelling
- host scripts
- product confidence and verification
- edit-product UX

## Notes Verification Fields
Fragrance note fields should be treated as structured product detail, not as optional decoration.

Typical note structure:
- top notes
- heart notes
- base notes
- verified flag

Recommended rule:
- verification should mark note confidence, not change product identity

## Inventory Movement Events
Inventory changes should be explainable by a real event.

Common legitimate events:
- winner confirmed
- cancelled payment
- restored cancelled sale
- sale order import
- TikTok Shop import
- in-house approval
- manual correction

If stock changes with no obvious event, investigate:
- duplicate winner rows
- double imports
- deleted sale-order lines without restoration
- manual DB edits

## Live Selling Behavior
During Whatnot or TikTok live sessions:
- confirmed product assignment should reduce visible stock
- cancellation should add stock back
- stock warning should update quickly enough for operators to stop overselling

Operationally, the dashboard should answer:
- how many do we have left?
- is this safe to keep selling?
- are we in warning state?

## Matching Imported Orders To Inventory
For imports such as TikTok Shop or packing-slip label handling:

Preferred match order:
1. barcode
2. SKU
3. normalized exact product name
4. manual review

Do not silently accept weak matches if:
- names are ambiguous
- multiple products share similar titles
- the import item is clearly a giveaway or zero-value free item

## Restore Rules
When restoring product detail from backups or exports:
- fill missing fields first
- avoid replacing trusted barcode/SKU/name without a strong reason
- preserve current inventory count unless the restore is specifically about stock

## Common Data Risks
Watch for:
- duplicate barcode across multiple products
- name-only matches creating wrong product linkage
- cost price missing or zero
- stale image URLs
- missing shelf/bin values
- inconsistent note formatting
- product variants collapsed into one record incorrectly

## Recommended Inventory Health Checks
Regularly review:
- low stock products
- out of stock products
- products with no barcode
- products with no image
- products with unverified notes
- dead stock / never sold
- negative or suspicious stock situations

## Safe Editing Rules
Safe to edit carefully:
- description
- notes
- fragrance note fields
- image URL
- supplier
- storage bin
- low stock threshold

High risk edits:
- barcode
- SKU
- product identity name changes
- cost price changes on popular products
- bulk imports that touch on-hand quantities

## Final Rule
Inventory is shared truth across the whole app.

If you change product identity or stock logic, verify the effect in:
- Winner Scanner
- Auction Results
- Sales Orders
- Inventory
- Pick List
- Customers
- TikTok Shop Sales
- In-House Sales
