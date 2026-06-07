#!/usr/bin/env python3
"""Headed-Chrome refresh for the TikTok seller cookies.

Opens a real Chrome window pointed at seller-us.tiktok.com. You log in
manually (password + 2FA if asked). Once you're on the order list page,
press Enter in this terminal and the storage state gets saved into
/home/cybertechna/.tiktok_seller_state.json — the same path the Odoo
video fetcher (`_fetch_tiktok_video_direct`) reads.

Run with the whatnot-collector venv:
    /home/cybertechna/AethrixSystems_Portable/hjay9672-WN /whatnot-collector/.venv/bin/python \
        tools_tiktok_seller_login.py
"""
import json
import os
import shutil
import sys
from pathlib import Path

STATE_PATH = "/home/cybertechna/.tiktok_seller_state.json"
SELLER_URL = "https://seller-us.tiktok.com/order"


def main():
    from playwright.sync_api import sync_playwright

    # Backup the existing state so we can roll back if the new login fails
    if os.path.exists(STATE_PATH):
        backup = STATE_PATH + ".bak"
        shutil.copy2(STATE_PATH, backup)
        print(f"[+] Backed up old cookies -> {backup}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                # Needed when running over `ssh -X` (forwarded X has no GPU/GLX);
                # harmless on a local desktop.
                "--disable-gpu",
            ],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.goto(SELLER_URL, wait_until="domcontentloaded", timeout=30000)
        print("\n[ACTION REQUIRED]")
        print("  1. Log into seller-us.tiktok.com in the Chrome window that just opened.")
        print("  2. Complete any 2FA / captcha.")
        print("  3. Wait until you can see the Order list page.")
        print("  4. THEN come back here and press Enter.\n")
        input(">>> Press Enter once you are logged in: ")

        # Probe: actually call the order API with the captured cookies before saving.
        # If the API still returns 'You must log in', don't overwrite the good backup.
        import urllib.request
        cookies = ctx.cookies()
        cookie_hdr = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        body = b'{"main_order_id":["577406685436612797"]}'
        req = urllib.request.Request(
            "https://seller-us.tiktok.com/api/fulfillment/na/order/get?aid=4068",
            data=body, method="POST",
            headers={
                "Cookie": cookie_hdr,
                "User-Agent": ctx._impl_obj._options["userAgent"]
                if hasattr(ctx, "_impl_obj") else
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
                "Referer": "https://seller-us.tiktok.com/order",
                "Origin": "https://seller-us.tiktok.com",
                "Content-Type": "application/json",
                "Accept": "*/*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read())
        except Exception as exc:
            print(f"[!] Probe call failed: {exc}")
            payload = {}
        code = payload.get("code", "?")
        msg = payload.get("msg") or payload.get("message") or ""
        print(f"[*] Probe response code={code} msg={msg!r}")

        if code in (0, "0", None) and not (msg and "log in" in msg.lower()):
            ctx.storage_state(path=STATE_PATH)
            os.chmod(STATE_PATH, 0o600)
            print(f"[+] Saved fresh cookies -> {STATE_PATH}")
        else:
            print("[!] Probe shows the session still isn't authenticated.")
            print("    NOT overwriting the existing cookies. Old file kept intact.")
            print(f"    Inspect the response above and try again.")
        browser.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Aborted by user.")
        sys.exit(130)
