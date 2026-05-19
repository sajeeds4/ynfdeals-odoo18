from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
IN_PATH = EXPORTS / "inventory_enrichment_master.csv"
OUT_CSV = EXPORTS / "inventory_enrichment_web.csv"
OUT_JSON = EXPORTS / "inventory_enrichment_web.json"

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 20

GENERIC_TOKENS = {
    "eau", "de", "parfum", "spray", "for", "men", "women", "unisex", "perfume",
    "ml", "oz", "ounce", "fl", "long", "lasting", "fragrance", "edp", "edt",
    "pour", "homme", "femme", "by", "of", "and", "the",
}

OFFICIAL_SOURCE_BY_BRAND = {
    "lattafa": "lattafa_usa",
    "lattafa perfume": "lattafa_usa",
    "maison alhambra": "lattafa_usa",
    "afnan": "afnan_us",
    "armaf": "armaf",
}

SEARCH_SOURCES = {
    "lattafa_usa": {
        "base_url": "https://lattafa-usa.com",
        "search_url": "https://lattafa-usa.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10",
        "kind": "official",
        "currency": "USD",
    },
    "afnan_us": {
        "base_url": "https://us.afnan.com",
        "search_url": "https://us.afnan.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10",
        "kind": "official",
        "currency": "USD",
    },
    "armaf": {
        "base_url": "https://armaf.com",
        "search_url": "https://armaf.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10",
        "kind": "official",
        "currency": "USD",
    },
    "tripletraders": {
        "base_url": "https://tripletraders.com",
        "search_url": "https://tripletraders.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10",
        "kind": "retailer",
        "currency": "USD",
    },
    "labelleperfumes": {
        "base_url": "https://labelleperfumes.com",
        "search_url": "https://labelleperfumes.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10",
        "kind": "retailer",
        "currency": "USD",
    },
    "intenseoud": {
        "base_url": "https://www.intenseoud.com",
        "search_url": "https://www.intenseoud.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10",
        "kind": "discount",
        "currency": "USD",
    },
    "perfumebox": {
        "base_url": "https://perfumebox.com",
        "search_url": "https://perfumebox.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10",
        "kind": "discount",
        "currency": "USD",
    },
    "filledwithbarakah": {
        "base_url": "https://filledwithbarakah.com",
        "search_url": "https://filledwithbarakah.com/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10",
        "kind": "discount",
        "currency": "USD",
    },
}


@dataclass
class Candidate:
    source: str
    kind: str
    title: str
    vendor: str
    price: str
    available: str
    url: str
    body: str
    score: float


def normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError("no rows to write")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=True)


def cleaned_product_name(name: str, brand: str) -> str:
    text = re.sub(r"^\[[^\]]+\]\s*", "", name)
    text = re.sub(re.escape(brand), "", text, flags=re.I)
    text = re.split(r"\s+-\s+|,", text, maxsplit=1)[0]
    text = re.sub(r"\b\d+(?:\.\d+)?\s*(?:ml|mL|ML|oz|Oz|Ounce|Ounces|fl\.?\s*oz)\b", " ", text)
    text = re.sub(r"[^A-Za-z0-9'&]+", " ", text)
    tokens = [token for token in re.sub(r"\s+", " ", text).strip().split() if normalize(token) not in GENERIC_TOKENS]
    return " ".join(tokens[:6]).strip()


def token_set(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize(text))
        if len(token) > 1 and token not in GENERIC_TOKENS
    }


def parse_size_ml(text: str) -> str:
    ml = re.search(r"(\d+(?:\.\d+)?)\s*(?:ml|mL|ML)\b", text)
    if ml:
        return str(int(round(float(ml.group(1)))))
    oz = re.search(r"(\d+(?:\.\d+)?)\s*(?:(?:fl\.\s*)?oz|ounce|ounces)\b", text, re.I)
    if oz:
        return str(int(round(float(oz.group(1)) * 29.5735)))
    return "unknown"


def extract_notes_from_text(text: str) -> dict[str, str]:
    plain = re.sub(r"\s+", " ", BeautifulSoup(unescape(text), "html.parser").get_text(" ", strip=True))
    patterns = {
        "top_notes": [
            r"Top Notes?\s*[:\-]\s*(.+?)(?=Middle Notes?|Heart Notes?|Base Notes?|$)",
            r"Top\s*[:\-]\s*(.+?)(?=Heart\s*[:\-]|Base\s*[:\-]|$)",
        ],
        "middle_notes": [
            r"(?:Middle|Heart) Notes?\s*[:\-]\s*(.+?)(?=Base Notes?|$)",
            r"Heart\s*[:\-]\s*(.+?)(?=Base\s*[:\-]|$)",
        ],
        "base_notes": [
            r"Base Notes?\s*[:\-]\s*(.+)$",
            r"Base\s*[:\-]\s*(.+)$",
        ],
    }
    found = {}
    for field, regexes in patterns.items():
        for regex in regexes:
            match = re.search(regex, plain, re.I)
            if match:
                found[field] = match.group(1).strip(" .;-")
                break
    return found


