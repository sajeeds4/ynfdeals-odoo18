#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.enrich_inventory_batch_20260427_third10 import (  # noqa: E402
    EXPORTS,
    ProductSeed,
    update_product,
)


REPORT_PATH = EXPORTS / "enrichment_batch_2026-04-27_final2_report.json"


SEEDS: list[ProductSeed] = [
    ProductSeed(
        product_id=130,
        barcode="614514331040",
        brand="Rasasi",
        name="Rasasi Hawas Ice Eau de Parfum Spray 100ml (3.38 oz) Men Perfume",
        gender="Men",
        size_oz=3.38,
        size_ml=100,
        volume_oz=3.38,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Rasasi Perfumes Industry LLC",
        description_intro="A bright men's eau de parfum with crisp apple and citrus on top, an icy marine-fruity heart, and a musky ambered woody base.",
        top_notes="Apple, Italian Lemon, Sicilian Bergamot, Star Anise",
        mid_notes="Plum, Orange Blossom, Cardamom, Marine Notes, Ice Accord",
        base_notes="Musk, Amber, Driftwood, Moss",
        scent="Fresh fruity aquatic sweet",
        feature="eau de parfum spray; men; 100ml / 3.38 oz",
        keywords="Rasasi, Hawas Ice, Eau De Parfum, Men, 100ml, 3.38 oz, Apple, Bergamot, Marine, Musk",
        highlights=[
            "Eau de parfum spray concentration.",
            "Men's fragrance from Rasasi's Hawas line.",
            "100 mL / 3.38 oz bottle size.",
            "Fresh fruity-aquatic profile with musky woody drydown.",
        ],
        similar_to="Rabanne Invictus Aqua (2018) / Invictus",
        verified_note="Verified from Fragrantica, Parfumo, and Jomashop support. Source-backed wear guidance points to warm-weather, daytime, gym, and easy mass-appeal use, with community similarity repeatedly landing near Invictus Aqua territory.",
        source_official_url=None,
        source_jomashop_url="https://www.jomashop.com/rasasi-hawas-ice-mens-edp.html",
        source_fragrantica_url="https://www.fragrantica.com/perfume/Rasasi/Hawas-Ice-89050.html",
        source_parfumo_url="https://www.parfumo.com/Perfumes/Rasasi/hawas-ice",
        image_sources=[
            "https://cdn2.jomashop.com/media/catalog/product/cache/0ee3019724ce73007b606b54ba535a23/r/a/rasasi-mens-hawas-ice-eau-de-perfume-spray-338-oz-fragrances-614514331040_2.jpg?width=546&height=546",
            "https://fimgs.net/mdimg/perfume/375x500.89050.jpg",
        ],
        official_discrepancy_note="Fragrantica and Parfumo align on the general fruity-fresh aquatic structure, while Parfumo includes explicit marine and ice accords in the heart. The saved pyramid preserves the overlapping core and retains those accords conservatively.",
    ),
    ProductSeed(
        product_id=134,
        barcode="6290360593685",
        brand="Lattafa",
        name="Lattafa Rave Now Pink Eau de Parfum Spray 100ml (3.4 oz) Women Perfume",
        gender="Women",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A playful women's eau de parfum with red fruits and orange on top, a marshmallow-floral heart, and a sweet vanilla-musk base.",
        top_notes="Red Fruits, Orange",
        mid_notes="Marshmallow, Lily of the Valley, Jasmine",
        base_notes="Vanilla, Moss, Musk",
        scent="Fruity floral sweet musky",
        feature="eau de parfum spray; women; 100ml / 3.4 oz",
        keywords="Lattafa, Rave Now Pink, Eau De Parfum, Women, 100ml, 3.4 oz, Red Fruits, Marshmallow, Jasmine, Vanilla",
        highlights=[
            "Eau de parfum spray concentration.",
            "Women's fragrance from Lattafa's Rave line.",
            "100 mL / 3.4 oz bottle size.",
            "Sweet fruity-floral profile with marshmallow and vanilla warmth.",
        ],
        similar_to=None,
        verified_note="Verified from exact-barcode retailer listings and multiple exact-match product pages. Public fragrance-reference coverage is weak on this barcode, so the saved pyramid follows the barcode-matched retailer consensus rather than forcing unsupported clone or comparison claims.",
        source_official_url=None,
        source_jomashop_url="https://www.jomashop.com/lattafa-ladies-rave-pink-edp-spray-3-4-oz-fragrances-6290360593685.html",
        source_fragrantica_url=None,
        source_parfumo_url=None,
        image_sources=[
            "https://encrypted-tbn2.gstatic.com/shopping?q=tbn:ANd9GcTFp_y0bUGg3Sqr_XDMvD91VVkBQBzVhqNpAqieq9-Be5mFNl-sqPZO8AMgDIrz2JZhXP0Y3jcHHrETGIT483-YdTMIb7xgBuCKfQWirOcdlM86-VFw9BKFYA",
        ],
        official_discrepancy_note="This release is sold under both 'Rave Now Pink' and 'Now Women' naming across exact-barcode retailer pages. The saved identity keeps the clearer Rave Now Pink naming while preserving the shared barcode-backed note pyramid.",
    ),
]


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results = [update_product(seed) for seed in SEEDS]
    REPORT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
