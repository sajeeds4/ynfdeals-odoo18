from __future__ import annotations

import csv
import importlib.util
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
INVENTORY_PATH = EXPORTS / "inventory_dupe_research_full.csv"
FRAGRANCE_PATH = EXPORTS / "fragrance_houses_combined.csv"
SCRIPT_SOURCE = ROOT / "generate_scripts.py"
OUT_CSV = EXPORTS / "inventory_enrichment_master.csv"
OUT_JSON = EXPORTS / "inventory_enrichment_master.json"

SOURCE_LABELS = {
    "inventory_dupe_research_full.csv": "inventory_dupe_research_full.csv",
    "fragrance_houses_combined.csv": "fragrance_houses_combined.csv",
    "generate_scripts.py": "generate_scripts.py",
}

FRAGRANCE_BRANDS = {
    "Baccarat Rouge 540": "Maison Francis Kurkdjian",
    "Baccarat Rouge 540 Extrait": "Maison Francis Kurkdjian",
    "Bianco Latte": "Giardini di Toscana",
    "Burberry Goddess": "Burberry",
    "Creed Aventus": "Creed",
    "Creed Green Irish Tweed": "Creed",
    "Dior Sauvage": "Dior",
    "Dior Sauvage Elixir": "Dior",
    "Dolce & Gabbana Dolce": "Dolce & Gabbana",
    "Dolce & Gabbana My Devotion": "Dolce & Gabbana",
    "Eilish No. 1": "Billie Eilish",
    "Givenchy L'Interdit": "Givenchy",
    "Initio Oud for Greatness": "Initio",
    "Initio Paragon": "Initio",
    "Invictus": "Paco Rabanne",
    "Invictus Aqua 2016": "Paco Rabanne",
    "Jean Paul Gaultier Ultra Male": "Jean Paul Gaultier",
    "Louis Vuitton Pacific Chill": "Louis Vuitton",
    "Parfums de Marly Delina": "Parfums de Marly",
    "Parfums de Marly Sedley": "Parfums de Marly",
    "YSL Y EDP": "Yves Saint Laurent",
}

TARGET_AUDIENCE_RULES = [
    (re.compile(r"\bfor men\b|\bmen'?s\b|\bpour lui\b|\bfor man\b", re.I), "men"),
    (re.compile(r"\bfor women\b|\bwomen'?s\b|\bpour femme\b|\bladies\b|\bfor her\b", re.I), "women"),
    (re.compile(r"\bunisex\b|\bfor unisex\b|\bunisexe\b", re.I), "unisex"),
]

SEASON_KEYWORDS = {
    "summer": ["summer", "hot weather", "warm weather", "vacation", "tropical"],
    "winter": ["winter", "cold weather", "cozy", "cold nights"],
    "spring": ["spring"],
    "fall": ["fall", "autumn"],
    "all-season": ["all seasons", "year-round", "all year", "versatile across seasons"],
}

OCCASION_KEYWORDS = {
    "daily wear": ["daily wear", "everyday", "daily driver"],
    "office": ["office", "work"],
    "party": ["night out", "party", "club"],
    "date night": ["date night", "date-night", "evening", "seductive"],
    "luxury": ["luxury", "luxurious", "upscale"],
    "casual": ["casual"],
    "special occasion": ["special occasion", "special occasions"],
}

CATEGORY_KEYWORDS = {
    "gourmand": ["gourmand", "dessert", "caramel", "praline", "chocolate", "coffee", "marshmallow", "cacao", "sweet"],
    "fresh": ["fresh", "citrus", "aquatic", "oceanic", "marine", "clean", "mint", "blue"],
    "woody": ["woody", "woods", "cedar", "sandalwood", "oakmoss", "vetiver"],
    "oriental": ["oriental", "amber", "resin", "incense", "oud", "spicy"],
    "floral": ["floral", "rose", "jasmine", "orange blossom", "peony", "white flowers"],
    "fruity": ["fruity", "berry", "apple", "pear", "pineapple", "mango", "plum", "peach"],
    "musky": ["musk", "musky"],
    "aromatic": ["aromatic", "lavender", "sage", "herbal"],
}


def normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def title_or_unknown(value: str | None) -> str:
    cleaned = (value or "").strip()
    return cleaned if cleaned else "unknown"


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_scripts() -> dict[int, str]:
    spec = importlib.util.spec_from_file_location("generate_scripts_module", SCRIPT_SOURCE)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load scripts from {SCRIPT_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(getattr(module, "SCRIPTS", {}))


def parse_size_ml(name: str) -> str:
    text = name or ""
    ml_match = re.search(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML)\b", text)
    if ml_match:
        return str(int(round(float(ml_match.group(1)))))

    oz_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:(?:fl\.\s*)?oz|ounce|ounces)\b", text, re.I)
    if oz_match:
        ml = float(oz_match.group(1)) * 29.5735
        return str(int(round(ml)))
    return "unknown"


