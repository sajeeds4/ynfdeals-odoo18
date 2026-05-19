import json
import fcntl
import os
import time
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
from server.postgres_cutover import domain_primary_backend, postgres_available

from .db import connect, finalize_spectator_stream_identity, get_or_create_spectator_stream, init_db

COLLECTOR_POSTGRES_DOMAINS = (
    "ingest_streams",
    "ingest_stream_merge",
    "ingest_events",
    "ingest_lots",
    "ingest_users",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_collector_postgres_runtime() -> bool:
    if not postgres_available():
        raise RuntimeError("collector_postgres_unavailable")
    sqlite_domains = [
        domain for domain in COLLECTOR_POSTGRES_DOMAINS
        if domain_primary_backend(domain) != "postgres"
    ]
    if sqlite_domains:
        raise RuntimeError(
            "collector_postgres_runtime_incomplete:"
            + ",".join(sqlite_domains)
        )
    return True


def insert_event(conn, stream_id: int, event_type: str, payload: dict):
    try:
        from server.ingest_cutover import insert_event as cutover_insert_event
        cutover_insert_event(
            int(stream_id),
            event_type,
            json.dumps(payload),
            created_at=utc_now(),
        )
        return True
    except Exception as exc:
        print(f"[collector] WARNING: failed to insert {event_type}: {exc}", flush=True)
        return False


def upsert_user(conn, username: str | None) -> bool:
    if not username:
        return False
    try:
        from server.ingest_cutover import upsert_ingest_user
        upsert_ingest_user(username)
        return True
    except Exception as exc:
        print(f"[collector] WARNING: failed to upsert user {username!r}: {exc}", flush=True)
        return False


def open_lot(conn, stream_id: int, lot_number, product_name: str | None, started_at: str) -> int | None:
    try:
        from server.ingest_cutover import upsert_ingest_lot_open
        return upsert_ingest_lot_open(
            int(stream_id),
            lot_number,
            product_name,
            started_at,
        )
    except Exception as exc:
        print(f"[collector] WARNING: failed to open lot {lot_number!r}: {exc}", flush=True)
        return None


def close_lot(conn, lot_id: int | None, winner_username: str | None, final_price, ended_at: str) -> bool:
    if not lot_id:
        return False
    try:
        from server.ingest_cutover import close_ingest_lot
        return bool(close_ingest_lot(int(lot_id), winner_username, final_price, ended_at))
    except Exception as exc:
        print(f"[collector] WARNING: failed to close lot {lot_id!r}: {exc}", flush=True)
        return False


def update_stream_metadata(
    conn,
    stream_id: int | None,
    *,
    stream_url: str | None = None,
    streamer_name: str | None = None,
    title: str | None = None,
    ended_at: str | None = None,
    clear_ended_at: bool = False,
) -> bool:
    if not stream_id:
        return False
    try:
        from server.ingest_cutover import update_ingest_stream_metadata
        return bool(
            update_ingest_stream_metadata(
                int(stream_id),
                stream_url=stream_url,
                streamer_name=streamer_name,
                title=title,
                ended_at=ended_at,
                clear_ended_at=clear_ended_at,
            )
        )
    except Exception as exc:
        print(f"[collector] WARNING: failed to update stream metadata for {stream_id!r}: {exc}", flush=True)
        return False


def create_stream(conn, stream_url: str) -> int:
    try:
        from server.ingest_cutover import ensure_ingest_stream
        stream_id = ensure_ingest_stream(stream_url, started_at=utc_now())
        if stream_id:
            return int(stream_id)
    except Exception as exc:
        print(f"[collector] WARNING: failed to create stream {stream_url!r}: {exc}", flush=True)
    return 0


def replace_competitor_listings_snapshot(conn, stream_id: int, listings: list[dict], scraped_at: str) -> int:
    try:
        from server.ingest_cutover import replace_competitor_listings_snapshot as cutover_replace_competitor_listings_snapshot
        return int(cutover_replace_competitor_listings_snapshot(int(stream_id), listings, scraped_at) or 0)
    except Exception as exc:
        print(f"[collector] WARNING: failed to replace competitor snapshot for stream {stream_id!r}: {exc}", flush=True)
        return 0


def load_cookies(path: str):
    raw = json.loads(Path(path).read_text())
    cookies = []
    for c in raw:
        same_site = (c.get("sameSite") or "Lax").lower()
        if same_site in ("no_restriction", "none"):
            same_site = "None"
        elif same_site == "strict":
            same_site = "Strict"
        else:
            same_site = "Lax"
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain"),
            "path": c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": same_site,
        }
        if "expirationDate" in c:
            cookie["expires"] = c["expirationDate"]
        cookies.append(cookie)
    return cookies


SHOP_SCRAPE_INTERVAL = 300  # seconds between shop panel scrapes
MAX_REASONABLE_WINNER_PRICE = 5000.0
FATAL_PAGE_ERROR_TOKENS = (
    "Target page, context or browser has been closed",
    "Browser has been closed",
    "Connection closed",
)


def _is_fatal_page_error(message: str | None) -> bool:
    text = str(message or "")
    return any(token in text for token in FATAL_PAGE_ERROR_TOKENS)


def _ensure_browser_alive(browser, page):
    if page.is_closed():
        raise RuntimeError("Target page, context or browser has been closed")
    if hasattr(browser, "is_connected") and not browser.is_connected():
        raise RuntimeError("Browser connection closed")


