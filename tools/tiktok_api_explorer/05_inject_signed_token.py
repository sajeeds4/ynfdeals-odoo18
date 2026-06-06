"""HAND-OFF POINT: when you can compute X-Bogus, try the direct call here.

Usage:
  python 05_inject_signed_token.py <order_id> --x-bogus=<value> [--ms-token=<value>] [--signature=<value>]

Or to dry-run with empty headers (will fail same as 01):
  python 05_inject_signed_token.py <order_id>

If the call succeeds (non-empty body with auction_video_receipt_url), the
integration into production is straightforward — see README.md.
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error

from _shared import (
    ORDER_GET_URL, UA_CHROME, cookie_header, load_cookies,
    order_referer, report_video,
)

ap = argparse.ArgumentParser()
ap.add_argument("order_id")
ap.add_argument("--x-bogus", dest="xbogus", default="")
ap.add_argument("--ms-token", dest="ms_token", default="")
ap.add_argument("--signature", dest="signature", default="")
ap.add_argument("--url", default=None,
                help="Override URL (e.g. paste an X-Bogus-signed URL with query param)")
args = ap.parse_args()

cookies = load_cookies()
url = args.url or ORDER_GET_URL

headers = {
    "Cookie": cookie_header(),
    "User-Agent": UA_CHROME,
    "Referer": order_referer(args.order_id),
    "Origin": "https://seller-us.tiktok.com",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-csrftoken": cookies.get("csrftoken", ""),
    "x-tt-passport-csrf-token": cookies.get("passport_csrf_token", ""),
    "x-tt-oec-region": "US",
}
if args.xbogus:
    headers["X-Bogus"] = args.xbogus
if args.ms_token:
    headers["msToken"] = args.ms_token
if args.signature:
    headers["_signature"] = args.signature

print(f"  URL: {url}")
print(f"  X-Bogus: {'<set>' if args.xbogus else '<empty>'}")
print(f"  msToken: {'<set>' if args.ms_token else '<empty>'}")
print(f"  _signature: {'<set>' if args.signature else '<empty>'}")

req = urllib.request.Request(url, data=b"", method="POST", headers=headers)
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        elapsed = (time.time() - t0) * 1000
        print(f"  HTTP {resp.status} in {elapsed:.0f}ms, body={len(raw)} bytes")
        if not raw:
            print("  ❌ empty body — signature still wrong/missing")
            sys.exit(2)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            print(f"  parse error: {exc}; first 300 bytes: {raw[:300]}")
            sys.exit(2)
        if report_video(body, "signed direct"):
            print(f"\n  🎯 SIGNATURE WORKS — integration plan in README.md section 'When you solve X-Bogus'")
            sys.exit(0)
        print(f"  body code: {body.get('code')}, msg: {body.get('msg')}")
        print(f"  body keys: {list(body.keys())[:20]}")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code}: {e.read()[:400]}")
except Exception as exc:
    print(f"  ERROR: {exc}")