def extract_target_audience(name: str, description: str) -> tuple[str, str]:
    haystack = f"{name} {description}"
    for pattern, label in TARGET_AUDIENCE_RULES:
        if pattern.search(haystack):
            return label, "high"
    return "unknown", "low"


def extract_seasonality(text: str) -> tuple[str, str]:
    lowered = normalize(text)
    found = [season for season, keywords in SEASON_KEYWORDS.items() if any(k in lowered for k in keywords)]
    if not found:
        return "unknown", "low"
    if "all-season" in found:
        return "all-season", "high"
    ordered = [s for s in ("spring", "summer", "fall", "winter") if s in found]
    return ", ".join(ordered), "medium" if len(ordered) > 1 else "high"


def extract_occasions(text: str) -> tuple[str, str]:
    lowered = normalize(text)
    found = [occasion for occasion, keywords in OCCASION_KEYWORDS.items() if any(k in lowered for k in keywords)]
    if not found:
        return "unknown", "low"
    return ", ".join(found), "medium" if len(found) > 1 else "high"


def extract_fragrance_category(*texts: str) -> tuple[str, str]:
    lowered = " ".join(normalize(t) for t in texts if t)
    scores = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score:
            scores.append((score, category))
    if not scores:
        return "unknown", "low"
    scores.sort(reverse=True)
    categories = [category for _, category in scores[:3]]
    confidence = "high" if scores[0][0] >= 3 else "medium"
    return ", ".join(categories), confidence


def map_similarity_level(confidence: str, classification: str, inspiration_fragrance: str) -> str:
    if not inspiration_fragrance or inspiration_fragrance.startswith("Unconfirmed") or inspiration_fragrance.startswith("Unclear"):
        return "Low"
    lowered = normalize(classification)
    if "direct dupe" in lowered:
        return "High"
    if "close dupe" in lowered or confidence == "high":
        return "High"
    if confidence == "medium":
        return "Medium"
    return "Low"


def infer_inspiration_brand(inspiration_fragrance: str) -> str:
    if not inspiration_fragrance:
        return "unknown"
    for fragrance_name, brand in FRAGRANCE_BRANDS.items():
        if fragrance_name.lower() in inspiration_fragrance.lower():
            return brand
    if "Burberry Goddess" in inspiration_fragrance:
        return "Burberry"
    return "unknown"


