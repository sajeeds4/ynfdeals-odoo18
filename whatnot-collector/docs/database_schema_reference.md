# Database Schema Reference

## Purpose
This file explains the main SQLite schema used by the application.

Primary schema source:
- [server/company_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/company_db.py)

Primary database file:
- [data/whatnot.db](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/data/whatnot.db)

## Two Kinds Of Data

### Raw stream data
Produced by the collector.

Examples:
- stream events
- reconstructed spectator history
- OCR/caption support data

Main logic layer:
- [server/events_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/events_db.py)

### Business / operational data
Produced by the local app.

Examples:
- products
- company sessions
- company lots
- winner assignments
- auction results
- sale orders
- pick lists

Main schema layer:
- [server/company_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/company_db.py)

## Truth Hierarchy
When tables disagree, the intended trust order is usually:

1. confirmed winner assignment
2. synced auction result derived from confirmed winner assignment
3. provisional pending winner assignment
4. raw Whatnot winner-like event

That hierarchy matters when debugging duplicates.

## Table Reference

### company_sessions
Purpose:
- one company-owned livestream session

Key columns:
- `id`
- `stream_id`
- `show_id`
- `whatnot_account`
- `name`
- `status`
- `current_lot_number`
- `started_at`
- `ended_at`
- `total_revenue`
- `total_cost`
- `total_profit`
- `total_products_sold`
- `total_lots_sold`

Relationships:
- parent of `company_lots`
- parent of `auction_results`
- parent of `pending_winner_assignments`
- parent of `sale_orders`
- parent of `buyer_groups`
- parent of `pick_lists`

Truth type:
- business truth

### company_lots
Purpose:
- local working lots inside a session

Key columns:
- `id`
- `session_id`
- `lot_number`
- `status`
- `winner_username`
- `winning_price`
- `fees`
- `total_cost`
- `total_profit`
- `total_products`
- `sold_products`
- `dropped_products`
- `created_at`
- `updated_at`
- `closed_at`

Relationships:
- belongs to `company_sessions`
- parent of `company_lot_items`
- referenced by `auction_results`
- referenced by `sale_order_lines`
- referenced by `pending_winner_assignments`

Truth type:
- local operational truth

Important note:
- `lot_number` here can be local working context and must be handled carefully when compared with noisy Whatnot data

### product_categories
Purpose:
- normalized category list for products

Key columns:
- `id`
- `name`
- `created_at`
- `updated_at`

Relationships:
- referenced by `products.category_id`

Truth type:
- business support data

### products
Purpose:
- master inventory catalog

Key columns:
- `id`
- `name`
- `sku`
- `barcode`
- `category_id`
- `brand`
- `gender`
- `supplier_name`
- `storage_bin`
- `product_type`
- `image_path`
- `cost_price`
- `retail_price`
- `on_hand_qty`
- `low_stock_threshold`
- `active`
- `notes`
- `created_at`
- `updated_at`

Relationships:
- referenced by `company_lot_items`
- referenced by `pending_winner_assignments.assigned_product_id`
- referenced by `pending_winner_assignment_items`
- referenced by `sale_order_lines`
- referenced by `inventory_movements`

Truth type:
- business truth

Important note:
- name, SKU, and barcode are identity-critical fields and should not be casually changed

### company_lot_items
Purpose:
- items scanned into a working lot

Key columns:
- `id`
- `lot_id`
- `product_id`
- `barcode`
- `sku`
- `product_name`
- `unit_cost`
- `qty_snapshot`
- `scanned_at`
- `status`

Relationships:
- belongs to `company_lots`
- optionally belongs to `products`

Truth type:
- operational working-state data

Important statuses often seen:
- open
- released
- dropped
- active/selected in UI logic

### customers
Purpose:
- known customers / Whatnot users

Key columns:
- `id`
- `whatnot_username`
- `display_name`
- `email`
- `phone`
- `address`
- `notes`

Relationships:
- referenced by `auction_results`
- referenced by `sale_orders`
- referenced by `buyer_groups`
- referenced by `pick_list_items`

Truth type:
- business support data

### auction_results
Purpose:
- sold-lot ledger for a session

Key columns:
- `id`
- `session_id`
- `lot_id`
- `lot_number`
- `winner_username`
- `customer_id`
- `sold_at`
- `sale_price`
- `fees`
- `cost_price`
- `profit`
- `margin_pct`
- `product_name`
- `barcode`
- `sku`
- `products_sold_count`
- `source_event_id`

Relationships:
- belongs to `company_sessions`
- optionally references `company_lots`
- optionally references `customers`
- optionally referenced by `pending_winner_assignments`
- optionally referenced by `sale_order_lines`

Truth type:
- business truth, but historically vulnerable to duplicate/provisional rows if not synchronized properly

Important note:
- confirmed winner-scanner output should usually dominate this table’s final meaning

### pending_winner_assignments
Purpose:
- queue of winner tickets

Key columns:
- `id`
- `session_id`
- `lot_id`
- `auction_result_id`
- `lot_number`
- `winner_username`
- `sale_price`
- `source_event_id`
- `detected_at`
- `status`
- `assigned_product_id`
- `assigned_barcode`
- `assigned_sku`
- `assigned_product_name`
- `assigned_cost_price`
- `assigned_at`
- `confirmed_at`
- `notes`

