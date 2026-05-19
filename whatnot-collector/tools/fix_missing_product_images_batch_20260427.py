#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.company_db import get_product, list_products, set_product_details


HEADERS = {"User-Agent": "Mozilla/5.0"}
MEDIA_ROOT = ROOT / "data" / "marketplace_images"
TARGET_BARCODES = {
    "6291106814873","6291106813029","6281110003226","6291110113375","6291110091642","6291110117069","6291110116284",
    "6291110091451","6291110117076","6291110116291","6291110116307","6291110112910","6281110049187","6291110112422",
    "6291110100078","6291110112392","6281110085291","6291110111708","6291110104090","6281110022913","6291110111890",
    "6281110001703","6291110101457","6281110001680","6085010044712","6290362340492","6291110101440","3760060762870",
    "6291107458571","6290360598918","6290360593722","6290362342373","6290360591971","6290362346104","6290362347095",
    "6291108735541","6291108730140","6290362341130","6290362341147","6290362341109","6290362341161","6290362341123",
}


def sanitize_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-") or "image"


def load_seed_metadata() -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for path in sorted((ROOT / "tools").glob("enrich_inventory_batch_20260427_*.py")):
        name = path.stem
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
        except Exception:
            continue
        seeds = getattr(mod, "SEEDS", None)
        if not seeds:
            continue
        for seed in seeds:
            barcode = getattr(seed, "barcode", None)
            if barcode not in TARGET_BARCODES:
                continue
            bucket = merged.setdefault(barcode, {
                "image_sources": [],
                "source_official_url": None,
                "source_jomashop_url": None,
                "source_fragrantica_url": None,
                "source_parfumo_url": None,
            })
            for field in ("source_official_url", "source_jomashop_url", "source_fragrantica_url", "source_parfumo_url"):
                current = bucket.get(field)
                incoming = getattr(seed, field, None)
                if not current and incoming:
                    bucket[field] = incoming
            for source in list(getattr(seed, "image_sources", []) or []):
                if source and source not in bucket["image_sources"]:
                    bucket["image_sources"].append(source)
    return merged


def scrape_page_images(url: str) -> list[str]:
    if not url:
        return []
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except Exception:
        return []
    html = response.text
    candidates: list[str] = []
    patterns = [
        r"data-preload-product-image=['\"]([^'\"]+)['\"]",
        r"<link[^>]+rel=['\"]preload['\"][^>]+href=['\"]([^'\"]+)['\"][^>]+as=['\"]image['\"]",
        r"<meta[^>]+property=['\"]og:image['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]twitter:image['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"\"image\"\s*:\s*\"([^\"]+)\"",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html, re.I):
            value = match.group(1).replace("&amp;", "&").strip()
            if value.startswith("//"):
                value = "https:" + value
            if value.startswith("/") and "jomashop.com" in url:
                value = "https://www.jomashop.com" + value
            if value.startswith("http") and value not in candidates:
                candidates.append(value)
    return candidates


def download_image(product_id: int, index: int, source: str) -> str | None:
    try:
        response = requests.get(source, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except Exception:
        return None
    content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    suffix = ".jpg"
    if "png" in content_type or source.lower().endswith(".png"):
        suffix = ".png"
    elif "webp" in content_type or source.lower().endswith(".webp"):
        suffix = ".webp"
    elif "avif" in content_type or source.lower().endswith(".avif"):
        suffix = ".avif"
    folder = MEDIA_ROOT / str(product_id)
    folder.mkdir(parents=True, exist_ok=True)
    stem = sanitize_slug(Path(urlparse(source).path).stem)[:48]
    filename = f"{index:02d}-{stem}{suffix}"
    target = folder / filename
    target.write_bytes(response.content)
    return f"/marketplace-media/{product_id}/{filename}"


def main() -> int:
    products = {str(p.get("barcode")): p for p in list_products(active_only=False, low_stock_only=False)}
    seed_data = load_seed_metadata()
    repaired = []
    skipped = []

    for barcode in sorted(TARGET_BARCODES):
        product = products.get(barcode)
        if not product:
            skipped.append({"barcode": barcode, "reason": "missing_product"})
            continue
        current_media = str(product.get("media_url") or "").strip()
        current_gallery_raw = product.get("image_gallery_urls")
        if isinstance(current_gallery_raw, str) and current_gallery_raw.strip().startswith("["):
            try:
                current_gallery = [str(v).strip() for v in json.loads(current_gallery_raw or "[]") if str(v).strip()]
            except Exception:
                current_gallery = []
        else:
            current_gallery = [str(v).strip() for v in str(current_gallery_raw or "").splitlines() if str(v).strip()]
        if current_media or current_gallery:
            continue

        merged = seed_data.get(barcode, {})
        candidate_urls: list[str] = []
        for source in merged.get("image_sources", []):
            if source and source not in candidate_urls:
                candidate_urls.append(source)

        for field_name in ("source_jomashop_url", "source_official_url"):
            source_url = (
                (merged.get(field_name) or "").strip()
                or str(product.get(field_name) or "").strip()
            )
            if source_url:
                for image_url in scrape_page_images(source_url):
                    if image_url not in candidate_urls:
                        candidate_urls.append(image_url)

        local_gallery: list[str] = []
        seen_local: set[str] = set()
        for source in candidate_urls[:6]:
            local = download_image(int(product["id"]), len(local_gallery) + 1, source)
            if local and local not in seen_local:
                seen_local.add(local)
                local_gallery.append(local)

        if not local_gallery:
            skipped.append({"barcode": barcode, "name": product.get("name"), "reason": "no_recoverable_source_image"})
            continue

        set_product_details(
            int(product["id"]),
            media_url=local_gallery[0],
            image_gallery_urls=json.dumps(local_gallery, ensure_ascii=True),
            source_official_url=(merged.get("source_official_url") or product.get("source_official_url")),
            source_jomashop_url=(merged.get("source_jomashop_url") or product.get("source_jomashop_url")),
            source_fragrantica_url=(merged.get("source_fragrantica_url") or product.get("source_fragrantica_url")),
            source_parfumo_url=(merged.get("source_parfumo_url") or product.get("source_parfumo_url")),
        )
        repaired.append({
            "barcode": barcode,
            "name": product.get("name"),
            "images_saved": len(local_gallery),
            "primary_image": local_gallery[0],
        })

    print(json.dumps({"repaired": repaired, "skipped": skipped}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
