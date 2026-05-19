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


REPORT_PATH = EXPORTS / "enrichment_batch_2026-04-27_remainder08_report.json"
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


LOOKUP = {product.get("barcode"): product for product in list_products()}


SEEDS: list[ProductSeed] = [
    ProductSeed(
        product_id=171,
        barcode="6291108326428",
        brand="Fragrance World",
        name="Fragrance World Barakkat Rouge 540 Extrait de Parfum Spray 100ml (3.4 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.4,
        size_ml=100,
        volume_oz=3.4,
        volume_ml=100,
        product_form="Extrait De Parfum",
        manufacturer="Fragrance World",
        description_intro="A rich unisex extrait de parfum with bitter almond and saffron up top, a jasmine-cedar core, and a warm woody musky ambergris finish.",
        top_notes="Bitter Almond, Saffron",
        mid_notes="Cedar, Jasmine",
        base_notes="Woody Notes, Ambergris, Musk",
        scent="Oriental woody amber musky",
        feature="extrait de parfum spray; unisex; 100ml / 3.4 oz",
        keywords="Fragrance World, Barakkat Rouge 540, Extrait De Parfum, Unisex, 100ml, 3.4 oz, Saffron, Bitter Almond, Jasmine, Ambergris",
        highlights=[
            "Extrait de parfum spray concentration.",
            "Unisex fragrance from Fragrance World.",
            "100 mL / 3.4 oz bottle size.",
            "Warm almond-saffron amber profile with strong statement wear character.",
        ],
        similar_to="Maison Francis Kurkdjian Baccarat Rouge 540 Extrait de Parfum",
        verified_note="Verified from Fragrantica and multiple retail listings tied to the barcode and 100ml format. BR540-extrait style oriental woody profile with bitter almond, saffron, jasmine, and musky woods; best for statement wear and shoppers specifically seeking this DNA.",
        source_official_url=None,
        source_jomashop_url=None,
        source_fragrantica_url="https://www.fragrantica.com/perfume/Fragrance-World/Barakkat-Rouge-540-Extrait-de-Parfum-107710.html",
        source_parfumo_url=None,
        image_sources=["https://fimgs.net/mdimg/perfume/375x500.107710.jpg"],
        ingredients=(LOOKUP["6291108326428"].get("ingredients") or DEFAULT_INGREDIENTS).strip(),
    ),
    ProductSeed(
        product_id=7,
        barcode="6291110112910",
        brand="Al Rehab",
        name="Al Rehab Cupcake Eau de Parfum Spray 100ml (3.33 oz) Unisex Perfume",
        gender="Unisex",
        size_oz=3.33,
        size_ml=100,
        volume_oz=3.33,
        volume_ml=100,
        product_form="Eau De Parfum",
        manufacturer="Al Rehab Perfumes",
        description_intro=extract_intro(LOOKUP["6291110112910"]),
        top_notes="Citrus, Amber",
        mid_notes="Vanilla",
        base_notes="Amber, Musk",
        scent=((LOOKUP["6291110112910"].get("tiktok_scent") or "Gourmand sweet vanilla").strip()),
        feature="eau de parfum spray; unisex; 100ml / 3.33 oz",
        keywords="Al Rehab, Cupcake, Eau De Parfum, Unisex, 100ml, 3.33 oz, Citrus, Amber, Vanilla, Musk",
        highlights=[
            "Eau de parfum spray concentration.",
            "Unisex fragrance from Al Rehab.",
            "100 mL / 3.33 oz bottle size.",
            "Sweet gourmand profile with vanilla and warm amber musk.",
        ],
        similar_to=None,
        verified_note="Completed from the product's existing verified note pyramid and internal product script, both aligned on the 100ml EDP format. This round fills the missing size, volume, and SDS structure without inventing new fragrance data.",
        source_official_url=(LOOKUP["6291110112910"].get("source_official_url") or None),
        source_jomashop_url=(LOOKUP["6291110112910"].get("source_jomashop_url") or None),
        source_fragrantica_url=(LOOKUP["6291110112910"].get("source_fragrantica_url") or None),
        source_parfumo_url=(LOOKUP["6291110112910"].get("source_parfumo_url") or None),
        image_sources=[],
        ingredients=(LOOKUP["6291110112910"].get("ingredients") or DEFAULT_INGREDIENTS).strip(),
    ),
    ProductSeed(
        product_id=228,
        barcode="6290362348085",
        brand="Lattafa Pride",
        name="Lattafa Pride 5 x 20ml Gift Set (Art of Arabia III Edition) 100ml (3.38 oz) Unisex Fragrance Set",
        gender="Unisex",
        size_oz=3.38,
        size_ml=100,
        volume_oz=3.38,
        volume_ml=100,
        product_form="Gift Set",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A five-piece mini fragrance gift set designed for discovery, travel, and gifting, featuring curated Lattafa Pride scents in 20ml spray bottles.",
        top_notes="Varies by included fragrance in the set",
        mid_notes="Varies by included fragrance in the set",
        base_notes="Varies by included fragrance in the set",
        scent="Mixed discovery set",
        feature="5 x 20ml eau de parfum sprays; unisex fragrance gift set; total 100ml",
        keywords="Lattafa Pride, Mini Gift Set, Art of Arabia III, Ajwaa, Al Qiam Gold, Masa, Brioche Vanille, 5x20ml",
        highlights=[
            "Gift set with five 20 mL mini fragrance sprays.",
            "Lattafa Pride unisex discovery-style set.",
            "Total fill volume 100 mL / 3.38 oz.",
            "Includes Art of Arabia III, Ajwaa, Al Qiam Gold, Masa, and Brioche Vanille.",
        ],
        similar_to=None,
        verified_note="Verified from retailer sources tied to the barcode. This is a mixed mini set rather than a single fragrance pyramid, making it best for gifting, sampling, travel, or trying multiple Lattafa Pride profiles without committing to full bottles.",
        source_official_url=None,
        source_jomashop_url="https://www.jomashop.com/lattafa-mini-set-gift-set-fragrances-6290362348085.html",
        source_fragrantica_url=None,
        source_parfumo_url=None,
        image_sources=[
            "https://cdn2.jomashop.com/media/catalog/product/cache/b3e31d40bbb1abcc90b26106659d5d3f/l/a/lattafa-mini-set-gift-set-fragrances-6290362348085.jpg?width=800&height=800",
        ],
        ingredients=(LOOKUP["6290362348085"].get("ingredients") or DEFAULT_INGREDIENTS).strip(),
    ),
    ProductSeed(
        product_id=217,
        barcode="6290362348061",
        brand="Lattafa",
        name="Lattafa Pride Mini Gift Set 100ml Total (Vintage Radio Edition) Unisex Fragrance Set",
        gender="Unisex",
        size_oz=3.38,
        size_ml=100,
        volume_oz=3.38,
        volume_ml=100,
        product_form="Gift Set",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A curated unisex mini fragrance set featuring five 20ml Lattafa Pride scents for travel, sampling, and gifting.",
        top_notes="Varies by included fragrance in the set",
        mid_notes="Varies by included fragrance in the set",
        base_notes="Varies by included fragrance in the set",
        scent="Mixed discovery set",
        feature="5 x 20ml eau de parfum sprays; unisex fragrance gift set; total 100ml",
        keywords="Lattafa Pride, Mini Gift Set, Vintage Radio, Shaheen Silver, African Drummer, Shuyukh Silver, Bike 1910, 5x20ml",
        highlights=[
            "Gift set with five 20 mL mini fragrance sprays.",
            "Unisex Lattafa Pride discovery-style set.",
            "Total fill volume 100 mL / 3.38 oz.",
            "Includes Bike 1910, Shaheen Silver, African Drummer, Shuyukh Silver, and Vintage Radio.",
        ],
        similar_to=None,
        verified_note="Verified from Lattafa UK and retailer mirrors tied to the barcode. This is a mixed mini set rather than one fragrance pyramid; best used as a discovery, travel, or gifting set with Bike 1910, Shaheen Silver, African Drummer, Shuyukh Silver, and Vintage Radio.",
        source_official_url="https://www.lattafasuk.com/p/lattafa-pride-5x20ml-giftset/",
        source_jomashop_url="https://www.jomashop.com/lattafa-mini-set-gift-set-fragrances-6290362348061.html",
        source_fragrantica_url=None,
        source_parfumo_url=None,
        image_sources=[
            "https://cdn2.jomashop.com/media/catalog/product/cache/0ee3019724ce73007b606b54ba535a23/l/a/lattafa-mini-set-gift-set-fragrances-6290362348061.jpg?width=546&height=546",
        ],
        ingredients=(LOOKUP["6290362348061"].get("ingredients") or DEFAULT_INGREDIENTS).strip(),
    ),
    ProductSeed(
        product_id=225,
        barcode="6290362348092",
        brand="Lattafa",
        name="Lattafa Pride Mini Gift Set 100ml Total (Nebras Edition) Unisex Fragrance Set",
        gender="Unisex",
        size_oz=3.38,
        size_ml=100,
        volume_oz=3.38,
        volume_ml=100,
        product_form="Gift Set",
        manufacturer="Lattafa Perfumes Industries L.L.C",
        description_intro="A curated unisex mini fragrance set featuring five 20ml Lattafa Pride scents for sampling, travel, and gifting.",
        top_notes="Varies by included fragrance in the set",
        mid_notes="Varies by included fragrance in the set",
        base_notes="Varies by included fragrance in the set",
        scent="Mixed discovery set",
        feature="5 x 20ml eau de parfum sprays; unisex fragrance gift set; total 100ml",
        keywords="Lattafa Pride, Mini Gift Set, Nebras, Art of Wood, Art of Universe, Ansaam Gold, Kashan, 5x20ml",
        highlights=[
            "Gift set with five 20 mL mini fragrance sprays.",
            "Unisex Lattafa Pride discovery-style set.",
            "Total fill volume 100 mL / 3.38 oz.",
            "Includes Nebras, Art of Wood, Art of Universe, Ansaam Gold, and Kashan.",
        ],
        similar_to=None,
        verified_note="Verified from retailer mirrors tied to the barcode. This is a mixed mini set rather than one fragrance pyramid; best used as a discovery, travel, or gifting set with Nebras, Art of Wood, Art of Universe, Ansaam Gold, and Kashan.",
        source_official_url=None,
        source_jomashop_url="https://www.jomashop.com/lattafa-mini-set-gift-set-fragrances-6290362348092.html",
        source_fragrantica_url=None,
        source_parfumo_url=None,
        image_sources=[
            "https://cdn2.jomashop.com/media/catalog/product/cache/0ee3019724ce73007b606b54ba535a23/l/a/lattafa-mini-set-gift-set-fragrances-6290362348092.jpg?width=546&height=546",
        ],
        ingredients=(LOOKUP["6290362348092"].get("ingredients") or DEFAULT_INGREDIENTS).strip(),
    ),
]


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
