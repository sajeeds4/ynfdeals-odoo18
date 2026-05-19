#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.company_db import get_product
from tools.attach_sds_batch_20260427_first10 import attach_paths, generate
from tools.enrich_inventory_batch_20260427_third10 import SEEDS


def main() -> int:
    artifacts = [generate(seed) for seed in SEEDS]
    attach_paths(artifacts)
    for item in artifacts:
        refreshed = get_product(item.product_id) or {}
        print(
            {
                "product_id": item.product_id,
                "barcode": item.barcode,
                "name": item.name,
                "pdf_path": str(item.pdf_path),
                "stored_path": refreshed.get("tiktok_sds_file_path"),
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