def _load_json_file(path: str):
    try:
        if not path or not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json_file(path: str, payload: dict):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, path)


def _refresh_write_lease(lease_path: str | None, *, process_role: str, stream_url: str, session_id, ttl_sec: int):
    if not lease_path:
        return True
    os.makedirs(os.path.dirname(lease_path), exist_ok=True)
    lock_path = f"{lease_path}.lock"
    now = time.time()
    identity = f"{os.getpid()}:{process_role}"
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        current = _load_json_file(lease_path)
        owner_id = str(current.get("owner_id") or "")
        owner_role = str(current.get("owner_role") or "")
        last_heartbeat = float(current.get("heartbeat_ts") or 0)
        expired = not owner_id or (now - last_heartbeat > max(1, ttl_sec))
        should_claim = False
        if owner_id == identity:
            should_claim = True
        elif expired:
            should_claim = True
        elif process_role == "active" and owner_role == "standby":
            should_claim = True
        if should_claim:
            payload = {
                "owner_id": identity,
                "owner_role": process_role,
                "heartbeat_ts": now,
                "stream_url": stream_url,
                "session_id": session_id,
            }
            _save_json_file(lease_path, payload)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            return True
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return False


def _collect_named_rows(page, row_selector: str, name_selector: str, extra_selector: str | None = None):
    rows = []
    try:
        nodes = page.query_selector_all(row_selector)
    except Exception:
        return rows
    for node in nodes:
        try:
            name_el = node.query_selector(name_selector) if name_selector else node
            name = name_el.inner_text().strip() if name_el else None
            extra = None
            if extra_selector:
                extra_el = node.query_selector(extra_selector)
                extra = extra_el.inner_text().strip() if extra_el else None
            if name:
                rows.append({"name": name, "extra": extra})
        except Exception:
            continue
    return rows


def _extract_price_token(text: str | None):
    if not text:
        return None
    matches = re.findall(r"\$[0-9][0-9,]*(?:\.[0-9]{2})?", text)
    return matches[-1] if matches else None