Relationships:
- belongs to `company_sessions`
- optionally references `company_lots`
- optionally references `auction_results`
- optionally references `products`
- parent of `pending_winner_assignment_items`

Truth type:
- workflow truth

Statuses:
- `pending`
- `assigned`
- `confirmed`
- `needs_review`

### pending_winner_assignment_items
Purpose:
- line items scanned into a winner ticket

Key columns:
- `id`
- `assignment_id`
- `product_id`
- `barcode`
- `sku`
- `product_name`
- `unit_cost`
- `qty`

Relationships:
- belongs to `pending_winner_assignments`
- references `products`

Truth type:
- workflow truth

Important note:
- this table enables multi-product assignment for a single lot

### sale_orders
Purpose:
- commercial order header records

Key columns:
- `id`
- `order_number`
- `session_id`
- `customer_id`
- `buyer_group_id`
- `whatnot_buyer_username`
- `state`
- `fulfillment_status`
- `payment_status`
- `tracking_number`
- `packed_at`
- `shipped_at`
- `subtotal`
- `total_amount`
- `notes`
- `ordered_at`

Relationships:
- optionally belongs to `company_sessions`
- optionally belongs to `customers`
- referenced by `buyer_groups`
- parent of `sale_order_lines`

Truth type:
- business truth

### buyer_groups
Purpose:
- aggregate lots and value per buyer for a session

Key columns:
- `id`
- `session_id`
- `customer_id`
- `buyer_username`
- `total_items`
- `total_lots_won`
- `total_revenue`
- `total_cost`
- `total_profit`
- `overall_margin`
- `sale_order_id`

Relationships:
- belongs to `company_sessions`
- optionally references `customers`
- optionally references `sale_orders`

Truth type:
- derived business aggregation

### sale_order_lines
Purpose:
- commercial order line items

Key columns:
- `id`
- `sale_order_id`
- `product_id`
- `lot_id`
- `auction_result_id`
- `description`
- `qty`
- `unit_price`
- `subtotal`
- `inventory_applied`

Relationships:
- belongs to `sale_orders`
- optionally references `products`
- optionally references `company_lots`
- optionally references `auction_results`

Truth type:
- business truth

### inventory_movements
Purpose:
- inventory adjustment trail

Key columns:
- `id`
- `product_id`
- `movement_type`
- `qty_delta`
- `reason`
- `reference_type`
- `reference_id`
- `created_at`

Relationships:
- belongs to `products`

Truth type:
- audit truth

Important note:
- this is the best place to understand stock changes over time

### app_settings
Purpose:
- generic key/value app settings

Key columns:
- `key`
- `value`
- `updated_at`

Truth type:
- application configuration data

### pick_lists
Purpose:
- upload/session-level shipping batch records

Key columns:
- `id`
- `session_id`
- `filename`
- `total_shipments`
- `total_lots`
- `matched_lots`
- `unmatched_lots`
- `total_revenue`
- `customers_synced`
- `orders_synced`
- `inventory_deducted`
- `created_at`

Relationships:
- optionally belongs to `company_sessions`
- parent of `pick_list_items`

Truth type:
- workflow/support data

### pick_list_items
Purpose:
- lot-level rows extracted from a shipping/pick-list upload

Key columns:
- `id`
- `pick_list_id`
- `shipment_index`
- `username`
- `buyer_name`
- `address`
- `tracking_number`
- `shipping_method`
- `ship_date`
- `weight`
- `lot_number`
- `product_name`
- `barcode`
- `sku`
- `sale_price`
- `order_id`
- `matched`
- `sale_order_id`
- `customer_id`

Relationships:
- belongs to `pick_lists`
- optionally references `sale_orders`
- optionally references `customers`

Truth type:
- workflow/support data

## Relationship Summary

Typical high-level flow:

- `company_sessions`
  - own `company_lots`
  - own `auction_results`
  - own `pending_winner_assignments`
  - own `sale_orders`
  - own `buyer_groups`
  - own `pick_lists`

- `company_lots`
  - own `company_lot_items`
  - may be linked to `auction_results`

- `pending_winner_assignments`
  - may point to `auction_results`
  - own `pending_winner_assignment_items`

- `sale_orders`
  - own `sale_order_lines`

## Raw Vs Business Truth Table Groups

### Mostly raw / event-side
- raw collector event tables from collector/event DB logic
- OCR/caption support tables
- reconstructed stream insight tables

### Mostly workflow truth
- `pending_winner_assignments`
- `pending_winner_assignment_items`
- `company_lots`
- `company_lot_items`

### Mostly business truth
- `products`
- `auction_results`
- `sale_orders`
- `sale_order_lines`
- `inventory_movements`
- `customers`

## Typical Query/Debug Strategy

If a sale looks wrong, inspect in this order:

1. `pending_winner_assignments`
2. `pending_winner_assignment_items`
3. `auction_results`
4. `sale_order_lines`
5. `inventory_movements`

If inventory looks wrong, inspect:

1. `products`
2. `inventory_movements`
3. `sale_order_lines`
4. related winner assignment item rows

If session totals look wrong, inspect:

1. `company_sessions`
2. `company_lots`
3. `auction_results`
4. `buyer_groups`

## Schema Safety Notes

- foreign keys are enabled
- SQLite WAL mode is used
- destructive changes should be backed up first
- hard deletes should be treated carefully because several tables are historically linked
