"""Baseline: vanilla urllib POST. Expected to FAIL (empty body)."""
import json, sys, time, urllib.request, urllib.error

from _shared import (
    ORDER_GET_URL, UA_CHROME, cookie_header, load_cookies,
    order_referer, report_video, require_order_id,
)

order_id = require_order_id(sys.argv)
cookies = load_cookies()

headers = {
    "Cookie": cookie_header(),
    "User-Agent": UA_CHROME,
    "Referer": order_referer(order_id),
    "Origin": "https://seller-us.tiktok.com",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-csrftoken": cookies.get("csrftoken", ""),
    "x-tt-passport-csrf-token": cookies.get("passport_csrf_token", ""),
    "x-tt-oec-region": "US",
}

req = urllib.request.Request(ORDER_GET_URL, data=b"", method="POST", headers=headers)
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        elapsed = (time.time() - t0) * 1000
        print(f"HTTP {resp.status}  in {elapsed:.0f}ms  body={len(raw)} bytes")
        if raw:
            try:
                body = json.loads(raw.decode("utf-8"))
                report_video(body, "urllib")
            except Exception as exc:
                print(f"  parse error: {exc}")
        else:
            print("  ❌ empty body — anti-bot blocked (expected baseline)")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code}: {e.read()[:300]}")
except Exception as exc:
    print(f"  ERROR: {exc}")
