"""curl_cffi with Chrome TLS fingerprint. Expected to FAIL (still empty body).
Confirms anti-bot isn't TLS-based; it's request signing."""
import json, sys, time
from curl_cffi import requests as cffi_requests

from _shared import (
    ORDER_GET_URL, UA_CHROME, load_cookies,
    order_referer, report_video, require_order_id,
)

order_id = require_order_id(sys.argv)
cookies = load_cookies()
headers = {
    "Referer": order_referer(order_id),
    "Origin": "https://seller-us.tiktok.com",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-tt-oec-region": "US",
    "User-Agent": UA_CHROME,
}

for impersonate in ["chrome131", "chrome124", "chrome120", "chrome116", "chrome110"]:
    t0 = time.time()
    try:
        r = cffi_requests.post(
            ORDER_GET_URL, cookies=cookies, headers=headers,
            data="", impersonate=impersonate, timeout=15,
        )
        elapsed = (time.time() - t0) * 1000
        body_len = len(r.content or b"")
        has = body_len > 0
        print(f"  {impersonate}: HTTP {r.status_code} in {elapsed:.0f}ms, body={body_len} bytes")
        if has:
            try:
                body = json.loads(r.text)
                if report_video(body, impersonate):
                    sys.exit(0)
            except Exception as exc:
                print(f"    parse error: {exc}")
    except Exception as exc:
        print(f"  {impersonate}: ERROR {exc}")
print("\n  ❌ All TLS fingerprints rejected. Confirms it's signature-based, not TLS.")
