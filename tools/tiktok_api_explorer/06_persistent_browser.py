"""Persistent Chromium daemon — launches ONE browser, serves N orders.
Demonstrates speed difference between cold (browser launch) and warm calls.

Run:
  python 06_persistent_browser.py <order_id_1> <order_id_2> ...

Measures per-order latency. First order pays for launch; subsequent orders
should run in ~2s each (just navigation + network wait, no boot)."""
import asyncio, json, sys, time
from playwright.async_api import async_playwright

from _shared import STATE_FILE, order_referer, report_video

if len(sys.argv) < 2:
    sys.exit(f"usage: {sys.argv[0]} <order_id> [order_id...]")

ORDERS = sys.argv[1:]


async def fetch_one(page, order_id):
    captured = {"body": None}

    async def handle(resp):
        if "/api/fulfillment/na/order/get" not in resp.url:
            return
        if captured["body"] is not None:
            return
        try:
            body = await resp.json()
            if "auction_video_receipt_url" in json.dumps(body):
                captured["body"] = body
        except Exception:
            pass

    listener = lambda r: asyncio.create_task(handle(r))
    page.on("response", listener)
    t0 = time.time()
    try:
        await page.goto(order_referer(order_id), wait_until="domcontentloaded", timeout=20000)
    except Exception:
        pass
    for _ in range(40):
        if captured["body"]:
            break
        await asyncio.sleep(0.2)
    elapsed = (time.time() - t0) * 1000
    try:
        page.remove_listener("response", listener)
    except Exception:
        pass
    return elapsed, captured["body"]


async def main():
    async with async_playwright() as p:
        t_boot = time.time()
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=str(STATE_FILE))
        page = await context.new_page()
        print(f"  browser+context boot: {(time.time()-t_boot)*1000:.0f}ms")

        for i, order_id in enumerate(ORDERS, 1):
            elapsed, body = await fetch_one(page, order_id)
            tag = "cold (1st)" if i == 1 else f"warm (#{i})"
            label = f"  order {order_id} [{tag}]: {elapsed:.0f}ms"
            if body:
                from _shared import find_key
                m3u8 = find_key(body, "auction_video_receipt_url")
                print(f"{label}  ✅ m3u8 OK ({(m3u8 or '')[:60]}...)")
            else:
                print(f"{label}  ❌ timed out")

        await context.close()
        await browser.close()

asyncio.run(main())
