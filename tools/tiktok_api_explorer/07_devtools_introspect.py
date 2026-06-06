"""Use Playwright as a 'DevTools probe' to find the X-Bogus signing function
inside TikTok's webmssdk.js — then expose it so we can call it from Python.

Strategy:
  1. Load any seller page so webmssdk loads
  2. Monkey-patch window.fetch BEFORE the page's JS runs, so we can see
     every signed request that goes out — captures URL + final headers
  3. Walk window.* looking for functions named *bogus*, *sign*, *acrawler*
  4. If found, try calling them via page.evaluate for a custom URL
  5. Report all signing candidates + sample signed URLs

Run:
  python 07_devtools_introspect.py
"""
import asyncio, json, time
from playwright.async_api import async_playwright

from _shared import STATE_FILE

INIT_SCRIPT = r"""
// Monkey-patch BEFORE TikTok's JS runs.
// Capture every signed request and any signing functions installed on window.
(() => {
    window.__captures = { fetches: [], signers: [], xhrs: [] };

    const origFetch = window.fetch;
    window.fetch = function(input, init = {}) {
        try {
            const url = (typeof input === 'string') ? input : input.url;
            const method = (init.method || 'GET').toUpperCase();
            const headers = init.headers || {};
            const headerObj = {};
            if (headers instanceof Headers) {
                headers.forEach((v, k) => headerObj[k] = v);
            } else {
                Object.assign(headerObj, headers);
            }
            window.__captures.fetches.push({
                url, method,
                headerSample: headerObj,
                ts: Date.now(),
            });
        } catch (e) {}
        return origFetch.apply(this, arguments);
    };

    const origXHRSend = XMLHttpRequest.prototype.send;
    const origXHROpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {
        this.__url = url;
        this.__method = method;
        return origXHROpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(body) {
        try {
            window.__captures.xhrs.push({
                url: this.__url,
                method: this.__method,
                ts: Date.now(),
            });
        } catch (e) {}
        return origXHRSend.apply(this, arguments);
    };
})();
"""


SCAN_SCRIPT = r"""
() => {
    // Walk window.* for any property that looks like a signing function
    const out = {
        windowKeys: [],
        candidates: [],
        captures: window.__captures || {},
    };
    const seen = new Set();
    const interesting = /bogus|gnarly|signature|sign|acrawler|webmssdk|mssdk|secsdk|byted|tt[_-]?req/i;

    const walk = (obj, path, depth) => {
        if (depth > 3 || seen.size > 20000) return;
        if (obj === null || obj === undefined) return;
        let keys;
        try { keys = Object.keys(obj); } catch (e) { return; }
        for (const k of keys) {
            const full = path ? `${path}.${k}` : k;
            if (seen.has(full)) continue;
            seen.add(full);
            if (interesting.test(k) || interesting.test(full)) {
                out.windowKeys.push(full);
                try {
                    const v = obj[k];
                    if (typeof v === 'function') {
                        out.candidates.push({
                            path: full,
                            type: 'function',
                            name: v.name || '',
                            length: v.length,
                            source: (v.toString() || '').slice(0, 600),
                        });
                    } else if (typeof v === 'object') {
                        out.candidates.push({
                            path: full,
                            type: 'object',
                            keys: (() => { try { return Object.keys(v); } catch(e) { return []; } })(),
                        });
                        walk(v, full, depth + 1);
                    }
                } catch (e) {}
            } else if (depth < 2) {
                try {
                    const v = obj[k];
                    if (typeof v === 'object' && v !== null) walk(v, full, depth + 1);
                } catch (e) {}
            }
        }
    };
    walk(window, '', 0);
    return out;
}
"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=str(STATE_FILE))
        # Inject our hooks BEFORE the page loads
        await context.add_init_script(INIT_SCRIPT)
        page = await context.new_page()

        print("→ Loading seller order page (so webmssdk.js loads + signs)...")
        t0 = time.time()
        await page.goto(
            "https://seller-us.tiktok.com/order/detail?order_no=577406169738941145&shop_region=US",
            wait_until="domcontentloaded", timeout=20000,
        )
        # Let TikTok's JS make its own API calls so signing JS is fully loaded
        await asyncio.sleep(4)
        print(f"  page loaded + settled in {(time.time()-t0)*1000:.0f}ms")

        print("\n→ Scanning window.* for signing functions...")
        result = await page.evaluate(SCAN_SCRIPT)
        captures = result.get("captures", {})
        fetches = captures.get("fetches", [])
        signers = result.get("candidates", [])
        keys = result.get("windowKeys", [])

        print(f"\n  Captured {len(fetches)} fetch() calls during page load")
        print(f"  Found {len(keys)} window properties matching signing keywords")
        print(f"  Function candidates: {sum(1 for s in signers if s.get('type') == 'function')}")

        print("\n=== Top fetch() URLs (first 10) ===")
        for f in fetches[:10]:
            print(f"  [{f['method']}] {f['url'][:120]}")
            xb = (f.get('headerSample') or {}).get('X-Bogus') or (f.get('headerSample') or {}).get('x-bogus')
            if xb:
                print(f"    X-Bogus seen in headerSample: {xb}")

        print("\n=== Signing function candidates ===")
        for s in signers:
            if s.get('type') == 'function':
                print(f"  PATH: {s['path']}  (name={s.get('name','')!r}, args={s.get('length',0)})")
                print(f"    source[:200]: {s.get('source','')[:200]!r}")
                print()
            elif s.get('type') == 'object':
                ks = s.get('keys', [])
                if ks:
                    print(f"  OBJ: {s['path']}  keys: {ks[:10]}")

        # If we found a likely signer, try to call it for our endpoint
        plausible = [s for s in signers if s.get('type') == 'function' and any(
            k in s.get('path', '').lower() for k in ('bogus', 'sign')
        )]
        if plausible:
            print(f"\n=== Trying to invoke {len(plausible)} plausible signer(s) ===")
            for s in plausible[:5]:
                path = s['path']
                target_url = "/api/fulfillment/na/order/get?aid=4068"
                try_code = (
                    "(p, u) => { "
                    "try { "
                    "  const fn = p.split('.').reduce((o,k) => o && o[k], window); "
                    "  if (!fn) return {ok:false, err:'not found'}; "
                    "  const r = fn(u, '', '');"
                    "  return {ok:true, result: String(r).slice(0,200)}; "
                    "} catch(e) { return {ok:false, err: e.message}; } "
                    "}"
                )
                try:
                    res = await page.evaluate(try_code, [path, target_url])
                    print(f"  {path}: {res}")
                except Exception as e:
                    print(f"  {path}: ERROR {e}")

        await context.close()
        await browser.close()


asyncio.run(main())
