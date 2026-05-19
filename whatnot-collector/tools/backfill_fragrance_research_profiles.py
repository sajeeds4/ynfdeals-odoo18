#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.company_db import list_products, set_product_fragrance_research


ACCORD_KEYWORDS = (
    "woody", "amber", "warm spicy", "spicy", "fresh spicy", "sweet", "fruity", "citrus",
    "powdery", "aromatic", "fresh", "vanilla", "gourmand", "musky", "musk", "leathery",
    "floral", "white floral", "rose", "aquatic", "marine", "green", "smoky", "oud",
    "balsamic", "earthy", "patchouli", "coconut", "coffee", "caramel", "chocolate"
)
SEASON_KEYWORDS = ("spring", "summer", "fall", "autumn", "winter")
OCCASION_KEYWORDS = ("party", "date", "office", "formal", "evening", "night out", "daily", "everyday", "special occasion")
TIME_KEYWORDS = ("day", "night")


def normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_multiline(value) -> str:
    text = str(value or "").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def sentence_chunks(text: str) -> list[str]:
    clean = normalize_multiline(text)
    if not clean:
        return []
    return [
        chunk.strip()
        for chunk in re.split(r"(?<=[.!?])\s+|\n+", clean)
        if chunk and chunk.strip()
    ]


def keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    haystack = f" {normalize_text(text).lower()} "
    found = []
    for keyword in keywords:
        needle = keyword.lower()
        if f" {needle} " in haystack:
            found.append(keyword.title() if keyword != "night out" else "Night out")
    return list(OrderedDict.fromkeys(found))


def extract_sentence(texts: list[str], needles: tuple[str, ...]) -> str:
    lowered_needles = tuple(item.lower() for item in needles)
    for text in texts:
        for sentence in sentence_chunks(text):
            sentence_lower = sentence.lower()
            if any(needle in sentence_lower for needle in lowered_needles):
                return sentence
    return ""


def extract_accords(product: dict) -> str:
    scent = normalize_text(product.get("tiktok_scent"))
    if scent:
        return scent
    combined = " ".join(
        normalize_text(product.get(field))
        for field in ("notes", "description", "dupe_notes", "similar_to", "dupe_inspiration")
    )
    found = keyword_hits(combined, ACCORD_KEYWORDS)
    return ", ".join(found[:8])


def extract_family(accords: str) -> str:
    if not accords:
        return ""
    parts = [item.strip() for item in accords.split(",") if item.strip()]
    return ", ".join(parts[:3])


def build_sources(product: dict, source_summary: str, captured_at: str) -> list[dict]:
    sources = []
    mapping = (
        ("source_official_url", "official", "Official"),
        ("source_jomashop_url", "retailer", "Jomashop"),
        ("source_parfumo_url", "community", "Parfumo"),
        ("source_fragrantica_url", "community", "Fragrantica"),
    )
    for field_name, source_type, label in mapping:
        url = normalize_text(product.get(field_name))
        if not url:
            continue
        sources.append(
            {
                "source_type": source_type,
                "source_label": label,
                "source_url": url,
                "evidence_kind": "reference_url",
                "evidence_excerpt": source_summary[:500] if source_summary else "",
                "captured_at": captured_at,
            }
        )
    if source_summary:
        sources.append(
            {
                "source_type": "internal_verified_note",
                "source_label": "Existing verified inventory note",
                "source_url": "",
                "evidence_kind": "source_summary",
                "evidence_excerpt": source_summary[:1000],
                "captured_at": captured_at,
            }
        )
    return sources


def main() -> int:
    products = list_products(active_only=False, low_stock_only=False)
    captured_at = datetime.now(timezone.utc).isoformat()
    updated = []
    manual_review = []

    for product in products:
        product_id = int(product["id"])
        texts = [
            normalize_multiline(product.get("notes")),
            normalize_multiline(product.get("description")),
            normalize_multiline(product.get("dupe_notes")),
        ]
        combined = " ".join(texts)
        seasons = keyword_hits(combined, SEASON_KEYWORDS)
        occasions = keyword_hits(combined, OCCASION_KEYWORDS)
        times = keyword_hits(combined, TIME_KEYWORDS)
        accords = extract_accords(product)
        source_summary = " ".join(sentence_chunks(product.get("notes"))[:2]) or " ".join(sentence_chunks(product.get("description"))[:2])
        external_source_count = sum(
            1 for field_name in ("source_official_url", "source_jomashop_url", "source_parfumo_url", "source_fragrantica_url")
            if normalize_text(product.get(field_name))
        )
        confidence = "high" if external_source_count >= 3 and source_summary else "medium" if external_source_count >= 2 else "low"
        needs_manual = int(
            external_source_count < 2
            and not source_summary
            and not normalize_text(product.get("similar_to"))
            and not normalize_text(product.get("dupe_inspiration"))
        )

        payload = {
            "accords": accords,
            "fragrance_family": extract_family(accords),
            "fragrance_dna": extract_sentence(texts, ("dna", "signature", "profile", "vibe", "style")),
            "best_for_seasons": ", ".join(seasons),
            "best_for_occasions": ", ".join(occasions),
            "best_for_time_of_day": ", ".join(times),
            "longevity": extract_sentence(texts, ("longevity", "long-lasting", "lasting")),
            "projection": extract_sentence(texts, ("projection", "projects", "stronger projection")),
            "sillage": extract_sentence(texts, ("sillage",)),
            "compliment_factor": extract_sentence(texts, ("compliment", "crowd pleasing", "crowd-pleasing")),
            "mood_keywords": ", ".join(keyword_hits(combined, ("cozy", "polished", "playful", "fresh", "bold", "sweet", "romantic", "formal", "clean", "airy"))),
            "similar_signature": normalize_text(product.get("similar_to")),
            "inspired_by_signature": normalize_text(product.get("dupe_inspiration")),
            "source_confidence": confidence,
            "source_summary": source_summary,
            "verified_sources_count": external_source_count,
            "needs_manual_review": needs_manual,
            "last_researched_at": captured_at,
            "sources": build_sources(product, source_summary, captured_at),
        }
        set_product_fragrance_research(product_id, **payload)
        updated.append(
            {
                "product_id": product_id,
                "barcode": product.get("barcode"),
                "name": product.get("name"),
                "confidence": confidence,
                "verified_sources_count": external_source_count,
                "needs_manual_review": bool(needs_manual),
            }
        )
        if needs_manual:
            manual_review.append({"barcode": product.get("barcode"), "name": product.get("name")})

    print(
        json.dumps(
            {
                "updated_count": len(updated),
                "manual_review_count": len(manual_review),
                "manual_review_rows": manual_review[:25],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
