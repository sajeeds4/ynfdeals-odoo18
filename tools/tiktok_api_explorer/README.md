# TikTok Seller API Explorer

Sandboxed tools to experiment with calling TikTok's internal seller-center API
**directly** (bypassing Playwright). Nothing here touches production Odoo.

## The goal
Replace the current ~6-second Playwright page navigation with a ~200ms HTTP call
to `POST /api/fulfillment/na/order/get?aid=4068`.

## The blocker
TikTok's web bundle adds a signed header (`X-Bogus`-style) to every API request
**before** the network layer sees it. Calls without that signature get HTTP 200
with an empty body — silent rejection.

## What's in this folder

| File | Purpose |
|---|---|
| `01_raw_http.py` | Bare-metal urllib POST. Confirms baseline (empty body). |
| `02_curl_cffi.py` | TLS-fingerprint-mimicking client. Also fails. Confirms it's not a TLS issue. |
| `03_playwright_evaluate.py` | Calls fetch from inside a loaded page via `page.evaluate`. Still fails — bypasses the JS signing layer. |
| `04_playwright_native.py` | The working approach: navigate to the order page and let TikTok's own JS call its API. ~6s/order. |
| `05_inject_signed_token.py` | **Hand-off point.** If you can compute X-Bogus, paste it here and the script will try the direct call. |
| `06_persistent_browser.py` | Keep one headless Chromium running, navigate per-order. ~2s/order (skips the browser launch cost). |
| `findings.md` | All observations, JSON payload shapes, header lists. |

## How to use

```bash
cd /home/cybertechna/AethrixSystems_Portable/hjay9672-WN\ /tools/tiktok_api_explorer
PYBIN="/home/cybertechna/AethrixSystems_Portable/hjay9672-WN /whatnot-collector/.venv/bin/python"

# Reproduce the failure paths (baseline)
$PYBIN 01_raw_http.py 577406164611404258
$PYBIN 02_curl_cffi.py 577406164611404258
$PYBIN 03_playwright_evaluate.py 577406164611404258

# The currently-working method (slow but reliable)
$PYBIN 04_playwright_native.py 577406164611404258

# The hopeful path — paste your computed X-Bogus signature
$PYBIN 05_inject_signed_token.py 577406164611404258 <your-x-bogus-here>

# The compromise path
$PYBIN 06_persistent_browser.py 577406164611404258
```

## Cookie source
All scripts read from `/home/cybertechna/.tiktok_seller_state.json` — the same
file production uses. Cookies expire ~24-48h; re-paste from a fresh browser
session when they do.

## Key API endpoint discovered
```
POST https://seller-us.tiktok.com/api/fulfillment/na/order/get?aid=4068
Headers:
  Cookie: <seller cookies>
  Referer: https://seller-us.tiktok.com/order/detail?order_no=<ORDER_ID>&shop_region=US
  Content-Type: application/json
  Origin: https://seller-us.tiktok.com
  x-tt-oec-region: US
  X-Bogus: <signed token>          ← THIS is the missing piece
  (possibly also: msToken, X-Gnarly, _signature)
Body: ""

Response JSON path:
  data.main_order[].auction_module.auction_video_receipt_url      ← the m3u8
  data.main_order[].auction_module.video_receipt_timestamp        ← seek offset (ms)
  data.main_order[].auction_module.live_room_id                   ← the live broadcast
```

## When you solve X-Bogus
Once `05_inject_signed_token.py` returns a populated body, the integration into
production is small:

1. Add a Python module that generates X-Bogus given URL + body + ts
2. Replace `fetch_tiktok_video.py`'s Playwright call with a curl_cffi POST
3. Keep Playwright as fallback if signing ever returns 403

That swap shrinks the cold-click time from ~10s → ~2s. Combined with the
existing pre-warm + on-disk MP4 cache, every operator click becomes <300ms.
