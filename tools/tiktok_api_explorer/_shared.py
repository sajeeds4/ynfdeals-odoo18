"""Shared helpers for all explorer scripts."""
import json
import sys
import time
from pathlib import Path

STATE_FILE = Path("/home/cybertechna/.tiktok_seller_state.json")
ORDER_GET_URL = "https://seller-us.tiktok.com/api/fulfillment/na/order/get?aid=4068"

UA_CHROME = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def load_cookies():
    if not STATE_FILE.exists():
        sys.exit(f"❌ Cookie state file missing: {STATE_FILE}")
    state = json.loads(STATE_FILE.read_text())
    return {c["name"]: c["value"] for c in state["cookies"]}


def cookie_header():
    return "; ".join(f"{k}={v}" for k, v in load_cookies().items())


def find_key(obj, key):
    """Recursive search for a key in nested dict/list."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for item in obj:
            r = find_key(item, key)
            if r is not None:
                return r
    return None


def report_video(body, label="result"):
    m3u8 = find_key(body, "auction_video_receipt_url")
    ts = find_key(body, "video_receipt_timestamp")
    room = find_key(body, "live_room_id")
    if m3u8:
        print(f"  ✅ {label}: m3u8 found")
        print(f"     m3u8: {m3u8[:140]}")
        print(f"     video_receipt_timestamp_ms: {ts}")
        print(f"     live_room_id: {room}")
        return True
    print(f"  ❌ {label}: no m3u8 in body")
    return False


def order_referer(order_id):
    return f"https://seller-us.tiktok.com/order/detail?order_no={order_id}&shop_region=US"


def require_order_id(argv):
    if len(argv) < 2:
        sys.exit(f"usage: {argv[0]} <order_id>")
    return argv[1].strip()
