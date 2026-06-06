"""Try fetch() from inside a loaded page via Playwright evaluate.
Expected to FAIL — bypasses the JS fetch interceptor that signs requests."""
import asyncio, json, sys, time
from playwright.async_api import async_playwright

from _shared import (
    STATE_FILE, ORDER_GET_URL, order_referer,
    report_video, require_order_id,
)

order_id = require_order_id(sys.argv)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=str(STATE_FILE))
        page = await context.new_page()
        t0 = time.time()
        await page.goto(order_referer(order_id), wait_until="domcontentloaded", timeout=20000)
        print(f"  nav: {(time.time()-t0)*1000:.0f}ms")
        await asyncio.sleep(2.5)  # let JS settle

        t1 = time.time()
        result = await page.evaluate('''
            async () => {
                const r = await fetch("/api/fulfillment/na/order/get?aid=4068", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: "",
                });
                return {status: r.status, body: await r.text()};
            }
        ''')
        print(f"  evaluate(fetch): {(time.time()-t1)*1000:.0f}ms, status={result['status']}, body_len={len(result.get('body',''))}")
        body_str = result.get("body", "")
        if body_str:
            try:
                report_video(json.loads(body_str), "evaluate(fetch)")
            except Exception as exc:
                print(f"  parse error: {exc}")
        else:
            print("  ❌ empty body — JS interceptor bypassed")
        await context.close()
        await browser.close()

asyncio.run(main())
