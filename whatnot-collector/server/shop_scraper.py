"""
Competitor shop scraper.

Scrapes all products from https://www.whatnot.com/user/{username}/shop
using Playwright. No login required — shop pages are public.

Runs in a background thread (asyncio.run) so it doesn't block the API server.
Normal runtime is Postgres-only.
"""
import asyncio
import threading
import time
from datetime import datetime, timezone

from .config import (
    COLLECTOR_HEADLESS,
    POSTGRES_SIDECAR_SCHEMA,
    SHOP_AUTOSCRAPE_ENABLED,
    SHOP_AUTOSCRAPE_INTERVAL_SEC,
    SHOP_AUTOSCRAPE_MIN_HOURS,
    SHOP_AUTOSCRAPE_WARMUP_SEC,
    SHOP_AUTOSCRAPE_MAX_PER_CYCLE,
)
from .postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, log_cutover_event, postgres_available

# ── In-memory scrape status ────────────────────────────────────────────────
# { streamer_name_lower: { status, started_at, finished_at, product_count, error } }
_status: dict = {}
_status_lock = threading.Lock()
_autoscrape_thread = None
_autoscrape_lock = threading.Lock()


def _ensure_pg_table():
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products (
                    id            BIGSERIAL PRIMARY KEY,
                    streamer_name TEXT NOT NULL,
                    scraped_at    TEXT NOT NULL,
                    product_name  TEXT,
                    price         DOUBLE PRECISION,
                    qty           INTEGER,
                    image_url     TEXT,
                    listing_url   TEXT
                )
                """
            )
            cur.execute(
                f"""
                CREATE SEQUENCE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products_id_seq
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products
                ALTER COLUMN id SET DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products_id_seq')
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_shop_products_streamer
                ON {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products (LOWER(streamer_name), scraped_at)
                """
            )
            cur.execute(
                f"""
                SELECT setval(
                    '{POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products_id_seq',
                    GREATEST(
                        1,
                        COALESCE((SELECT MAX(id) FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products), 0) + 1
                    ),
                    false
                )
                """
            )
        conn.commit()


def _require_postgres_shop_runtime(db_path: str | None = None) -> None:
    if db_path:
        raise RuntimeError("shop_scraper_sqlite_runtime_retired")
    if not postgres_available():
        raise RuntimeError("shop_scraper_postgres_runtime_required")


def get_scrape_status(streamer_name: str) -> dict:
    key = streamer_name.lower()
    with _status_lock:
        return dict(_status.get(key, {"status": "idle"}))


def _parse_iso(ts: str | None):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def get_latest_shop_scrape_times(db_path: str = None) -> dict:
    _require_postgres_shop_runtime(db_path)
    return _pg_get_latest_shop_scrape_times()


def _pg_get_latest_shop_scrape_times() -> dict:
    _ensure_pg_table()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT LOWER(streamer_name), MAX(scraped_at)
                FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products
                GROUP BY LOWER(streamer_name)
                """
            )
            return {row[0]: row[1] for row in cur.fetchall() if row[0]}


def get_shop_products(streamer_name: str, db_path: str = None) -> dict:
    """Return the latest shop scrape for a streamer (most recent scraped_at batch)."""
    _require_postgres_shop_runtime(db_path)
    return _pg_get_shop_products(streamer_name)


