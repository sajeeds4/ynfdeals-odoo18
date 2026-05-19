import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import json


def load_cookies(path: str):
    raw = json.loads(Path(path).read_text())
    cookies = []
    for c in raw:
        same_site = (c.get("sameSite") or "Lax").lower()
        if same_site in ("no_restriction", "none"):
            same_site = "None"
        elif same_site == "strict":
            same_site = "Strict"
        else:
            same_site = "Lax"
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain"),
            "path": c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": same_site,
        }
        if "expirationDate" in c:
            cookie["expires"] = c["expirationDate"]
        cookies.append(cookie)
    return cookies


load_dotenv()
stream_url = os.getenv("WHATNOT_STREAM_URL")
cookies_path = os.getenv("COOKIES_PATH")

if not stream_url:
    raise SystemExit("Set WHATNOT_STREAM_URL in .env")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir="/home/cybertechna/.whatnot-profile",
        headless=False,
        channel="chrome",
    )
    if cookies_path and Path(cookies_path).exists():
        context.add_cookies(load_cookies(cookies_path))
    page = context.new_page()
    page.goto(stream_url)
    input("Page opened. Use DevTools to inspect selectors. Press Enter to close...")
    context.close()
