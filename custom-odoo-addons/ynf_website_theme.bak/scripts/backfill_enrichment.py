#!/usr/bin/env python3
"""Backfill product.template.x_ynf_dupe_inspiration + x_ynf_note_*
fields from whatnot-collector/exports/inventory_enrichment_master.json.

Run via Odoo shell:

    cd /home/cybertechna/odoo18_live && \
        .venv/bin/python odoo-bin shell -c odoo.conf -d YNFDEALS --no-http \
        < /path/to/this/script

Idempotent — only writes when the target field is empty or has placeholder
values like "unknown" / "Unclear". Existing real data is never overwritten.
"""
import json
import os
import sys

JSON_PATH = ("/home/cybertechna/AethrixSystems_Portable/hjay9672-WN "
             "/whatnot-collector/exports/inventory_enrichment_master.json")

PLACEHOLDERS = {
    "", "unknown", "n/a", "na",
    "unclear / not enough reliable agreement yet",
    "unclear",
}


def is_placeholder(value):
    return (value or "").strip().lower() in PLACEHOLDERS


def main(env):
    if not os.path.exists(JSON_PATH):
        print(f"ERROR: {JSON_PATH} not found")
        return 1
    with open(JSON_PATH) as f:
        rows = json.load(f)
    print(f"Loaded {len(rows)} enrichment rows")

    Product = env["product.product"]
    Template = env["product.template"]
    by_barcode = {}
    for r in rows:
        b = (r.get("barcode") or "").strip()
        if b and b not in PLACEHOLDERS:
            by_barcode[b] = r

    print(f"  → {len(by_barcode)} rows have a usable barcode")

    inspiration_set = notes_set = skipped = no_match = 0
    products = Product.search([("barcode", "in", list(by_barcode.keys()))])
    print(f"Matching {len(products)} products by barcode...")

    for p in products:
        row = by_barcode.get(p.barcode or "")
        if not row:
            no_match += 1
            continue
        tmpl = p.product_tmpl_id
        vals = {}

        # Inspiration: combine "inspiration_brand" + "inspiration_fragrance"
        ibrand = (row.get("inspiration_brand") or "").strip()
        ifrag = (row.get("inspiration_fragrance") or "").strip()
        if not is_placeholder(ifrag):
            inspiration = ifrag
            if not is_placeholder(ibrand) and ibrand.lower() not in ifrag.lower():
                inspiration = f"{ibrand} {ifrag}"
            if (is_placeholder(tmpl.x_ynf_dupe_inspiration)
                    and inspiration):
                vals["x_ynf_dupe_inspiration"] = inspiration[:200]
                inspiration_set += 1

        # Notes — only fill if empty
        if is_placeholder(tmpl.x_ynf_note_top) and not is_placeholder(row.get("top_notes")):
            vals["x_ynf_note_top"] = row["top_notes"].strip()[:200]
        if is_placeholder(tmpl.x_ynf_note_mid) and not is_placeholder(row.get("middle_notes")):
            vals["x_ynf_note_mid"] = row["middle_notes"].strip()[:200]
        if is_placeholder(tmpl.x_ynf_note_base) and not is_placeholder(row.get("base_notes")):
            vals["x_ynf_note_base"] = row["base_notes"].strip()[:200]

        if any(k.startswith("x_ynf_note_") for k in vals):
            notes_set += 1

        if vals:
            try:
                tmpl.write(vals)
            except Exception as exc:
                print(f"  ! write failed for {p.barcode}: {exc}")
                skipped += 1
        else:
            skipped += 1

    env.cr.commit()
    print()
    print(f"Done.  inspiration backfilled: {inspiration_set}")
    print(f"       notes backfilled:       {notes_set}")
    print(f"       no change needed:       {skipped}")
    print(f"       no-match barcodes:      {no_match}")
    return 0


sys.exit(main(env))