def _extract_lot_number_from_text(text: str | None):
    if not text:
        return None
    match = re.search(r"(?:^|[\s(])#\s*(\d{1,6})(?:\b|[)\s]|$)", str(text))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    match = re.search(r"\blot\s*#?\s*(\d{1,6})\b", str(text), re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _parse_price_token(price_text: str | None):
    if not price_text or "$" not in price_text:
        return None
    try:
        value = float(price_text.replace("$", "").replace(",", "").strip())
        if value <= 0 or value > MAX_REASONABLE_WINNER_PRICE:
            return None
        return value
    except ValueError:
        return None


def _sanitize_price_pair(price_text: str | None, price_value):
    if price_value is None:
        return None, None
    if price_value <= 0 or price_value > MAX_REASONABLE_WINNER_PRICE:
        return None, None
    return price_text, price_value


def _normalize_winner_text(text: str | None):
    if not text:
        return None
    text = " ".join(str(text).split()).strip()
    if not text:
        return None
    low = text.lower()
    if "winning" in low:
        return None
    text = re.sub(r"\bwon!?\b", "", text, flags=re.IGNORECASE).strip(" -:\n\t")
    return text or None


def _extract_banner_winner_username(text: str | None):
    if not text:
        return None
    compact = " ".join(str(text).split()).strip()
    if not compact:
        return None
    if re.search(r"\bis\s+winning!?$", compact, flags=re.IGNORECASE):
        return None
    match = re.match(r"^(@?[A-Za-z0-9._-]{2,40})\s+won!?$", compact, flags=re.IGNORECASE)
    if match:
        return match.group(1).lstrip("@")
    return None


def _looks_like_username(text: str | None):
    if not text:
        return False
    candidate = " ".join(str(text).split()).strip()
    if not candidate or len(candidate) <= 1 or len(candidate) > 40:
        return False
    if "\n" in str(text) or " " in candidate:
        return False
    low = candidate.lower()
    blocked_terms = (
        "follow",
        "shipping",
        "taxes",
        "auction",
        "available",
        "bids",
        "shop",
        "search",
        "filter",
        "sort",
        "products",
        "host",
        "scroll",
        "watching",
        "cancellation",
        "bid",
        "winning",
    )
    if any(term in low for term in blocked_terms):
        return False
    if candidate.upper() == candidate and re.search(r"[A-Z]", candidate):
        return False
    return bool(re.fullmatch(r"@?[A-Za-z0-9._-]+", candidate))


def _extract_sold_price(page, lot_winner_el=None, lot_footer_el=None):
    candidates = []
    if lot_winner_el:
        candidates.append(lot_winner_el)
    if lot_footer_el:
        candidates.append(lot_footer_el)
    for node in candidates:
        try:
            sold_price = node.evaluate(
                """(root) => {
                    const priceRe = /\\$[0-9][0-9,]*(?:\\.[0-9]{2})?/g;
                    const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
                    let current = root;
                    for (let depth = 0; depth < 6 && current; depth++, current = current.parentElement) {
                        const strongs = Array.from(current.querySelectorAll('strong'));
                        const hasSoldLabel = strongs.some((el) => /^sold$/i.test(textOf(el)));
                        if (!hasSoldLabel) continue;
                        const text = textOf(current);
                        const matches = text.match(priceRe);
                        if (matches?.length) return matches[matches.length - 1];
                    }
                    return null;
                }"""
            )
            if sold_price:
                return sold_price
        except Exception:
            continue
    try:
        sold_price = page.evaluate(
            """() => {
                const priceRe = /\\$[0-9][0-9,]*(?:\\.[0-9]{2})?/g;
                const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
                const soldLabels = Array.from(document.querySelectorAll('strong'))
                    .filter((el) => /^sold$/i.test(textOf(el)));
                for (const label of soldLabels) {
                    let current = label.parentElement;
                    for (let depth = 0; depth < 5 && current; depth++, current = current.parentElement) {
                        const text = textOf(current);
                        const matches = text.match(priceRe);
                        if (matches?.length) return matches[matches.length - 1];
                    }
                }
                return null;
            }"""
        )
        if sold_price:
            return sold_price
    except Exception:
        pass
    return None


def _extract_live_bid_price(page, lot_footer_el=None):
    if lot_footer_el:
        try:
            price = lot_footer_el.evaluate(
                """(root) => {
                    const priceRe = /\\$[0-9][0-9,]*(?:\\.[0-9]{2})?/g;
                    const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
                    const direct = Array.from(root.querySelectorAll('strong, span, div'))
                        .map((el) => textOf(el))
                        .find((text) => /^\\$[0-9]/.test(text));
                    if (direct) return direct;
                    const text = textOf(root);
                    const matches = text.match(priceRe);
                    return matches?.length ? matches[matches.length - 1] : null;
                }"""
            )
            if price:
                return price
        except Exception:
            pass
    try:
        return page.evaluate(
            """() => {
                const priceRe = /\\$[0-9][0-9,]*(?:\\.[0-9]{2})?/g;
                const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
                const selectors = [
                    "strong.tabular-nums",
                    "[data-testid='show-current-bid']",
                    "[data-testid='current-bid-amount']",
                    "[data-testid='show-price']",
                    "[data-testid='show-custom-bid-button']"
                ];
                for (const sel of selectors) {
                    const nodes = Array.from(document.querySelectorAll(sel));
                    for (const node of nodes) {
                        let current = node;
                        for (let depth = 0; depth < 5 && current; depth++, current = current.parentElement) {
                            const text = textOf(current);
                            const matches = text.match(priceRe);
                            if (matches?.length) return matches[matches.length - 1];
                        }
                    }
                }
                return null;
            }"""
        )
    except Exception:
        return None


def _extract_completed_winner(page, lot_winner_el=None, lot_footer_el=None, allow_page_fallback=True):
    direct = None
    try:
        banner_text = lot_winner_el.inner_text() if lot_winner_el else None
        direct = _extract_banner_winner_username(banner_text)
    except Exception:
        direct = None
    if direct:
        return direct
    candidates = []
    if lot_winner_el:
        candidates.append(lot_winner_el)
    if lot_footer_el:
        candidates.append(lot_footer_el)
    for node in candidates:
        try:
            text = node.evaluate(
                """(root) => {
                    const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
                    let current = root;
                    for (let depth = 0; depth < 6 && current; depth++, current = current.parentElement) {
                        const strongs = Array.from(current.querySelectorAll('strong'));
                        const hasSoldLabel = strongs.some((el) => /^sold$/i.test(textOf(el)));
                        if (!hasSoldLabel) continue;
                        return textOf(current);
                    }
                    return null;
                }"""
            )
            normalized = _normalize_winner_text(text)
            if normalized and normalized.lower() != "sold":
                price_tokens = re.findall(r"\$[0-9][0-9,]*(?:\.[0-9]{2})?", normalized)
                for token in price_tokens:
                    normalized = normalized.replace(token, "").strip()
                normalized = normalized.replace("Sold", "").replace("sold", "").strip(" -:\n\t")
                lines = [line.strip() for line in normalized.splitlines() if line.strip()]
                for line in lines:
                    candidate = _normalize_winner_text(line)
                    if candidate and candidate.lower() != "sold" and _looks_like_username(candidate):
                        return candidate.lstrip("@")
        except Exception:
            continue
    if not allow_page_fallback:
        return None
    return None


def _extract_our_stream_winner(lot_winner_el=None, lot_footer_el=None):
    try:
        banner_text = lot_winner_el.inner_text() if lot_winner_el else None
        direct = _extract_banner_winner_username(banner_text)
    except Exception:
        direct = None
    if direct and _looks_like_username(direct):
        return direct.lstrip("@")
    candidates = []
    if lot_winner_el:
        candidates.append(lot_winner_el)
    if lot_footer_el:
        candidates.append(lot_footer_el)
    for node in candidates:
        try:
            text = node.evaluate(
                """(root) => {
                    const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
                    let current = root;
                    for (let depth = 0; depth < 4 && current; depth++, current = current.parentElement) {
                        const strongs = Array.from(current.querySelectorAll('strong'));
                        const hasSoldLabel = strongs.some((el) => /^sold$/i.test(textOf(el)));
                        if (!hasSoldLabel) continue;
                        const lines = textOf(current).split(/\\n+/).map((line) => line.trim()).filter(Boolean);
                        return lines;
                    }
                    return [];
                }"""
            )
            for line in text or []:
                candidate = _normalize_winner_text(line)
                if candidate and candidate.lower() != "sold" and _looks_like_username(candidate):
                    return candidate.lstrip("@")
        except Exception:
            continue
    return None


def _winner_signal_is_final(page, lot_winner_el=None, lot_footer_el=None):
    try:
        banner_text = lot_winner_el.inner_text() if lot_winner_el else None
    except Exception:
        banner_text = None
    compact = " ".join(str(banner_text or "").split()).strip()
    if compact and re.search(r"\bwon!?$", compact, flags=re.IGNORECASE):
        return True

    candidates = []
    if lot_winner_el:
        candidates.append(lot_winner_el)
    if lot_footer_el:
        candidates.append(lot_footer_el)
    for node in candidates:
        try:
            has_sold = node.evaluate(
                """(root) => {
                    const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
                    let current = root;
                    for (let depth = 0; depth < 6 && current; depth++, current = current.parentElement) {
                        const strongs = Array.from(current.querySelectorAll('strong'));
                        if (strongs.some((el) => /^sold$/i.test(textOf(el)))) return true;
                    }
                    return false;
                }"""
            )
            if has_sold:
                return True
        except Exception:
            continue
    try:
        sold_price = _extract_sold_price(page, lot_winner_el, lot_footer_el)
        if sold_price:
            return True
    except Exception:
        pass
    return False


def _choose_final_price(sold_price_str, sold_price_value, live_price_str, live_price_value):
    sold_price_str, sold_price_value = _sanitize_price_pair(sold_price_str, sold_price_value)
    live_price_str, live_price_value = _sanitize_price_pair(live_price_str, live_price_value)
    if live_price_value is not None:
        if sold_price_value is None:
            return live_price_str, live_price_value
        # Ignore bogus sold-price reads that jump far away from the actual live bid.
        if sold_price_value > (live_price_value * 1.5) or sold_price_value < (live_price_value * 0.5):
            return live_price_str, live_price_value
    if sold_price_value is not None:
        return sold_price_str, sold_price_value
    return live_price_str, live_price_value


def _extract_chat_parts(node):
    try:
        username_el = (
            node.query_selector("div.flex.flex-col > div strong")
            or node.query_selector("strong[data-testid*='username']")
            or node.query_selector("[data-testid*='username'] strong")
            or node.query_selector("div strong")
        )
        message_el = (
            node.query_selector("div.flex.flex-col > strong")
            or node.query_selector("[data-testid*='message']")
            or node.query_selector("strong + span")
            or node.query_selector("div.flex.flex-col span")
        )
        username = username_el.inner_text().strip() if username_el else None
        message = message_el.inner_text().strip() if message_el else None
        if (not message) and node:
            text = " ".join((node.inner_text() or "").split())
            if text:
                if username and text.startswith(username):
                    message = text[len(username):].strip(" :,-")
                elif not username:
                    parts = text.split(" ", 1)
                    username = parts[0].strip() if parts else None
                    message = parts[1].strip() if len(parts) > 1 else None
        return username, message
    except Exception:
        return None, None


def _scroll_chat_to_latest(page):
    try:
        page.evaluate(
            """() => {
                const list = document.querySelector("[data-testid='virtuoso-item-list']");
                if (!list) return;
                let scroller = list.parentElement;
                while (scroller && scroller !== document.body) {
                    const style = window.getComputedStyle(scroller);
                    const canScroll = /(auto|scroll)/.test(style.overflowY || '') || scroller.scrollHeight > scroller.clientHeight + 20;
                    if (canScroll) {
                        scroller.scrollTop = scroller.scrollHeight;
                        return;
                    }
                    scroller = scroller.parentElement;
                }
            }"""
        )
    except Exception:
        pass


def scrape_shop_listings(page, conn, stream_id: int) -> int:
    """Scrape the competitor's shop panel listings via JS injection.

    Returns the number of rows inserted (0 if panel not found or empty).
    Each call replaces the snapshot for this scrape timestamp — callers
    retrieve only the latest snapshot via MAX(scraped_at).
    """
    try:
        listings = page.evaluate("""() => {
            const results = [];
            // Find the "Products (N)" header strong element
            const strongs = Array.from(document.querySelectorAll('strong'));
            const header = strongs.find(el => /^Products\\s*\\(/.test((el.textContent || '').trim()));
            if (!header) return results;

            // Walk up to find the scrollable container that holds the product grid
            let container = header.parentElement;
            for (let i = 0; i < 8 && container; i++) {
                if (container.querySelectorAll('section.relative').length > 0) break;
                container = container.parentElement;
            }
            if (!container) return results;

            const cards = container.querySelectorAll('section.relative');
            cards.forEach((card, index) => {
                // Product name — strong with title attribute
                const nameEl = card.querySelector('strong[title]');
                const product_name = nameEl ? nameEl.getAttribute('title') || nameEl.textContent.trim() : null;
                const imageEl = card.querySelector('img');
                const image_url = imageEl ? imageEl.getAttribute('src') || imageEl.getAttribute('data-src') : null;

                // Qty — text containing "Qty."
                let qty = null;
                card.querySelectorAll('span, p, div').forEach(el => {
                    const t = (el.textContent || '').trim();
                    const m = t.match(/Qty\\.?\\s*(\\d+)/i);
                    if (m) qty = parseInt(m[1], 10);
                });

                // Starting price — first $X.XX pattern
                let starting_price = null;
                const allText = card.textContent || '';
                const priceMatch = allText.match(/\\$([0-9][0-9,]*(?:\\.[0-9]{2})?)/);
                if (priceMatch) starting_price = parseFloat(priceMatch[1].replace(/,/g, ''));

                // Bid count — "N bid(s)" pattern
                let bid_count = null;
                const bidMatch = allText.match(/(\\d+)\\s+bids?/i);
                if (bidMatch) bid_count = parseInt(bidMatch[1], 10);

                // Listing type — last button text in the card
                const buttons = card.querySelectorAll('button');
                let listing_type = 'unknown';
                let button_label = null;
                if (buttons.length > 0) {
                    const btnText = (buttons[buttons.length - 1].textContent || '').trim().toLowerCase();
                    button_label = (buttons[buttons.length - 1].textContent || '').trim() || null;
                    if (btnText.includes('pre') || btnText.includes('bid')) listing_type = 'pre_bid';
                    else if (btnText.includes('buy')) listing_type = 'buy_now';
                    else if (btnText.includes('notify') || btnText.includes('save')) listing_type = 'save_notify';
                    else if (btnText.includes('auction')) listing_type = 'active_auction';
                    else listing_type = btnText || 'unknown';
                }
                const badgeCandidates = Array.from(card.querySelectorAll('span, p, div'))
                    .map(el => (el.textContent || '').trim())
                    .filter(Boolean);
                const badge_text = badgeCandidates.find(text => /giveaway|auction|buy now|save|notify|pre-bid|bid/i.test(text)) || null;

                results.push({
                    product_name,
                    qty,
                    starting_price,
                    bid_count,
                    listing_type,
                    image_url,
                    button_label,
                    badge_text,
                    catalog_position: index + 1,
                });
            });
            return results;
        }""")
    except Exception:
        return 0

    if not listings:
        return 0

    scraped_at = utc_now()
    return replace_competitor_listings_snapshot(conn, stream_id, listings, scraped_at)


def run():
    load_dotenv()

    stream_url = os.getenv("WHATNOT_STREAM_URL")
    if not stream_url:
        raise SystemExit("WHATNOT_STREAM_URL is required")

    postgres_mode = require_collector_postgres_runtime()
    db_path = os.getenv("DB_PATH", "").strip() or None
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    poll_interval_ms = int(os.getenv("POLL_INTERVAL_MS", "250"))
    cookies_path = os.getenv("COOKIES_PATH")
    viewer_selector = os.getenv("VIEWER_COUNT_SELECTOR")
    viewer_list_row_selector = os.getenv("VIEWER_LIST_ROW_SELECTOR", "").strip()
    viewer_list_name_selector = os.getenv("VIEWER_LIST_NAME_SELECTOR", "").strip()
    bid_row_selector = os.getenv("BID_ROW_SELECTOR", "").strip()
    bid_name_selector = os.getenv("BID_NAME_SELECTOR", "").strip()
    bid_amount_selector = os.getenv("BID_AMOUNT_SELECTOR", "").strip()
    collector_role = (os.getenv("COLLECTOR_ROLE") or "active").strip().lower() or "active"
    lease_path = os.getenv("COLLECTOR_LEASE_PATH", "").strip()
    lease_ttl_sec = int(os.getenv("COLLECTOR_LEASE_TTL_SEC", "6"))
    # Spectator mode = no company session binding (WHATNOT_SESSION_ID is empty).
    # Shop panel scraping is competitor-only — never run on our own stream.
    is_spectator = not bool(os.getenv("WHATNOT_SESSION_ID", "").strip())
    # Winner ingestion is handled exclusively by the server's
    # /events side-effects processor (_maybe_ingest_winner_event) using the
    # SQLite event id as the idempotency key. Doing it here too would create
    # duplicate auction results because the two paths generate different
    # source_event_ids and both bypass the unique constraint.

    conn = connect(db_path, postgres_mode=postgres_mode)
    init_db(conn)
    started_at = utc_now()
    # Reuse the same stream row for the same live slug/day even for our own
    # collector. If we create a brand-new stream row on every collector restart,
    # the server-side winner queue can miss handoff continuity because the
    # company session keeps hopping between multiple stream_ids for the exact
    # same Whatnot show URL.
    stream_id = get_or_create_spectator_stream(conn, stream_url, started_at)
    conn.commit()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-dev-shm-usage",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
        )
        context = browser.new_context()
        if cookies_path and Path(cookies_path).exists():
            context.add_cookies(load_cookies(cookies_path))
        page = context.new_page()

        page.goto(stream_url, wait_until="domcontentloaded")

        # Wait for Cloudflare challenge to resolve (up to 30 seconds)
        for _cf_wait in range(60):
            _title = page.title() or ""
            if "just a moment" not in _title.lower():
                break
            time.sleep(0.5)
        else:
            print("[collector] WARNING: Cloudflare challenge did not resolve after 30s", flush=True)

        # Whatnot pages often keep background network activity alive indefinitely.
        # If networkidle never arrives, continue scraping instead of killing the collector.
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            print("[collector] WARNING: networkidle timeout; continuing with partially active page", flush=True)
        except Exception as exc:
            if _is_fatal_page_error(exc):
                raise RuntimeError(f"collector_fatal_browser_state: {exc}") from exc
            print(f"[collector] WARNING: initial page settle failed; continuing anyway: {exc}", flush=True)

        try:
            page_title = page.title()
            # Title is typically "username is live - Stream title" or "username's Profile"
            if " is live - " in page_title:
                parts = page_title.split(" is live - ", 1)
                if is_spectator:
                    stream_id = finalize_spectator_stream_identity(conn, stream_id, stream_url, parts[0].strip(), parts[1].strip())
                else:
                    update_stream_metadata(conn, stream_id, streamer_name=parts[0].strip(), title=parts[1].strip())
                conn.commit()
            elif " is live" in page_title:
                parts = page_title.split(" is live", 1)
                if is_spectator:
                    stream_id = finalize_spectator_stream_identity(conn, stream_id, stream_url, parts[0].strip(), page_title)
                else:
                    update_stream_metadata(conn, stream_id, streamer_name=parts[0].strip(), title=page_title)
                conn.commit()
            else:
                if is_spectator:
                    stream_id = finalize_spectator_stream_identity(conn, stream_id, stream_url, title=page_title)
                else:
                    update_stream_metadata(conn, stream_id, title=page_title)
                conn.commit()
        except Exception:
            pass

        # TODO: If login is required, implement login flow here.

        # Whatnot selectors (from UI inspection)
        chat_selector = "[data-testid='chat-message']"
        lot_title_selector = "[data-testid='show-product-title']"
        lot_footer_selector = "footer[class*='LivePlayer_livePlayerFooter'] section"
        lot_price_selector = "strong.tabular-nums"
        lot_winner_selector = "[data-testid='show-winning-status']"
        shipping_info_selector = "[data-testid='show-shipping-info']"

        seen_chat = set()
        recent_chat = deque(maxlen=500)
        known_usernames = set()
        last_lot_title = None
        last_lot_price = None
        last_winner = None
        last_winner_key = None
        last_viewer_count = None
        current_price_str = None
        current_price_value = None
        current_lot_number = None
        current_lot_db_id = None   # row id in the lots table for the active lot
        last_lot_change_ts = 0.0
        last_price_ts = 0.0
        last_auction_state = None
        last_shop_scrape_ts = 0.0
        last_end_banner_check_ts = 0.0
        known_viewers = set()
        seen_bid_events = set()
        recent_bid_signatures = deque(maxlen=500)

        # Extract show ID for redirect detection (e.g. /live/<show_id>)
        _show_id_m = re.search(r'/live/([^/?#]+)', stream_url)
        original_show_id = _show_id_m.group(1) if _show_id_m else None
        _startup_ts = time.time()  # Grace period for stream-end detection

        while True:
            now_ts = time.time()
            _ensure_browser_alive(browser, page)
            can_write = _refresh_write_lease(
                lease_path,
                process_role=collector_role,
                stream_url=stream_url,
                session_id=os.getenv("WHATNOT_SESSION_ID", "").strip() or None,
                ttl_sec=lease_ttl_sec,
            )
            if not can_write:
                time.sleep(min(1.0, max(0.25, poll_interval_ms / 1000.0)))
                continue
            # ── Stream-end detection ──────────────────────────────────────────────
            # Skip stream-end detection during startup grace period (Cloudflare/page load)
            _age = now_ts - _startup_ts
            if _age >= 20:
                # 1. URL redirect check: Whatnot redirects away when a stream ends.
                #    If the browser is no longer on the original show URL, stop collecting.
                current_page_url = page.url
                if original_show_id and original_show_id not in current_page_url:
                    if "whatnot.com" in current_page_url:
                        insert_event(conn, stream_id, "stream_ended", {
                            "reason": "url_changed",
                            "redirected_to": current_page_url,
                        })
                        update_stream_metadata(conn, stream_id, ended_at=utc_now())
                        break
                    if current_page_url.startswith("http"):
                        print(
                            f"[collector] ignoring off-site redirect while stream is active: {current_page_url}",
                            flush=True,
                        )
                    try:
                        page.goto(stream_url, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(1.0)
                        continue
                    except Exception:
                        pass

                # 2. DOM banner check (throttled to every 5 s)
                if now_ts - last_end_banner_check_ts >= 5.0:
                    last_end_banner_check_ts = now_ts
                    try:
                        if page.evaluate(
                            "() => /stream has ended/i.test(document.body?.innerText || '')"
                        ):
                            insert_event(conn, stream_id, "stream_ended", {"reason": "ended_banner"})
                            update_stream_metadata(conn, stream_id, ended_at=utc_now())
                            break
                    except Exception:
                        pass

            # Wrap all DOM queries so a mid-tick page navigation ("Execution context was
            # destroyed") skips the tick rather than crashing the entire collector process.
            try:
                _scroll_chat_to_latest(page)
                # Capture chat messages (virtualized list; de-dupe by content)
                chat_nodes = page.query_selector_all(chat_selector)
                for node in chat_nodes:
                    username, message = _extract_chat_parts(node)
                    if not username and not message:
                        continue
                    chat_index = None
                    try:
                        chat_index = (
                            node.get_attribute("data-index")
                            or node.get_attribute("data-item-index")
                        )
                        if not chat_index:
                            parent = node.evaluate(
                                """(el) => el.closest('[data-index],[data-item-index]')?.getAttribute('data-index')
                                    || el.closest('[data-index],[data-item-index]')?.getAttribute('data-item-index')
                                    || null"""
                            )
                            chat_index = parent or None
                    except Exception:
                        chat_index = None
                    sig = f"{chat_index or ''}|{username}|{message}"
                    if sig in seen_chat:
                        continue
                    seen_chat.add(sig)
                    recent_chat.append(sig)
                    payload = {"username": username, "message": message}
                    insert_event(conn, stream_id, "chat_message", payload)
                    # Track unique chatters in the users table
                    if username and username not in known_usernames:
                        if upsert_user(conn, username):
                            known_usernames.add(username)
                while len(recent_chat) > recent_chat.maxlen:
                    old = recent_chat.popleft()
                    seen_chat.discard(old)

                # Capture current lot data (DOM overlay)
                lot_title_el = page.query_selector(lot_title_selector)
                lot_footer_el = page.query_selector(lot_footer_selector)
                lot_price_el = lot_footer_el.query_selector(lot_price_selector) if lot_footer_el else None
                if lot_footer_el and not lot_price_el:
                    # Fallback: any strong with a $ in the footer section
                    for strong in lot_footer_el.query_selector_all("strong"):
                        text = (strong.inner_text() or "").strip()
                        if re.match(r"^\$\d", text):
                            lot_price_el = strong
                            break
                lot_winner_el = page.query_selector(lot_winner_selector)
                viewer_el = page.query_selector(viewer_selector) if viewer_selector else None
                shipping_info_el = page.query_selector(shipping_info_selector)

                lot_title = None
                if lot_title_el:
                    lot_title = (lot_title_el.get_attribute("title") or "").strip()
                    if not lot_title:
                        lot_title = (lot_title_el.inner_text() or "").strip()
                    if lot_title:
                        lot_title = " ".join(lot_title.split())
                lot_price = lot_price_el.inner_text().strip() if lot_price_el else None
                lot_winner = lot_winner_el.inner_text().strip() if lot_winner_el else None
                viewer_text = viewer_el.inner_text().strip() if viewer_el else None
                shipping_info_visible = bool(shipping_info_el)

                awaiting_next_item = False
                for strong in page.query_selector_all("button strong"):
                    text = (strong.inner_text() or "").strip().lower()
                    if text == "awaiting next item":
                        awaiting_next_item = True
                        break

                footer_text = lot_footer_el.inner_text().strip() if lot_footer_el else ""
                if not lot_price and footer_text:
                    lines = footer_text.splitlines()
                    tail_text = "\n".join(lines[1:]) if len(lines) > 1 else footer_text
                    matches = re.findall(r"\$[0-9][0-9,]*(?:\.[0-9]{2})?", tail_text)
                    if matches:
                        lot_price = matches[-1]

                price_value = None
                if lot_price and not re.match(r"^\$\d", lot_price):
                    # Ignore non-price labels like "Available" or "Pre-bids"
                    lot_price = None
                if lot_price:
                    price_value = _parse_price_token(lot_price)

                if is_spectator:
                    lot_winner = _extract_completed_winner(
                        page,
                        lot_winner_el,
                        lot_footer_el,
                        allow_page_fallback=True,
                    )
                else:
                    lot_winner = _extract_our_stream_winner(
                        lot_winner_el,
                        lot_footer_el,
                    )

                if lot_title and lot_title != last_lot_title:
                    lot_number = _extract_lot_number_from_text(lot_title)
                    # Keep previous lot number if new title doesn't have one
                    if lot_number is None and current_lot_number:
                        lot_number = current_lot_number
                    payload = {"lot_number": lot_number, "product_name": lot_title}
                    insert_event(conn, stream_id, "lot_update", payload)
                    last_lot_title = lot_title
                    current_lot_number = lot_number
                    last_lot_change_ts = time.time()
                    # Reset price for new lot to avoid carryover
                    current_price_str = None
                    current_price_value = None
                    last_lot_price = None
                    last_winner_key = None
                    # Record the lot in the lots table
                    current_lot_db_id = open_lot(conn, stream_id, lot_number, lot_title, utc_now())

                auction_state = None
                if awaiting_next_item:
                    auction_state = "awaiting_next_item"
                elif current_lot_number and (current_price_str or lot_price or lot_winner):
                    auction_state = "awaiting_auction"

                if auction_state and auction_state != last_auction_state:
                    insert_event(conn, stream_id, "auction_state", {
                        "state": auction_state,
                        "lot_number": current_lot_number,
                        "shipping_taxes_extra": shipping_info_visible,
                    })
                    last_auction_state = auction_state

                if lot_price and lot_price != last_lot_price:
                    payload = {
                        "price": lot_price,
                        "price_value": price_value,
                        "lot_number": current_lot_number,
                    }
                    insert_event(conn, stream_id, "bid_update", payload)
                    last_lot_price = lot_price
                    current_price_str = lot_price
                    current_price_value = price_value
                    last_price_ts = time.time()

                if lot_winner and lot_winner != last_winner:
                    if not _looks_like_username(lot_winner):
                        lot_winner = None
                if lot_winner and _winner_signal_is_final(page, lot_winner_el, lot_footer_el):
                    sold_price_str = _extract_sold_price(page, lot_winner_el, lot_footer_el)
                    sold_price_value = _parse_price_token(sold_price_str)
                    # If price wasn't updated yet, try to read it now from footer
                    if sold_price_str:
                        current_price_str = sold_price_str
                        current_price_value = sold_price_value
                    elif not current_price_str or last_price_ts < last_lot_change_ts:
                        current_price_str = _extract_live_bid_price(page, lot_footer_el)
                        current_price_value = _parse_price_token(current_price_str)
                        if current_price_str is None and lot_footer_el:
                            lines = footer_text.splitlines()
                            tail_text = "\n".join(lines[1:]) if len(lines) > 1 else footer_text
                            current_price_str = _extract_price_token(tail_text)
                            current_price_value = _parse_price_token(current_price_str)
                    current_price_str, current_price_value = _choose_final_price(
                        sold_price_str,
                        sold_price_value,
                        current_price_str,
                        current_price_value,
                    )
                    inferred_lot_number = (
                        current_lot_number
                        or _extract_lot_number_from_text(last_lot_title)
                        or _extract_lot_number_from_text(footer_text)
                    )
                    if inferred_lot_number is not None and current_lot_number is None:
                        current_lot_number = inferred_lot_number
                    product_name = last_lot_title or footer_text or None
                    winner_key = (
                        current_lot_number or _extract_lot_number_from_text(product_name) or "",
                        lot_winner,
                        current_price_str or "",
                    )
                    if winner_key == last_winner_key:
                        continue
                    payload = {
                        "winner": lot_winner,
                        "winner_username": lot_winner,
                        "price": current_price_str,
                        "price_value": current_price_value,
                        "lot_number": current_lot_number,
                        "product_name": product_name,
                        "footer_text": footer_text if not current_price_str else None,
                    }
                    insert_event(conn, stream_id, "auction_winner", payload)
                    # Update the lots table with winner + final price
                    if current_lot_db_id:
                        if close_lot(conn, current_lot_db_id, lot_winner, current_price_value, utc_now()):
                            current_lot_db_id = None  # lot is closed
                    # Track winner in users table too
                    if lot_winner and lot_winner not in known_usernames:
                        if upsert_user(conn, lot_winner):
                            known_usernames.add(lot_winner)
                    last_winner = lot_winner
                    last_winner_key = winner_key
                elif not lot_winner and last_winner:
                    # Winner banner disappeared — reset so the next lot's winner
                    # fires even if the same buyer wins again.
                    last_winner = None
                    last_winner_key = None

                if viewer_text:
                    digits = re.findall(r"\d+", viewer_text.replace(",", ""))
                    viewer_count = int(digits[0]) if digits else None
                    if viewer_count is not None and viewer_count != last_viewer_count:
                        insert_event(conn, stream_id, "live_viewers", {"count": viewer_count, "viewer_count": viewer_count})
                        last_viewer_count = viewer_count

                if viewer_list_row_selector and viewer_list_name_selector:
                    current_viewers = {
                        row["name"].lstrip("@").strip()
                        for row in _collect_named_rows(page, viewer_list_row_selector, viewer_list_name_selector)
                        if row["name"]
                    }
                    joined = sorted(current_viewers - known_viewers)
                    left = sorted(known_viewers - current_viewers)
                    for username in joined:
                        insert_event(conn, stream_id, "viewer_join", {
                            "username": username,
                            "lot_number": current_lot_number,
                        })
                    for username in left:
                        insert_event(conn, stream_id, "viewer_leave", {
                            "username": username,
                            "lot_number": current_lot_number,
                        })
                    known_viewers = current_viewers

                if bid_row_selector and bid_name_selector:
                    bid_rows = _collect_named_rows(page, bid_row_selector, bid_name_selector, bid_amount_selector or None)
                    for row in bid_rows:
                        username = (row["name"] or "").lstrip("@").strip()
                        raw_amount = (row.get("extra") or "").strip()
                        amount = None
                        if raw_amount:
                            matches = re.findall(r"\$[0-9][0-9,]*(?:\.[0-9]{2})?", raw_amount)
                            if matches:
                                raw_amount = matches[-1]
                        if raw_amount and "$" in raw_amount:
                            try:
                                amount = float(raw_amount.replace("$", "").replace(",", "").strip())
                            except ValueError:
                                amount = None
                        sig = f"{current_lot_number}|{username}|{raw_amount or amount}"
                        if not username or sig in seen_bid_events:
                            continue
                        seen_bid_events.add(sig)
                        recent_bid_signatures.append(sig)
                        if len(seen_bid_events) > 1000:
                            while len(seen_bid_events) > 600 and recent_bid_signatures:
                                seen_bid_events.discard(recent_bid_signatures.popleft())
                        insert_event(conn, stream_id, "bid_event", {
                            "username": username,
                            "amount": amount,
                            "raw_amount": raw_amount or None,
                            "lot_number": current_lot_number,
                            "product_name": last_lot_title,
                        })
                        if username and username not in known_usernames:
                            if upsert_user(conn, username):
                                known_usernames.add(username)

                # Periodic shop panel scrape — spectator/competitor streams only.
                # Our own stream uses local inventory (scanned items), not this panel.
                if is_spectator:
                    if now_ts - last_shop_scrape_ts >= SHOP_SCRAPE_INTERVAL:
                        scrape_shop_listings(page, conn, stream_id)
                        last_shop_scrape_ts = now_ts

            except Exception as _nav_err:
                _msg = str(_nav_err)
                if _is_fatal_page_error(_msg):
                    print(f"[collector] FATAL: browser/page closed; exiting for supervisor restart: {_msg[:160]}", flush=True)
                    raise RuntimeError(f"collector_fatal_browser_state: {_msg}") from _nav_err
                if any(k in _msg for k in ("Execution context was destroyed", "navigation")):
                    print(f"[collector] page navigated mid-tick, skipping: {_msg[:120]}", flush=True)
                    time.sleep(1.0)
                    continue
                raise

            time.sleep(poll_interval_ms / 1000.0)


if __name__ == "__main__":
    run()
