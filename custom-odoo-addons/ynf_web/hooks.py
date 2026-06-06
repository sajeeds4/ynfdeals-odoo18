# -*- coding: utf-8 -*-
"""Post-install hook — restore x_ynf_* values from the CSV snapshot taken
right before the ynf_storefront uninstall.

The columns were dropped by Odoo's uninstall of `ynf_storefront`. The new
`ynf_web` module re-declares them via `_inherit`, so installation re-creates
the empty columns. This hook reads the most recent backup CSV and refills
them. It's idempotent — only writes when the current cell is empty.
"""
import csv
import glob
import logging
import os

_logger = logging.getLogger(__name__)

BACKUP_GLOB = "/home/cybertechna/odoo_backups/pre-storefront-uninstall-*/product_template_xynf_values.csv"


def post_init_restore_xynf(env):
    """Refill x_ynf_inspired_by / x_ynf_family / x_ynf_image_url on
    product.template rows from the latest CSV backup.

    Only writes a value if the column is currently empty — safe to re-run.
    """
    csvs = sorted(glob.glob(BACKUP_GLOB))
    if not csvs:
        _logger.info("ynf_web: no x_ynf backup CSV found at %s — skipping refill", BACKUP_GLOB)
        return
    latest = csvs[-1]
    _logger.info("ynf_web: restoring x_ynf_* from %s", latest)

    Product = env["product.template"].sudo()
    restored = skipped = missing = 0
    with open(latest) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pid = int(row["id"])
            except (KeyError, ValueError):
                continue
            tmpl = Product.browse(pid).exists()
            if not tmpl:
                missing += 1
                continue
            vals = {}
            for col in ("x_ynf_inspired_by", "x_ynf_family", "x_ynf_image_url"):
                v = (row.get(col) or "").strip()
                if v and not getattr(tmpl, col, False):
                    vals[col] = v
            if vals:
                tmpl.write(vals)
                restored += 1
            else:
                skipped += 1
    _logger.info(
        "ynf_web: x_ynf restore done — restored=%s skipped=%s missing=%s",
        restored, skipped, missing,
    )
