#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.company_db import get_product, list_products  # noqa: E402
from tools.enrich_inventory_batch_20260427_third10 import (  # noqa: E402
    EXPORTS,
    ProductSeed,
    update_product,
)


REPORT_PATH = EXPORTS / "enrichment_batch_2026-04-27_remainder06_report.json"
DEFAULT_INGREDIENTS = "Alcohol Denat., Parfum (Fragrance), Aqua (Water), fragrance compounds, fixatives, and stabilizers."


def extract_intro(current: dict) -> str:
    description = (current.get("description") or "").strip()
    if not description:
        top = (current.get("note_top") or "").strip().rstrip(".")
        mid = (current.get("note_mid") or "").strip().rstrip(".")
        base = (current.get("note_base") or "").strip().rstrip(".")
        return (
            f"{current.get('name') or 'This fragrance'} opens with {top.lower()}, "
            f"moves into {mid.lower()}, and settles into {base.lower()}."
        )
    parts = [part.strip() for part in re.split(r"\n\s*\n", description) if part.strip()]
    for part in parts:
        low = part.lower()
        if low.startswith("top notes:") or low.startswith("middle notes:") or low.startswith("base notes:"):
            continue
        if low.startswith("verified:"):
            continue
        if re.match(r"^[A-Za-z0-9 .&'/-]+\d+\s*ml", part, flags=re.IGNORECASE):
            continue
        return part
    return description.splitlines()[0].strip()


def normalize_gender(value: str | None, fallback: str) -> str:
    text = (value or "").strip().lower()
    if text in {"women", "woman", "female"}:
        return "Women"
    if text in {"men", "man", "male"}:
        return "Men"
    if text in {"unisex"}:
        return "Unisex"
    return fallback


def make_verified_note(current: dict, size_ml: int, size_oz: float) -> str:
    return (
        "Completion pass using the product's existing verified note pyramid and the "
        f"exact title-backed {size_ml}ml / {size_oz} oz format. This round fills the "
        "missing size, volume, and SDS structure without inventing new fragrance data."
    )


LOOKUP = {product.get("barcode"): product for product in list_products()}


SPECS = [
    {"barcode": "6281110001703", "size_ml": 50, "size_oz": 1.7, "gender": "Women", "manufacturer": "Al Rehab Perfumes", "product_form": "Eau De Parfum"},
    {"barcode": "6291110101457", "size_ml": 50, "size_oz": 1.65, "gender": "Unisex", "manufacturer": "Al Rehab Perfumes", "product_form": "Eau De Parfum"},
    {"barcode": "6281110001680", "size_ml": 50, "size_oz": 1.7, "gender": "Men", "manufacturer": "Al Rehab Perfumes", "product_form": "Eau De Parfum"},
    {"barcode": "6291100131716", "size_ml": 60, "size_oz": 2.0, "gender": "Unisex", "manufacturer": "Al Haramain Perfumes LLC", "product_form": "Eau De Parfum"},
    {"barcode": "6085010094151", "size_ml": 106, "size_oz": 3.6, "gender": "Women", "manufacturer": "Armaf Perfumes", "product_form": "Eau De Parfum"},
    {"barcode": "6085010044712", "size_ml": 106, "size_oz": 3.6, "gender": "Men", "manufacturer": "Armaf Perfumes", "product_form": "Eau De Toilette"},
    {"barcode": "6294015188622", "size_ml": 100, "size_oz": 3.4, "gender": "Women", "manufacturer": "Armaf Perfumes", "product_form": "Eau De Parfum"},
    {"barcode": "6291107456355", "size_ml": 100, "size_oz": 3.4, "gender": "Women", "manufacturer": "Lattafa Perfumes Industries L.L.C", "product_form": "Eau De Parfum"},
    {"barcode": "6290362345183", "size_ml": 100, "size_oz": 3.4, "gender": "Unisex", "manufacturer": "Lattafa Perfumes Industries L.L.C", "product_form": "Eau De Parfum"},
    {"barcode": "6291110101440", "size_ml": 50, "size_oz": 1.65, "gender": "Men", "manufacturer": "Al Rehab Perfumes", "product_form": "Eau De Parfum"},
]


SEEDS: list[ProductSeed] = []
for spec in SPECS:
    current = LOOKUP[spec["barcode"]]
    brand = (current.get("brand") or "").strip()
    name = (current.get("name") or "").strip()
    gender = normalize_gender(current.get("gender"), spec["gender"])
    top = (current.get("note_top") or "").strip()
    mid = (current.get("note_mid") or "").strip()
    base = (current.get("note_base") or "").strip()
    feature = f"{spec['product_form'].lower()} spray; {gender.lower()}; {spec['size_ml']}ml / {spec['size_oz']} oz"
    keywords = ", ".join(
        filter(
            None,
            [
                brand,
                name.split(" Spray ")[0].replace("  ", " ").strip(),
                spec["product_form"],
                gender,
                f"{spec['size_ml']}ml",
                f"{spec['size_oz']} oz",
            ],
        )
    )
    highlights = [
        f"{spec['product_form']} spray concentration.",
        f"{gender}'s fragrance from {brand}." if gender != "Unisex" else f"Unisex fragrance from {brand}.",
        f"{spec['size_ml']} mL / {spec['size_oz']} oz bottle size.",
        "Existing verified note pyramid preserved during structural completion.",
    ]
    SEEDS.append(
        ProductSeed(
            product_id=current["id"],
            barcode=spec["barcode"],
            brand=brand,
            name=name,
            gender=gender,
            size_oz=spec["size_oz"],
            size_ml=spec["size_ml"],
            volume_oz=spec["size_oz"],
            volume_ml=spec["size_ml"],
            product_form=spec["product_form"],
            manufacturer=spec["manufacturer"],
            description_intro=extract_intro(current),
            top_notes=top,
            mid_notes=mid,
            base_notes=base,
            scent=((current.get("tiktok_scent") or "") or "Fragrance").strip(),
            feature=feature,
            keywords=keywords,
            highlights=highlights,
            similar_to=(current.get("similar_to") or None),
            verified_note=make_verified_note(current, spec["size_ml"], spec["size_oz"]),
            source_official_url=(current.get("source_official_url") or None),
            source_jomashop_url=(current.get("source_jomashop_url") or None),
            source_fragrantica_url=(current.get("source_fragrantica_url") or None),
            source_parfumo_url=(current.get("source_parfumo_url") or None),
            image_sources=[],
            package_weight_oz=current.get("tiktok_package_weight_oz"),
            ingredients=(current.get("ingredients") or current.get("tiktok_ingredients") or DEFAULT_INGREDIENTS).strip(),
        )
    )


def main() -> int:
    results = []
    for seed in SEEDS:
        updated = update_product(seed)
        refreshed = get_product(seed.product_id) or {}
        results.append(
            {
                "product_id": seed.product_id,
                "barcode": seed.barcode,
                "name": updated.get("name"),
                "gender": updated.get("gender"),
                "size_oz": refreshed.get("size_oz"),
                "size_ml": refreshed.get("size_ml"),
                "volume_oz": refreshed.get("volume_oz"),
                "volume_ml": refreshed.get("volume_ml"),
                "media_url": refreshed.get("media_url"),
            }
        )
    REPORT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