def fetch_json(url: str) -> dict[str, Any] | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


def fetch_text(url: str) -> str | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if response.status_code != 200:
            return None
        return response.text
    except Exception:
        return None


def page_product_data(url: str) -> dict[str, str]:
    html = fetch_text(url)
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, str] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        payloads = payload if isinstance(payload, list) else [payload]
        for item in payloads:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Product":
                desc = item.get("description")
                if desc:
                    result["description"] = BeautifulSoup(unescape(desc), "html.parser").get_text(" ", strip=True)
                offers = item.get("offers") or []
                if isinstance(offers, dict):
                    offers = [offers]
                if offers:
                    offer = offers[0]
                    if offer.get("price"):
                        result["price"] = str(offer.get("price"))
                    if offer.get("availability"):
                        result["availability"] = "in stock" if "InStock" in str(offer.get("availability")) else "out of stock"
                    if offer.get("priceCurrency"):
                        result["currency"] = str(offer.get("priceCurrency"))
                notes = extract_notes_from_text(result.get("description", ""))
                result.update(notes)
                return result
    notes = extract_notes_from_text(html)
    result.update(notes)
    return result


def score_candidate(row: dict[str, str], title: str, vendor: str, body: str) -> float:
    cleaned_name = cleaned_product_name(row["product_name"], row["brand"])
    row_tokens = token_set(cleaned_name)
    title_tokens = token_set(title)
    body_text = BeautifulSoup(unescape(body), "html.parser").get_text(" ", strip=True)
    body_tokens = token_set(body_text)
    overlap = len(row_tokens & title_tokens)
    score = overlap * 4 + len(row_tokens & body_tokens)
    score += SequenceMatcher(None, normalize(cleaned_name), normalize(title)).ratio() * 10
    extra_title_tokens = title_tokens - row_tokens - token_set(row["brand"])
    score -= len(extra_title_tokens) * 2
    if normalize(row["brand"]) in normalize(f"{title} {vendor}"):
        score += 3
    barcode = normalize(row.get("barcode", ""))
    if barcode and barcode != "unknown" and barcode in normalize(body_text):
        score += 10
    size = row.get("size_ml", "unknown")
    candidate_size = parse_size_ml(f"{title} {body_text}")
    if size != "unknown" and candidate_size != "unknown":
        if abs(int(size) - int(candidate_size)) <= 10:
            score += 2
        else:
            score -= 4
    return score


def search_source(row: dict[str, str], source_name: str) -> Candidate | None:
    source = SEARCH_SOURCES[source_name]
    query = quote(f"{row['brand']} {cleaned_product_name(row['product_name'], row['brand'])}".strip())
    url = source["search_url"].format(query=query)
    payload = fetch_json(url)
    if not payload:
        return None
    products = payload.get("resources", {}).get("results", {}).get("products", [])
    best: Candidate | None = None
    for product in products:
        title = str(product.get("title") or "")
        body = str(product.get("body") or "")
        vendor = str(product.get("vendor") or "")
        score = score_candidate(row, title, vendor, body)
        if score < 5:
            continue
        candidate = Candidate(
            source=source_name,
            kind=source["kind"],
            title=title,
            vendor=vendor,
            price=str(product.get("price") or "unknown"),
            available="in stock" if product.get("available") else "out of stock",
            url=urljoin(source["base_url"], str(product.get("url") or "")),
            body=body,
            score=score,
        )
        if not best or candidate.score > best.score:
            best = candidate
    return best


def fill_source_fields(row: dict[str, str], prefix: str, candidate: Candidate, extra: dict[str, str] | None = None) -> None:
    extra = extra or {}
    row[f"{prefix}_price_usd"] = candidate.price or "unknown"
    row[f"{prefix}_availability"] = candidate.available or "unknown"
    row[f"{prefix}_seller_type"] = "official" if prefix == "official" else ("third-party" if prefix == "amazon" else prefix)
    row[f"{prefix}_source_url"] = candidate.url or "unknown"
    row[f"{prefix}_size_ml"] = extra.get("size_ml") or parse_size_ml(f"{candidate.title} {extra.get('description', '')}")
    if row[f"{prefix}_size_ml"] == "":
        row[f"{prefix}_size_ml"] = "unknown"


