"""
Playwright helper for following a Whatnot user from the search page.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from .config import COLLECTOR_COOKIES_PATH


@dataclass
class WhatnotFollowResult:
    ok: bool
    username: str
    search_url: str
    clicked: bool = False
    already_following: bool = False
    message: str = ""


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


def _search_url(username: str) -> str:
    clean = str(username or "").strip().replace("@", "")
    return f"https://www.whatnot.com/search?query={quote_plus(clean)}&referringSource=typed"


def follow_user_via_search(username: str) -> WhatnotFollowResult:
    clean = str(username or "").strip().replace("@", "")
    if not clean:
        return WhatnotFollowResult(ok=False, username="", search_url="", message="username required")

    search_url = _search_url(clean)
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
    except Exception:
        return WhatnotFollowResult(ok=False, username=clean, search_url=search_url, message="playwright not installed")

    cookies = _load_cookies()

    try:
        from playwright_stealth import stealth_sync
        stealth_available = True
    except Exception:
        stealth_available = False

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
            viewport={"width": 1440, "height": 900},
        )
        context.add_cookies(cookies)
        page = context.new_page()
        if stealth_available:
            stealth_sync(page)
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            for _ in range(60):
                title = page.title() or ""
                body_text = ""
                try:
                    body_text = page.locator("body").inner_text(timeout=500)
                except Exception:
                    body_text = ""
                if "just a moment" not in title.lower() and "Performing security verification" not in body_text:
                    break
                page.wait_for_timeout(500)
            try:
                page.wait_for_load_state("networkidle", timeout=7000)
            except Exception:
                pass

            username_patterns = [
                f"@{clean}",
                clean,
            ]
            follow_button = None

            for pattern in username_patterns:
                user_text = page.get_by_text(pattern, exact=False)
                if user_text.count() > 0:
                    for idx in range(min(user_text.count(), 5)):
                        node = user_text.nth(idx)
                        try:
                            container = node.locator("xpath=ancestor-or-self::*[self::article or self::li or self::div][1]")
                            button = container.get_by_role("button", name="Follow")
                            if button.count() > 0 and button.first.is_visible():
                                follow_button = button.first
                                break
                        except Exception:
                            continue
                if follow_button:
                    break

            if not follow_button:
                # Fallback to the first visible exact "Follow" button on the page.
                button = page.get_by_role("button", name="Follow")
                if button.count() > 0 and button.first.is_visible():
                    follow_button = button.first

            if not follow_button:
                # If no Follow button exists, we may already be following.
                for name in ("Following", "Follow Back"):
                    btn = page.get_by_role("button", name=name)
                    if btn.count() > 0 and btn.first.is_visible():
                        return WhatnotFollowResult(
                            ok=True,
                            username=clean,
                            search_url=search_url,
                            already_following=True,
                            message=f"Already following {clean}",
                        )
                return WhatnotFollowResult(
                    ok=False,
                    username=clean,
                    search_url=search_url,
                    message="Follow button not found",
                )

            follow_button.click(timeout=10000)
            try:
                page.wait_for_timeout(1200)
            except Exception:
                pass

            for name in ("Following", "Follow Back"):
                btn = page.get_by_role("button", name=name)
                if btn.count() > 0 and btn.first.is_visible():
                    return WhatnotFollowResult(
                        ok=True,
                        username=clean,
                        search_url=search_url,
                        clicked=True,
                        message=f"Followed {clean}",
                    )

            return WhatnotFollowResult(
                ok=True,
                username=clean,
                search_url=search_url,
                clicked=True,
                message=f"Clicked Follow for {clean}",
            )
        except PlaywrightTimeoutError:
            return WhatnotFollowResult(
                ok=False,
                username=clean,
                search_url=search_url,
                message="Timed out while trying to follow user",
            )
        finally:
            try:
                context.close()
            finally:
                browser.close()
