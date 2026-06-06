"""WINNING APPROACH — direct urllib POST, no signing required.

Discovery: the empty-body failure in scripts 01/02/03 was caused by sending
an empty request body. The browser sends `{"main_order_id":["<id>"]}` and so
must we. Once we do, the call works in ~400ms with no signing, no X-Bogus,
no Playwright navigation.

Usage:
  python 08_direct_urllib.py <order_id>

Cookies are loaded from STATE_FILE (~/.tiktok_seller_state.json). They must
be reasonably fresh — refresh via a Playwright login or a `06_persistent_browser`
warm-up if the call returns empty/expired.
"""
import json
import sys
import time
import urllib.request

from _shared import STATE_FILE, UA_CHROME, find_key, require_order_id

order_id = require_order_id(sys.argv)

state = json.loads(STATE_FILE.read_text())
cookie_jar = state.get("cookies", [])
cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookie_jar)

url = "https://seller-us.tiktok.com/api/fulfillment/na/order/get?aid=4068"
body = json.dumps({"main_order_id": [order_id]}).encode()
headers = {
    "Cookie": cookie_header,
    "User-Agent": UA_CHROME,
    "Referer": f"https://seller-us.tiktok.com/order/detail?order_no={order_id}&shop_region=US",
    "Origin": "https://seller-us.tiktok.com",
    "Content-Type": "application/json",
    "Accept": "*/*",
}

t0 = time.time()
req = urllib.request.Request(url, data=body, method="POST", headers=headers)
with urllib.request.urlopen(req, timeout=15) as resp:
    raw = resp.read()
    ms = (time.time() - t0) * 1000
    print(f"  HTTP {resp.status} in {ms:.0f}ms, body={len(raw)} bytes")
    payload = json.loads(raw.decode("utf-8"))

m3u8 = find_key(payload, "auction_video_receipt_url")
ts = find_key(payload, "video_receipt_timestamp")
room = find_key(payload, "live_room_id")
if m3u8:
    print(f"  m3u8: {m3u8}")
    print(f"  seek_offset_ms: {ts}")
    print(f"  live_room_id: {room}")
else:
    print(f"  code={payload.get('code')} msg={payload.get('message')}")
    print(f"  (no auction_video_receipt_url — order may not have a live video)")