def candidate_size_is_acceptable(row: dict[str, str], candidate: Candidate) -> bool:
    row_size = row.get("size_ml", "unknown")
    candidate_size = parse_size_ml(f"{candidate.title} {candidate.body} {candidate.url}")
    if row_size == "unknown" or candidate_size == "unknown":
        return True
    return abs(int(row_size) - int(candidate_size)) <= 10


def merge_note_fields(row: dict[str, str], notes: dict[str, str]) -> None:
    for field in ("top_notes", "middle_notes", "base_notes"):
        if row.get(field) in ("", "unknown") and notes.get(field):
            row[field] = notes[field]


def update_missing_tracking(row: dict[str, str]) -> None:
    tracked = [
        "top_notes", "middle_notes", "base_notes",
        "official_price_usd", "retailer_price_usd", "discount_price_usd", "amazon_price_usd",
        "seasonality", "occasion",
    ]
    row["missing_fields"] = ", ".join(field for field in tracked if row.get(field) in ("", "unknown")) or "none"


def enrich_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in rows:
        brand_key = normalize(row["brand"])

        official_source = OFFICIAL_SOURCE_BY_BRAND.get(brand_key)
        if official_source:
            candidate = search_source(row, official_source)
            if candidate:
                page_data = page_product_data(candidate.url)
                fill_source_fields(
                    row,
                    "official",
                    candidate,
                    {
                        "size_ml": parse_size_ml(f"{candidate.title} {page_data.get('description', '')}"),
                        "description": page_data.get("description", ""),
                    },
                )
                merge_note_fields(row, page_data or extract_notes_from_text(candidate.body))
                if page_data.get("description") and row.get("fragrance_description") in ("", "unknown"):
                    row["fragrance_description"] = page_data["description"]

        retailer_candidates = [candidate for candidate in (
            search_source(row, "tripletraders"),
            search_source(row, "labelleperfumes"),
        ) if candidate]
        if retailer_candidates:
            retailer = sorted(retailer_candidates, key=lambda item: item.score, reverse=True)[0]
            if candidate_size_is_acceptable(row, retailer):
                fill_source_fields(row, "retailer", retailer)
                merge_note_fields(row, extract_notes_from_text(retailer.body))

        discount_candidates = [candidate for candidate in (
            search_source(row, "intenseoud"),
            search_source(row, "perfumebox"),
            search_source(row, "filledwithbarakah"),
        ) if candidate]
        if discount_candidates:
            discount = sorted(discount_candidates, key=lambda item: item.score, reverse=True)[0]
            if candidate_size_is_acceptable(row, discount):
                fill_source_fields(row, "discount", discount)
                merge_note_fields(row, extract_notes_from_text(discount.body))
                if row.get("fragrance_description") in ("", "unknown"):
                    row["fragrance_description"] = BeautifulSoup(unescape(discount.body), "html.parser").get_text(" ", strip=True) or row.get("fragrance_description", "unknown")

        row["amazon_price_usd"] = row.get("amazon_price_usd") or "unknown"
        row["amazon_size_ml"] = row.get("amazon_size_ml") or "unknown"
        row["amazon_availability"] = row.get("amazon_availability") or "unknown"
        row["amazon_seller_type"] = row.get("amazon_seller_type") or "unknown"
        row["amazon_source_url"] = row.get("amazon_source_url") or "unknown"
        row["market_pricing_status"] = "partial_live_web_research"
        update_missing_tracking(row)
    return rows


def print_summary(rows: list[dict[str, str]]) -> None:
    counts = {
        "official_price": sum(1 for row in rows if row["official_price_usd"] != "unknown"),
        "retailer_price": sum(1 for row in rows if row["retailer_price_usd"] != "unknown"),
        "discount_price": sum(1 for row in rows if row["discount_price_usd"] != "unknown"),
        "amazon_price": sum(1 for row in rows if row["amazon_price_usd"] != "unknown"),
        "top_notes": sum(1 for row in rows if row["top_notes"] != "unknown"),
        "middle_notes": sum(1 for row in rows if row["middle_notes"] != "unknown"),
        "base_notes": sum(1 for row in rows if row["base_notes"] != "unknown"),
    }
    for key, value in counts.items():
        print(f"{key}={value}")
    print(OUT_CSV)
    print(OUT_JSON)


def main() -> None:
    rows = load_rows(IN_PATH)
    enriched = enrich_rows(rows)
    write_rows(OUT_CSV, enriched)
    write_json(OUT_JSON, enriched)
    print_summary(enriched)


if __name__ == "__main__":
    main()