def sentence_snippet(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return "unknown"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def build_sales_angle(row: dict[str, str]) -> tuple[str, str]:
    inspiration = row["inspiration_fragrance"]
    similarity = row["similarity_level"]
    category = row["fragrance_category"]
    if inspiration not in ("", "unknown") and not inspiration.startswith("Unconfirmed") and not inspiration.startswith("Unclear"):
        return f"Smells in the lane of {inspiration} for a much lower buy-in.", "medium"
    if category != "unknown":
        return f"Accessible {category} scent profile with strong live-sell appeal.", "low"
    return "unknown", "low"


def build_storytelling_script(existing_script: str) -> tuple[str, str]:
    script = re.sub(r"\s+", " ", (existing_script or "").replace("\n", " ")).strip()
    if not script:
        return "unknown", "low"
    return sentence_snippet(script, 320), "high"


def build_comparison_strategy(row: dict[str, str]) -> tuple[str, str]:
    inspiration = row["inspiration_fragrance"]
    level = row["similarity_level"]
    if inspiration not in ("", "unknown") and not inspiration.startswith("Unconfirmed") and not inspiration.startswith("Unclear"):
        return f"Compare against {inspiration} and frame it as a {level.lower()}-confidence alternative.", "medium"
    category = row["fragrance_category"]
    if category != "unknown":
        return f"Compare within the {category} lane instead of making an exact-dupe claim.", "low"
    return "unknown", "low"


def build_urgency(row: dict[str, str]) -> tuple[str, str]:
    qty = int(float(row["on_hand_qty"] or 0))
    parts = []
    confidence = "medium"
    if qty <= 3:
        parts.append(f"Low live stock: only {qty} on hand.")
    elif qty <= 10:
        parts.append(f"Limited live stock: {qty} on hand.")
    if row["similarity_level"] == "High":
        parts.append("Strong dupe/value angle can move quickly in live streams.")
    if not parts:
        return "Current inventory is available, but no strong urgency trigger is confirmed yet.", "low"
    return " ".join(parts), confidence


def token_set(*texts: str) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        for token in re.findall(r"[a-z0-9]+", normalize(text)):
            if len(token) > 2:
                tokens.add(token)
    return tokens


def choose_bundles(rows: list[dict[str, str]]) -> dict[str, str]:
    enriched = {}
    product_tokens = {
        row["product_id"]: token_set(
            row["brand"],
            row["fragrance_category"],
            row["inspiration_fragrance"],
            row["top_notes"],
            row["middle_notes"],
            row["base_notes"],
            row["fragrance_notes_summary"],
        )
        for row in rows
    }

    for row in rows:
        pid = row["product_id"]
        current_tokens = product_tokens[pid]
        scored = []
        for other in rows:
            if other["product_id"] == pid:
                continue
            overlap = current_tokens & product_tokens[other["product_id"]]
            if not overlap:
                continue
            score = len(overlap)
            if row["brand"] == other["brand"]:
                score += 2
            scored.append((score, other["product_name"]))
        scored.sort(key=lambda item: (-item[0], item[1]))
        enriched[pid] = " | ".join(name for _, name in scored[:3]) if scored else "unknown"
    return enriched


def summarize_missing_fields(row: dict[str, str], fields: Iterable[str]) -> str:
    missing = [field for field in fields if row.get(field, "unknown") in ("", "unknown")]
    return ", ".join(missing) if missing else "none"


def summarize_low_confidence(row: dict[str, str], confidence_fields: dict[str, str]) -> str:
    low_fields = [field for field, value in confidence_fields.items() if value == "low"]
    return ", ".join(low_fields) if low_fields else "none"


def build_master_rows() -> list[dict[str, str]]:
    inventory_rows = load_csv(INVENTORY_PATH)
    fragrance_rows = {row["id"]: row for row in load_csv(FRAGRANCE_PATH)}
    scripts = load_scripts()

    master_rows: list[dict[str, str]] = []
    for inventory in inventory_rows:
        pid = inventory["product_id"]
        fragrance = fragrance_rows.get(pid, {})
        existing_script = scripts.get(int(pid), "") if pid.isdigit() else ""

        description = fragrance.get("description", "") or ""
        note_top = fragrance.get("note_top", "") or "unknown"
        note_mid = fragrance.get("note_mid", "") or "unknown"
        note_base = fragrance.get("note_base", "") or "unknown"
        fragrance_notes = fragrance.get("notes", "") or "unknown"
        inspiration = inventory.get("inspiration_fragrance", "") or "unknown"
        similarity_confidence = (inventory.get("confidence", "") or "low").replace("low-medium", "medium")
        similarity_level = map_similarity_level(similarity_confidence, inventory.get("classification", ""), inspiration)
        inspiration_brand = infer_inspiration_brand(inspiration)
        size_ml = parse_size_ml(inventory["product_name"])
        audience, audience_confidence = extract_target_audience(inventory["product_name"], description)
        category, category_confidence = extract_fragrance_category(
            fragrance_notes,
            description,
            note_top,
            note_mid,
            note_base,
            inventory.get("classification", ""),
        )
        seasonality, seasonality_confidence = extract_seasonality(description)
        occasion, occasion_confidence = extract_occasions(description + " " + existing_script)
        storytelling_script, storytelling_confidence = build_storytelling_script(existing_script)

        row = {
            "product_id": pid,
            "product_name": inventory["product_name"],
            "brand": inventory["brand"] or "unknown",
            "category": inventory["category"] or "unknown",
            "sku": inventory["sku"] or "unknown",
            "barcode": inventory["barcode"] or "unknown",
            "size_ml": size_ml,
            "cost_price_usd": inventory["cost_price"] or "unknown",
            "our_retail_price_usd": inventory["retail_price"] or "unknown",
            "on_hand_qty": inventory["on_hand_qty"] or "0",
            "active": inventory["active"] or "0",
            "top_notes": note_top,
            "middle_notes": note_mid,
            "base_notes": note_base,
            "fragrance_notes_summary": fragrance_notes,
            "fragrance_description": description or "unknown",
            "inspiration_fragrance": inspiration,
            "inspiration_brand": inspiration_brand,
            "similarity_level": similarity_level,
            "similarity_confidence": similarity_confidence or "low",
            "dupe_classification": inventory.get("classification", "") or "unknown",
            "similarity_explanation": inventory.get("notes", "") or "unknown",
            "target_audience": audience,
            "seasonality": seasonality,
            "occasion": occasion,
            "fragrance_category": category,
            "official_price_usd": "unknown",
            "official_size_ml": "unknown",
            "official_availability": "unknown",
            "official_seller_type": "official",
            "official_source_url": "unknown",
            "retailer_price_usd": "unknown",
            "retailer_size_ml": "unknown",
            "retailer_availability": "unknown",
            "retailer_seller_type": "unknown",
            "retailer_source_url": "unknown",
            "discount_price_usd": "unknown",
            "discount_size_ml": "unknown",
            "discount_availability": "unknown",
            "discount_seller_type": "unknown",
            "discount_source_url": "unknown",
            "amazon_price_usd": "unknown",
            "amazon_size_ml": "unknown",
            "amazon_availability": "unknown",
            "amazon_seller_type": "unknown",
            "amazon_source_url": "unknown",
            "sales_angle": "unknown",
            "storytelling_script": storytelling_script,
            "comparison_strategy": "unknown",
            "urgency_triggers": "unknown",
            "bundle_suggestions": "unknown",
            "needs_smell_test": inventory.get("needs_smell_test", "") or "unknown",
            "research_sources": " | ".join(
                source
                for source in [
                    SOURCE_LABELS["inventory_dupe_research_full.csv"],
                    SOURCE_LABELS["fragrance_houses_combined.csv"] if fragrance else "",
                    SOURCE_LABELS["generate_scripts.py"] if existing_script else "",
                ]
                if source
            ),
        }

        sales_angle, sales_confidence = build_sales_angle(row)
        comparison_strategy, comparison_confidence = build_comparison_strategy(row)
        urgency, urgency_confidence = build_urgency(row)
        row["sales_angle"] = sales_angle
        row["comparison_strategy"] = comparison_strategy
        row["urgency_triggers"] = urgency
        row["_confidence_map"] = {
            "top_notes": "high" if note_top != "unknown" else "low",
            "middle_notes": "high" if note_mid != "unknown" else "low",
            "base_notes": "high" if note_base != "unknown" else "low",
            "inspiration_analysis": "high" if similarity_confidence == "high" else ("medium" if similarity_confidence == "medium" else "low"),
            "target_audience": audience_confidence,
            "seasonality": seasonality_confidence,
            "occasion": occasion_confidence,
            "fragrance_category": category_confidence,
            "sales_angle": sales_confidence,
            "storytelling_script": storytelling_confidence,
            "comparison_strategy": comparison_confidence,
            "urgency_triggers": urgency_confidence,
            "market_pricing": "low",
        }
        master_rows.append(row)

    bundle_map = choose_bundles(master_rows)
    for row in master_rows:
        row["bundle_suggestions"] = bundle_map[row["product_id"]]
        row["missing_fields"] = summarize_missing_fields(
            row,
            [
                "top_notes",
                "middle_notes",
                "base_notes",
                "official_price_usd",
                "retailer_price_usd",
                "discount_price_usd",
                "amazon_price_usd",
                "seasonality",
                "occasion",
            ],
        )
        row["low_confidence_fields"] = summarize_low_confidence(row, row["_confidence_map"])
        row["market_pricing_status"] = "pending_live_web_research"
        row["notes_source_confidence"] = row["_confidence_map"]["top_notes"]
        row["positioning_confidence"] = max(
            [row["_confidence_map"]["target_audience"], row["_confidence_map"]["fragrance_category"]],
            key=lambda value: {"low": 0, "medium": 1, "high": 2}[value],
        )
        del row["_confidence_map"]

    return master_rows


def write_outputs(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError("No rows to write")
    fieldnames = list(rows[0].keys())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with OUT_JSON.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=True)


def print_summary(rows: list[dict[str, str]]) -> None:
    counts = Counter()
    for row in rows:
        if row["top_notes"] != "unknown":
            counts["with_note_pyramid"] += 1
        if row["inspiration_fragrance"] not in ("unknown", ""):
            counts["with_inspiration_label"] += 1
        if row["storytelling_script"] != "unknown":
            counts["with_storytelling_script"] += 1
        if row["seasonality"] != "unknown":
            counts["with_seasonality"] += 1
        if row["occasion"] != "unknown":
            counts["with_occasion"] += 1
    print(f"wrote {len(rows)} rows")
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    print(OUT_CSV)
    print(OUT_JSON)


def main() -> None:
    rows = build_master_rows()
    write_outputs(rows)
    print_summary(rows)


if __name__ == "__main__":
    main()
