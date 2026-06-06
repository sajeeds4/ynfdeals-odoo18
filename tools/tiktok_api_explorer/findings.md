# Findings — TikTok Seller Internal API Investigation

Date: 2026-05-26

## TL;DR
- The internal endpoint `POST /api/fulfillment/na/order/get?aid=4068` returns
  the m3u8 URL in ~120ms inside a real browser session.
- Outside a real browser session, server returns HTTP 200 with **empty body**.
- The block is a signed header (X-Bogus-style) added by TikTok's JS
  interceptor before the network layer sees the request.
- We cannot replicate the signing trivially. Even calling `fetch()` from
  inside the loaded page via `page.evaluate` bypasses the interceptor.

## What we tried
| # | Method | Result |
|---|---|---|
| 01 | urllib POST with all cookies + CSRF tokens + Sec-Fetch-* | HTTP 200, 0 bytes |
| 02 | curl_cffi mimicking Chrome 110/116/120/124/131 TLS | HTTP 200, 0 bytes |
| 03 | Playwright page.evaluate(fetch) from inside loaded page | HTTP 200, 0 bytes |
| 04 | Playwright page navigation (TikTok's own JS calls API) | ✅ Works, ~6s/order |
| 05 | Direct call with custom X-Bogus header (placeholder) | depends on signature |
| 06 | Persistent Playwright daemon | ~2s/order after first |

## API endpoint
```
POST https://seller-us.tiktok.com/api/fulfillment/na/order/get?aid=4068
Cookie: <full seller cookie set>
Referer: https://seller-us.tiktok.com/order/detail?order_no=<ORDER_ID>&shop_region=US
Origin: https://seller-us.tiktok.com
Content-Type: application/json
x-tt-oec-region: US
X-Bogus: <SIGNED — algorithm hidden in webmssdk.js>
[possibly] msToken: <cookie value>
[possibly] _signature: <SIGNED — companion to X-Bogus>
Body: ""
```

## Response (when signing works)
```json
{
  "code": 0,
  "data": {
    "main_order": [{
      "main_order_id": "...",
      "trade_order_module": { ... },
      "auction_module": {
        "auction_video_receipt_url": "https://pull-hls-f16-thunder-tt01.fcdn.us.tiktokcdn-us.com/stage/stream-XXXXXX/index.m3u8?start=...&end=...&sign=...&ts_sign=true",
        "video_receipt_timestamp": 1800792,
        "live_room_id": 7644046666328197902
      },
      ...
    }]
  }
}
```

## Where the m3u8 URL itself comes from
The m3u8 URL is **pre-signed by TikTok** with `?sign=...` and `?expiry=...`
baked in. Once we have it, we can fetch the playlist + segments directly with
just the Referer header (`seller-us.tiktok.com`) — no signing needed.

So solving X-Bogus solves the WHOLE problem: one signed call gets us a
permanent (6-month-expiry) m3u8 URL.

## Known X-Bogus characteristics (from open-source reversing)
- Computed from `URL_params + body + canvas_fingerprint + UA + timestamp`
- ~28 bytes, base64-like character set
- Algorithm in `webmssdk.js` (heavily obfuscated, name-mangled)
- TikTok rotates the algorithm every 3-6 months on average
- Public reverse-engineered implementations exist (Python/Node/Go) — typically
  break within a quarter of release

## Recommended next steps
If you decide to pursue the direct API path:

1. **Extract the signing function** from a live browser:
   - Open Chrome DevTools on seller-us.tiktok.com
   - Set breakpoint on any `fetch` in the Network panel
   - Step into the call stack until you find the signing wrapper
   - Capture the function code OR identify its module name
2. **Port or wrap** that function to Python:
   - Easy: PyMiniRacer (JS-in-Python) running the extracted code as-is
   - Medium: Translate to pure Python
   - Hard: Extract the obfuscated bytecode and run it via QuickJS
3. **Test against script 05** with the computed X-Bogus
4. **Monitor for rotation** — TikTok will eventually swap the algorithm

## Why this matters for production
Current cold-click time: ~10s (6s Playwright + 4s ffmpeg+first frame).
Direct-API cold-click: ~2s (200ms HTTP + 2s ffmpeg).
Combined with pre-warm + on-disk MP4 cache: **<300ms instant playback**.
