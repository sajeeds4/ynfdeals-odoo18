from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
INVENTORY_CSV = EXPORTS / "inventory_enrichment_web.csv"
OUT_CSV = EXPORTS / "parfumo_match_candidates.csv"
OUT_JSON = EXPORTS / "parfumo_match_candidates.json"

PARFUMO_BASE = "https://www.parfumo.com/Perfumes"
PARFUMO_SEARCH = "https://www.parfumo.com/s_perfumes_x.php?in={query}&filter="

BRAND_SLUG_ALIASES = {
    "afnan": ["afnan-perfumes", "afnan"],
    "al haramain": ["al-haramain", "al-haramain-perfumes"],
    "al rehab": ["al-rehab", "crown-perfumes"],
    "amwaaj": ["amwaaj"],
    "armaf": ["armaf"],
    "fragrance world": ["fragrance-world", "french-avenue", "fa-paris"],
    "generic": [],
    "jovan": ["jovan"],
    "lattafa": ["lattafa", "lattafa-pride"],
    "lattafa perfume": ["lattafa", "lattafa-pride"],
    "maison alhambra": ["maison-alhambra"],
    "nautica": ["nautica"],
    "rasasi": ["rasasi"],
}

TRAILING_DESCRIPTORS = [
    r"\bfor men\b",
    r"\bfor women\b",
    r"\bfor unisex\b",
    r"\bmen'?s\b",
    r"\bwomen'?s\b",
    r"\bunisex\b",
    r"\beau de parfum\b",
    r"\beau de toilette\b",
    r"\bextrait de parfum\b",
    r"\bperfume oil\b",
    r"\bperfume spray\b",
    r"\bedp spray\b",
    r"\bedp\b",
    r"\bedt\b",
    r"\bspray\b",
    r"\bcologne\b",
    r"\bfragrances?\b",
    r"\blong-lasting fragrance\b",
    r"\btester\b",
    r"\bby [a-z0-9&' .-]+\b",
    r"\b\d+(?:\.\d+)?\s*(?:ml|mL|ML)\b",
    r"\b\d+(?:\.\d+)?\s*(?:fl\.?\s*oz|oz|ounce|ounces)\b",
    r"\(\s*[^)]*(?:ml|oz|barcode|UPC)[^)]*\)",
]

LEADING_BRAND_NOISE = [
    r"^lattafa maison alhambra\s+",
    r"^lattafa pride\s+",
    r"^lattafa perfum(?:e|es)?\s+",
    r"^lattafa\s+",
    r"^maison alhambra\s+",
    r"^al rehab\s+",
    r"^afnan\s+",
    r"^armaf\s+",
    r"^rasasi\s+",
    r"^amwaaj\s+",
    r"^fragrance world\s+",
    r"^al haramain\s+",
]


def load_inventory() -> list[dict[str, str]]:
    with INVENTORY_CSV.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_inventory_prefix(name: str) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", name).strip()


def clean_product_name(name: str) -> str:
    text = strip_inventory_prefix(name)
    text = text.replace("&", " and ")
    text = text.replace("'", "")
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"\b\d{12,14}\b", " ", text)
    for pattern in LEADING_BRAND_NOISE:
        text = re.sub(pattern, "", text, flags=re.I)
    for pattern in TRAILING_DESCRIPTORS:
        text = re.sub(pattern, " ", text, flags=re.I)
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"[,/|]+", " ", text)
    text = re.sub(r"[-–—]+", " ", text)
    text = re.sub(r"[()]+", " ", text)
    text = re.sub(r"(?:^|\s)[^A-Za-z0-9]+(?=\s|$)", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -_,")
    return normalize_spaces(text)


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def normalize_brand(brand: str) -> str:
    return normalize_spaces((brand or "").lower())


def candidate_brand_slugs(brand: str, product_name: str) -> list[str]:
    brand_key = normalize_brand(brand)
    candidates = list(BRAND_SLUG_ALIASES.get(brand_key, [slugify(brand_key)] if brand_key else []))

    lowered = product_name.lower()
    if "pride" in lowered and "lattafa-pride" not in candidates:
        candidates.insert(0, "lattafa-pride")
    if "maison alhambra" in lowered and "maison-alhambra" not in candidates:
        candidates.insert(0, "maison-alhambra")
    if "french avenue" in lowered and "french-avenue" not in candidates:
        candidates.insert(0, "french-avenue")

    seen = set()
    ordered = []
    for slug in candidates:
        if slug and slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    return ordered


def build_candidates(row: dict[str, str]) -> dict[str, str]:
    product_name = normalize_spaces(row.get("product_name") or "")
    brand = normalize_spaces(row.get("brand") or "")
    cleaned_name = clean_product_name(product_name)
    product_slug = slugify(cleaned_name or product_name)
    brand_slugs = candidate_brand_slugs(brand, product_name)
    primary_brand_slug = brand_slugs[0] if brand_slugs else ""

    alternate_urls = [f"{PARFUMO_BASE}/{brand_slug}/{product_slug}" for brand_slug in brand_slugs]
    confidence = "medium" if primary_brand_slug and product_slug else "low"
    if "lattafa-pride" in brand_slugs or "maison-alhambra" in brand_slugs:
        confidence = "medium-high"
    if brand.lower() in {"amwaaj", "armaf", "rasasi", "afnan"} and product_slug:
        confidence = "high"

    notes = []
    if strip_inventory_prefix(product_name) != cleaned_name:
        notes.append("removed_inventory_sku_prefix")
    if cleaned_name != product_name:
        notes.append("trimmed_sizes_and_descriptors")
    if len(brand_slugs) > 1:
        notes.append("multiple_brand_slug_candidates")
    if not primary_brand_slug:
        notes.append("brand_slug_unknown")
    if not product_slug:
        notes.append("product_slug_unknown")

    search_query = quote_plus(f"{brand} {cleaned_name or product_name}".strip())

    return {
        "product_id": row.get("product_id") or "",
        "product_name": product_name,
        "brand": brand,
        "barcode": row.get("barcode") or "",
        "cleaned_product_name": cleaned_name,
        "product_slug": product_slug,
        "primary_brand_slug": primary_brand_slug,
        "parfumo_url_candidate": alternate_urls[0] if alternate_urls else "",
        "alternate_parfumo_urls": " | ".join(alternate_urls[1:]),
        "parfumo_search_url": PARFUMO_SEARCH.format(query=search_query),
        "match_confidence": confidence,
        "matcher_notes": " | ".join(notes),
    }


def main() -> None:
    rows = load_inventory()
    candidates = [build_candidates(row) for row in rows]
    candidates.sort(key=lambda item: (item["brand"].lower(), item["product_name"].lower()))

    fieldnames = [
        "product_id",
        "product_name",
        "brand",
        "barcode",
        "cleaned_product_name",
        "product_slug",
        "primary_brand_slug",
        "parfumo_url_candidate",
        "alternate_parfumo_urls",
        "parfumo_search_url",
        "match_confidence",
        "matcher_notes",
    ]

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)

    with OUT_JSON.open("w", encoding="utf-8") as handle:
        json.dump(candidates, handle, indent=2, ensure_ascii=False)

    print(f"Wrote {len(candidates)} rows to {OUT_CSV}")
    print(f"Wrote {len(candidates)} rows to {OUT_JSON}")


if __name__ == "__main__":
    main()
