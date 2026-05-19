"""
Playwright helper for syncing Whatnot seller reviews and matching them to local customers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import (
    COLLECTOR_COOKIES_PATH,
    DB_PATH,
    REVIEW_AUTOSCRAPE_ENABLED,
    REVIEW_AUTOSCRAPE_INTERVAL_SEC,
    REVIEW_AUTOSCRAPE_TARGET,
    REVIEW_AUTOSCRAPE_WARMUP_SEC,
)
from .company_db import get_setting_map, upsert_customer_review, upsert_setting

_reviews_thread = None
_reviews_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setting_key(name: str, seller_username: str) -> str:
    clean = str(seller_username or "").strip().lstrip("@").lower() or "unknown"
    return f"whatnot_reviews:{clean}:{name}"


def _load_cookies():
    if not os.path.exists(COLLECTOR_COOKIES_PATH):
        raise RuntimeError(f"Cookies file not found: {COLLECTOR_COOKIES_PATH}")
    with open(COLLECTOR_COOKIES_PATH, "r", encoding="utf-8") as f:
        parsed = json.load(f)
    if isinstance(parsed, dict):
        parsed = parsed.get("cookies") or []
    if not isinstance(parsed, list):
        raise RuntimeError("Unexpected cookies format")
    cookies = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if not item.get("name") or not item.get("value"):
            continue
        cookie = dict(item)
        if "sameSite" in cookie and cookie["sameSite"] not in {"Strict", "Lax", "None"}:
            cookie.pop("sameSite", None)
        cookies.append(cookie)
    if not cookies:
        raise RuntimeError("No usable cookies found")
    return cookies


def _normalize_username(value: Any) -> str:
    return str(value or "").strip().lstrip("@").lower()


def _normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_rating(text: str, aria_labels: list[str]) -> float | None:
    for candidate in [text, *aria_labels]:
        raw = str(candidate or "")
        match = re.search(r"([0-5](?:\.\d)?)\s*(?:out of\s*5|/5)", raw, re.I)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                pass
    return None


def _extract_reply_text(text: str) -> tuple[str | None, str]:
    clean = _normalize_space(text)
    markers = [
        "Seller reply",
        "Seller response",
        "Response from seller",
        "Reply from seller",
        "ynfdeals replied",
    ]
    lowered = clean.lower()
    for marker in markers:
        idx = lowered.find(marker.lower())
        if idx >= 0:
            review_text = _normalize_space(clean[:idx])
            reply_text = _normalize_space(clean[idx + len(marker):])
            return (reply_text or None, review_text)
    return None, clean


def _extract_review_payload(seller_username: str, raw: dict[str, Any]) -> dict[str, Any] | None:
    seller_clean = _normalize_username(seller_username)
    text = _normalize_space(raw.get("text"))
    if not text:
        return None

    reviewer_username = ""
    reviewer_display = ""
    for link in raw.get("links") or []:
        href = str(link.get("href") or "")
        match = re.search(r"/user/([^/?#]+)", href)
        if not match:
            continue
        candidate = _normalize_username(match.group(1))
        if not candidate or candidate == seller_clean:
            continue
        reviewer_username = candidate
        reviewer_display = _normalize_space(link.get("text")) or candidate
        break

    if not reviewer_username:
        return None

    reply_text, review_text = _extract_reply_text(text)
    rating = _parse_rating(text, raw.get("aria_labels") or [])
    fingerprint_source = json.dumps(
        {
            "seller": seller_clean,
            "reviewer": reviewer_username,
            "rating": rating,
            "text": review_text,
            "reply": reply_text,
            "card": text,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    review_key = hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()
    return {
        "review_key": review_key,
        "seller_username": seller_clean,
        "reviewer_username": reviewer_username,
        "reviewer_display_name": reviewer_display or reviewer_username,
        "rating": rating,
        "review_text": review_text,
        "reply_text": reply_text,
        "source_url": raw.get("source_url"),
        "raw_payload": raw,
    }


@dataclass
class WhatnotReviewSyncResult:
    ok: bool
    seller_username: str
    source_url: str
    fetched: int = 0
    saved: int = 0
    matched_customers: int = 0
    challenge_blocked: bool = False
    error: str = ""
    reviews: list[dict[str, Any]] = field(default_factory=list)


def sync_seller_reviews(seller_username: str) -> WhatnotReviewSyncResult:
    clean = _normalize_username(seller_username)
    if not clean:
        return WhatnotReviewSyncResult(ok=False, seller_username="", source_url="", error="seller_username required")

    source_url = f"https://www.whatnot.com/user/{clean}/reviews"

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
        from playwright_stealth import Stealth
    except Exception:
        return WhatnotReviewSyncResult(
            ok=False,
            seller_username=clean,
            source_url=source_url,
            error="playwright not installed",
        )

    cookies = _load_cookies()
    started_at = _utc_now()
    upsert_setting(_setting_key("last_started_at", clean), started_at)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--disable-backgrounding-occluded-windows",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1440, "height": 2200},
            )
            Stealth().apply_stealth_sync(context)
            context.add_cookies(cookies)
            page = context.new_page()
            page.goto(source_url, wait_until="domcontentloaded", timeout=45000)

            for _ in range(60):
                title = (page.title() or "").lower()
                body_text = ""
                try:
                    body_text = (page.locator("body").inner_text(timeout=500) or "").lower()
                except Exception:
                    body_text = ""
                if "just a moment" not in title and "performing security verification" not in body_text:
                    break
                page.wait_for_timeout(500)

            page.wait_for_timeout(1200)
            body_text = ""
            try:
                body_text = page.locator("body").inner_text(timeout=1500) or ""
            except Exception:
                body_text = ""
            if "Performing security verification" in body_text or "Just a moment" in (page.title() or ""):
                context.close()
                browser.close()
                result = WhatnotReviewSyncResult(
                    ok=False,
                    seller_username=clean,
                    source_url=source_url,
                    challenge_blocked=True,
                    error="cloudflare_challenge",
                )
                upsert_setting(_setting_key("last_finished_at", clean), _utc_now())
                upsert_setting(_setting_key("last_status", clean), "challenge_blocked")
                upsert_setting(_setting_key("last_error", clean), result.error)
                return result

            last_height = -1
            stable_cycles = 0
            while stable_cycles < 4:
                try:
                    page.mouse.wheel(0, 2400)
                except Exception:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(900)
                height = int(page.evaluate("document.body.scrollHeight"))
                if height == last_height:
                    stable_cycles += 1
                else:
                    stable_cycles = 0
                    last_height = height

            raw_cards = page.evaluate(
                """
                () => {
                  const grid =
                    document.querySelector('[class*="grid-flow-row-dense"][class*="grid-cols-2"][class*="gap-2"][class*="pt-3"]')
                    || document.querySelector('main [class*="grid-flow-row-dense"]')
                    || document.querySelector('[class*="grid-cols-2"][class*="gap-2"]');
                  if (!grid) return [];
                  return Array.from(grid.children).map((node) => {
                    const text = (node.innerText || '').trim();
                    const links = Array.from(node.querySelectorAll('a[href*="/user/"]')).map((a) => ({
                      href: a.getAttribute('href') || '',
                      text: (a.textContent || '').trim(),
                    }));
                    const ariaLabels = Array.from(node.querySelectorAll('[aria-label]')).map((el) => el.getAttribute('aria-label') || '');
                    return {
                      text,
                      html: node.innerHTML || '',
                      links,
                      aria_labels: ariaLabels,
                    };
                  }).filter((item) => item.text);
                }
                """
            )
            context.close()
            browser.close()
    except PlaywrightTimeoutError:
        result = WhatnotReviewSyncResult(
            ok=False,
            seller_username=clean,
            source_url=source_url,
            error="timeout",
        )
        upsert_setting(_setting_key("last_finished_at", clean), _utc_now())
        upsert_setting(_setting_key("last_status", clean), "timeout")
        upsert_setting(_setting_key("last_error", clean), result.error)
        return result
    except Exception as exc:
        result = WhatnotReviewSyncResult(
            ok=False,
            seller_username=clean,
            source_url=source_url,
            error=str(exc),
        )
        upsert_setting(_setting_key("last_finished_at", clean), _utc_now())
        upsert_setting(_setting_key("last_status", clean), "error")
        upsert_setting(_setting_key("last_error", clean), result.error)
        return result

    parsed_reviews = []
    saved = 0
    matched = 0
    for raw in raw_cards or []:
        payload = _extract_review_payload(clean, {**raw, "source_url": source_url})
        if not payload:
            continue
        parsed_reviews.append(payload)
        row = upsert_customer_review(**payload)
        if row:
            saved += 1
            if row.get("matched_customer_id"):
                matched += 1

    upsert_setting(_setting_key("last_finished_at", clean), _utc_now())
    upsert_setting(_setting_key("last_status", clean), "ok")
    upsert_setting(_setting_key("last_error", clean), "")
    upsert_setting(_setting_key("last_count", clean), str(len(parsed_reviews)))
    return WhatnotReviewSyncResult(
        ok=True,
        seller_username=clean,
        source_url=source_url,
        fetched=len(raw_cards or []),
        saved=saved,
        matched_customers=matched,
        reviews=parsed_reviews,
    )


def get_review_sync_status(seller_username: str | None = None) -> dict[str, Any]:
    seller = _normalize_username(seller_username or REVIEW_AUTOSCRAPE_TARGET)
    settings = get_setting_map() or {}
    return {
        "seller_username": seller,
        "enabled": bool(REVIEW_AUTOSCRAPE_ENABLED),
        "interval_sec": int(REVIEW_AUTOSCRAPE_INTERVAL_SEC),
        "last_started_at": settings.get(_setting_key("last_started_at", seller)),
        "last_finished_at": settings.get(_setting_key("last_finished_at", seller)),
        "last_status": settings.get(_setting_key("last_status", seller)),
        "last_error": settings.get(_setting_key("last_error", seller)),
        "last_count": int(settings.get(_setting_key("last_count", seller)) or 0),
    }


def _review_loop():
    if REVIEW_AUTOSCRAPE_WARMUP_SEC > 0:
        time.sleep(REVIEW_AUTOSCRAPE_WARMUP_SEC)
    while True:
        try:
            status = get_review_sync_status(REVIEW_AUTOSCRAPE_TARGET)
            last_finished = status.get("last_finished_at") or ""
            due = True
            if last_finished:
                try:
                    last_dt = datetime.fromisoformat(last_finished.replace("Z", "+00:00"))
                    due = (datetime.now(timezone.utc) - last_dt).total_seconds() >= max(3600, REVIEW_AUTOSCRAPE_INTERVAL_SEC)
                except Exception:
                    due = True
            if due:
                result = sync_seller_reviews(REVIEW_AUTOSCRAPE_TARGET)
                print(
                    f"[whatnot-review-sync] seller={REVIEW_AUTOSCRAPE_TARGET} "
                    f"ok={result.ok} fetched={result.fetched} saved={result.saved} "
                    f"matched={result.matched_customers} error={result.error or '-'}"
                )
        except Exception as exc:
            print(f"[whatnot-review-sync] cycle failed: {exc}")
        time.sleep(max(1800, REVIEW_AUTOSCRAPE_INTERVAL_SEC // 8 or 1800))


def start_review_autoscrape_scheduler(db_path: str = None) -> bool:
    del db_path  # parity with other scheduler helpers
    global _reviews_thread
    if not REVIEW_AUTOSCRAPE_ENABLED:
        return False
    with _reviews_lock:
        if _reviews_thread and _reviews_thread.is_alive():
            return False
        _reviews_thread = threading.Thread(
            target=_review_loop,
            daemon=True,
            name="whatnot-review-sync",
        )
        _reviews_thread.start()
        return True