def _pg_get_shop_products(streamer_name: str) -> dict:
    _ensure_pg_table()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(scraped_at)
                FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products
                WHERE LOWER(streamer_name) = %s
                """,
                (streamer_name.lower(),),
            )
            row = cur.fetchone()
            latest = row[0] if row else None
            if not latest:
                return {"products": [], "scraped_at": None, "total": 0}
            cur.execute(
                f"""
                SELECT product_name, price, qty, image_url, listing_url
                FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products
                WHERE LOWER(streamer_name) = %s AND scraped_at = %s
                ORDER BY id ASC
                """,
                (streamer_name.lower(), latest),
            )
            products = [
                {
                    "product_name": row[0],
                    "price": row[1],
                    "qty": row[2],
                    "image_url": row[3],
                    "listing_url": row[4],
                }
                for row in cur.fetchall()
            ]
            return {"products": products, "scraped_at": latest, "total": len(products)}


def _pg_save_products(streamer_name: str, products: list, scraped_at: str):
    _ensure_pg_table()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products WHERE LOWER(streamer_name) = %s",
                (streamer_name.lower(),),
            )
            if products:
                cur.executemany(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.competitor_shop_products
                    (streamer_name, scraped_at, product_name, price, qty, image_url, listing_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            streamer_name,
                            scraped_at,
                            p.get("product_name"),
                            p.get("price"),
                            p.get("qty"),
                            p.get("image_url"),
                            p.get("listing_url"),
                        )
                        for p in products
                    ],
                )
        conn.commit()


def _save_products_compat(streamer_name: str, products: list, scraped_at: str, db_path: str | None):
    _require_postgres_shop_runtime(db_path)
    try:
        _pg_save_products(streamer_name, products, scraped_at)
    except Exception as exc:
        log_cutover_event(
            "shop_scraper_writes",
            "postgres_primary_failed_closed",
            "competitor_shop_products",
            streamer_name.lower(),
            {"error": str(exc)},
        )
        raise


# ── Playwright scraper ────────────────────────────────────────────────────────

_EXTRACT_JS = """
() => {
    // Match cards: look for the anchor links to /listing/ paths
    const links = document.querySelectorAll('a[href*="/listing/"]');
    const seen = new Set();
    const results = [];

    for (const link of links) {
        const href = link.getAttribute('href') || '';
        if (!href || seen.has(href)) continue;
        seen.add(href);

        const card = link.closest('section') || link.parentElement;
        if (!card) continue;

        // Product name — strong with a title that is NOT a price
        let name = null;
        for (const s of card.querySelectorAll('strong[title]')) {
            if (!s.title.startsWith('$') && s.title.trim()) {
                name = s.title.trim();
                break;
            }
        }
        if (!name) {
            // Fallback: alt text of first image
            const img = card.querySelector('img');
            if (img && img.alt && !img.alt.match(/^Front$/i)) name = img.alt.trim();
        }
        if (!name) continue;

        // Price
        let price = null;
        for (const s of card.querySelectorAll('strong[title]')) {
            if (s.title.startsWith('$')) {
                const n = parseFloat(s.title.replace(/[^0-9.]/g, ''));
                if (!isNaN(n)) { price = n; break; }
            }
        }

        // Qty
        let qty = null;
        for (const s of card.querySelectorAll('strong')) {
            const m = s.textContent.match(/Qty\\.\\s*(\\d+)/);
            if (m) { qty = parseInt(m[1]); break; }
        }

        // Best image from srcset (256px variant)
        let imageUrl = null;
        const img = card.querySelector('img[srcset]');
        if (img) {
            const srcs = img.srcset.split(',').map(s => s.trim());
            // Try to find 256w entry
            let chosen = null;
            for (const s of srcs) {
                const parts = s.split(' ');
                if (parts.length >= 2 && parts[1] === '256w') {
                    chosen = parts[0];
                    break;
                }
            }
            imageUrl = chosen || img.src || null;
        }

        results.push({
            product_name: name,
            price: price,
            qty: qty,
            image_url: imageUrl,
            listing_url: 'https://www.whatnot.com' + href,
        });
    }
    return results;
}
"""

_COUNT_JS = """
() => {
    // Extract total product count from e.g. "Products (539)"
    const headers = document.querySelectorAll('strong, h1, h2, h3, [class*="title"]');
    for (const el of headers) {
        const m = el.textContent.match(/Products\\s*\\((\\d+)\\)/i);
        if (m) return parseInt(m[1]);
    }
    return null;
}
"""


async def _run_scrape(username: str, db_path: str):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright not installed — run: pip install playwright && playwright install chromium")

    key = username.lower()
    scraped_at = datetime.now(timezone.utc).isoformat()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=COLLECTOR_HEADLESS != "0",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )

        try:
            shop_url = f"https://www.whatnot.com/user/{username}/shop"
            await page.goto(shop_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # The shop grid often renders listing links before they're considered "visible",
            # so use a count-based readiness check instead of a visibility wait.
            await page.wait_for_function(
                """() => {
                    const links = document.querySelectorAll('a[href*="/listing/"]');
                    return links && links.length > 0;
                }""",
                timeout=20000,
            )
            await page.wait_for_timeout(1500)

            total_expected = await page.evaluate(_COUNT_JS)

            # Scroll to load all products (infinite scroll)
            stale_rounds = 0
            last_count = 0
            max_rounds = 80  # safety cap

            for _ in range(max_rounds):
                current = await page.evaluate(
                    "() => document.querySelectorAll('a[href*=\"/listing/\"]').length"
                )
                unique = await page.evaluate(
                    "() => new Set([...document.querySelectorAll('a[href*=\"/listing/\"]')].map(a=>a.getAttribute('href'))).size"
                )

                # Update live count in status
                with _status_lock:
                    if key in _status:
                        _status[key]["product_count"] = unique

                if total_expected and unique >= total_expected:
                    break  # loaded everything

                if unique <= last_count:
                    stale_rounds += 1
                    if stale_rounds >= 4:
                        break  # no more loading
                else:
                    stale_rounds = 0

                last_count = unique

                # Scroll progressively so virtualized grids keep materializing cards.
                await page.evaluate(
                    """() => {
                        const step = Math.max(window.innerHeight * 0.9, 700);
                        window.scrollBy(0, step);
                    }"""
                )
                await page.wait_for_timeout(900)

            # Final fallback if the scroll loop never materialized products.
            if last_count == 0:
                await page.wait_for_timeout(2000)

            # Final extraction
            products = await page.evaluate(_EXTRACT_JS)

        finally:
            await browser.close()

    return products, scraped_at


def _thread_scrape(username: str, db_path: str):
    key = username.lower()
    try:
        products, scraped_at = asyncio.run(_run_scrape(username, db_path))
        _save_products_compat(username, products, scraped_at, db_path)
        with _status_lock:
            _status[key].update({
                "status": "done",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "product_count": len(products),
                "error": None,
            })
    except Exception as exc:
        with _status_lock:
            if key in _status:
                _status[key].update({
                    "status": "error",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                })


def start_shop_scrape(username: str, db_path: str = None, synchronous: bool = False) -> bool:
    """
    Start a background shop scrape for the given username.
    Returns False if a scrape is already running for this user.
    """
    _require_postgres_shop_runtime(db_path)
    key = username.lower()
    db = db_path
    with _status_lock:
        current = _status.get(key, {})
        if current.get("status") == "running":
            return False  # already in progress
        _status[key] = {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "product_count": 0,
            "error": None,
        }

    if synchronous:
        _thread_scrape(username, db)
    else:
        t = threading.Thread(target=_thread_scrape, args=(username, db), daemon=True)
        t.start()
    return True


def _due_shop_scrape_targets(db_path: str = None):
    _require_postgres_shop_runtime(db_path)
    db = db_path
    latest_map = get_latest_shop_scrape_times(db)
    from .events_db import get_competitor_businesses

    businesses = get_competitor_businesses(db_path=db)
    now = datetime.now(timezone.utc)
    due = []
    for business in businesses:
        streamer_name = (business.get("streamer_name") or "").strip()
        if not streamer_name:
            continue
        latest = _parse_iso(latest_map.get(streamer_name.lower()))
        age_hours = None
        if latest:
            age_hours = (now - latest).total_seconds() / 3600.0
        if age_hours is None or age_hours >= SHOP_AUTOSCRAPE_MIN_HOURS:
            due.append({
                "streamer_name": streamer_name,
                "last_scraped_at": latest_map.get(streamer_name.lower()),
                "age_hours": round(age_hours, 1) if age_hours is not None else None,
                "sessions": len(business.get("sessions") or []),
            })
    due.sort(key=lambda row: (row["age_hours"] is None, row["age_hours"] or 0), reverse=True)
    if SHOP_AUTOSCRAPE_MAX_PER_CYCLE > 0:
        due = due[:SHOP_AUTOSCRAPE_MAX_PER_CYCLE]
    return due


def _autoscrape_loop(db_path: str):
    if SHOP_AUTOSCRAPE_WARMUP_SEC > 0:
        time.sleep(SHOP_AUTOSCRAPE_WARMUP_SEC)
    while True:
        try:
            due = _due_shop_scrape_targets(db_path)
            if due:
                print(f"[shop-autoscrape] due targets: {len(due)}")
            for row in due:
                streamer_name = row["streamer_name"]
                started = start_shop_scrape(streamer_name, db_path=db_path, synchronous=True)
                if started:
                    print(
                        f"[shop-autoscrape] scraped {streamer_name}"
                        f" (last={row['last_scraped_at'] or 'never'}, age_hours={row['age_hours']})"
                    )
                else:
                    print(f"[shop-autoscrape] skipped {streamer_name} (already running)")
                time.sleep(2)
        except Exception as exc:
            print(f"[shop-autoscrape] cycle failed: {exc}")
        time.sleep(max(60, SHOP_AUTOSCRAPE_INTERVAL_SEC))


def start_shop_autoscrape_scheduler(db_path: str = None) -> bool:
    global _autoscrape_thread
    if not SHOP_AUTOSCRAPE_ENABLED:
        return False
    _require_postgres_shop_runtime(db_path)
    with _autoscrape_lock:
        if _autoscrape_thread and _autoscrape_thread.is_alive():
            return False
        db = db_path
        _autoscrape_thread = threading.Thread(
            target=_autoscrape_loop,
            args=(db,),
            daemon=True,
            name="shop-autoscrape",
        )
        _autoscrape_thread.start()
        return True
