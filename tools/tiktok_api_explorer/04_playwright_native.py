"""The currently-working approach: navigate to the order page, let TikTok's
own JS auto-call the API, and intercept the network response.
~6s/order — slow but reliable. This mirrors what production uses."""
import asyncio, json, sys, time
from playwright.async_api import async_playwright

from _shared import (
    STATE_FILE, order_referer, report_video, require_order_id,
)

order_id = require_order_id(sys.argv)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=str(STATE_FILE))
        page = await context.new_page()
        captured = {"body": None, "ts": None}

        async def on_response(resp):
            if "/api/fulfillment/na/order/get" not in resp.url:
                return
            if captured["body"] is not None:
                return
            try:
                body = await resp.json()
                if "auction_video_receipt_url" in json.dumps(body):
                    captured["body"] = body
                    captured["ts"] = time.time()
            except Exception:
                pass

        page.on("response", lambda r: asyncio.create_task(on_response(r)))

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
        print(f"  total: {elapsed:.0f}ms")
        if captured["body"]:
            report_video(captured["body"], "native")
        else:
            print("  ❌ timed out without capturing response")
        await context.close()
        await browser.close()

asyncio.run(main())
