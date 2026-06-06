# Advanced PDF Label Enrichment System

## Purpose & Goals
- Accurately map TikTok/Whatnot PDF packing slips to internal inventory and orders.
- Prevent wrong-item shipments by robustly matching buyer, order, and product info.
- Enable warehouse staff to verify fulfillment by scanning tracking numbers and product barcodes.

---

## Pipeline Overview

### A. PDF Upload & Parsing
- User uploads raw PDF (label + packing slip).
- System parses:
  - Buyer ID, Buyer Name
  - Order ID(s)
  - Product Name(s) (with batch suffixes, e.g., B1, B2, ...)
  - Tracking Number, Package Weight, Address, etc.

### B. Batch & Lot Mapping
- Product names ending with `B1`, `B2`, ... are mapped to internal batches:
  - B1 = 1–300, B2 = 301–600, etc.
- For each product line:
  - Extract batch number and lot number.
  - Use internal mapping to assign the correct barcode/SKU.

### C. Enrichment & Validation
- For each order line:
  - Cross-reference extracted info with internal auction/order records.
  - Validate:
    - Buyer matches
    - Order ID matches
    - Product name and batch/lot mapping is correct
    - Barcode/SKU assignment is unique and not duplicated
- Flag any mismatches or ambiguities for manual review.

### D. Order Creation for Packing
- Create enriched orders in a dedicated “Packing” section.
- Each order includes:
  - All extracted and mapped fields
  - Internal barcode/SKU
  - Tracking number
  - Link to original PDF for audit

### E. Warehouse Workflow
- Staff scan tracking number → system pulls up the order.
- Staff scan product barcode(s) → system verifies match.
- If mismatch, system blocks fulfillment and alerts supervisor.

### F. Audit & Error Logging
- Every enrichment action is logged:
  - Who uploaded, when, what was mapped, any manual overrides.
- All errors, mismatches, and manual interventions are tracked for QA.

---

## Root Causes of Past Errors
- Loose or ambiguous mapping between PDF product names and internal barcodes, especially with batch suffixes.
- No validation that buyer/order/product/barcode all match across systems.
- No audit trail for manual corrections or overrides.
- No duplicate check for barcodes/SKUs across multiple orders in the same batch.
- No “packing” separation—orders not clearly separated from live auction flow.

---

## Checklist for Robust Enrichment
- [x] Parse all required fields from PDF (buyer, order, product, batch, tracking, etc.)
- [x] Implement strict batch/lot mapping logic
- [x] Cross-validate all fields with internal records
- [x] Block/flag ambiguous or duplicate assignments
- [x] Require manual review for any mismatch
- [x] Log all actions and errors for audit
- [x] Separate packing orders from auction flow
- [x] Enable barcode-based verification at packing
- [x] Provide UI for upload, review, and correction

---

## Sample Enrichment Logic (Python, Pseudocode)

```python
def enrich_packing_slip(pdf_bytes, auction_rows, inventory_map):
    shipments = parse_packing_slip_pdf(pdf_bytes)
    enriched_orders = []
    errors = []
    for shipment in shipments:
        for item in shipment["items"]:
            # Extract batch from product name (e.g., ...B2)
            batch = extract_batch(item["whatnot_name"])
            lot = int(item["lot_number"])
            # Map to internal product
            product = find_internal_product(batch, lot, auction_rows, inventory_map)
            if not product:
                errors.append({"item": item, "reason": "No matching product"})
                continue
            # Validate buyer/order/barcode
            if not validate_buyer_order(shipment, product):
                errors.append({"item": item, "reason": "Mismatch"})
                continue
            enriched_orders.append({
                **shipment,
                "internal_barcode": product["barcode"],
                "sku": product["sku"],
                "validated": True,
            })
    return enriched_orders, errors
```

---

## UI/UX Recommendations
- **Upload page:** Drag-and-drop PDF, show parsed preview, highlight any errors.
- **Review screen:** List all orders, show mapping, allow manual correction if needed.
- **Packing screen:** Scan tracking → show order, scan product → verify match.
- **Audit log:** Show all enrichment actions, errors, and manual interventions.

---

## Monitoring & QA
- **Daily error report** for all enrichment actions.
- **Random audit** of enriched orders.
- **Feedback loop** for warehouse staff to report mismatches.

---

## Next Steps
- Implement or refactor enrichment logic as above.
- Add strict validation and error handling.
- Build or improve UI for upload, review, and packing.
- Set up audit logging and monitoring.
