import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*_args, **_kwargs):
        return False


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
DEFAULT_FILTERS = (
    "webcast",
    "im-ws",
    "tiktok.com/api",
    "live",
    "room",
    "chat",
    "gift",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value or "").strip("_") or "probe"


def load_cookies(path: str):
    text = Path(path).read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        raw = json.loads(text)
        return _load_json_cookies(raw)
    return _load_netscape_cookies(text)


def _load_json_cookies(raw):
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


def _load_netscape_cookies(text: str):
    cookies = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        domain, include_subdomains, path, secure, expires, name, value = parts
        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path or "/",
            "httpOnly": False,
            "secure": str(secure).upper() == "TRUE",
            "sameSite": "None" if str(secure).upper() == "TRUE" else "Lax",
        }
        try:
            expiry = int(expires)
            if expiry > 0:
                cookie["expires"] = expiry
        except ValueError:
            pass
        cookies.append(cookie)
    return cookies


def maybe_json(value):
    try:
        return json.loads(value)
    except Exception:
        return None


def shorten_text(value, limit=1200):
    text = str(value or "")
    return text if len(text) <= limit else f"{text[:limit]}...[truncated {len(text) - limit} chars]"


def extract_html_signals(html: str):
    signals = {}

    title_match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        signals["title"] = re.sub(r"\s+", " ", title_match.group(1)).strip()

    for key in ("room_id", "user_count", "streamId", "session_id"):
        match = re.search(rf'"{re.escape(key)}"\s*:\s*("?[^",}}]+"?)', html)
        if match:
            raw = match.group(1).strip('"')
            if raw.isdigit():
                signals[key] = int(raw)
            else:
                signals[key] = raw

    api_domains_match = re.search(
        r'<script id="api-domains" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if api_domains_match:
        domains = maybe_json(api_domains_match.group(1))
        if isinstance(domains, dict):
            signals["api_domains"] = {
                key: domains.get(key)
                for key in ("webcastApi", "webcastRootApi", "imFrontier", "rootApi", "kind")
                if domains.get(key)
            }

    owner_match = re.search(r'"owner"\s*:\s*\{.*?"nickname"\s*:\s*"([^"]+)"', html)
    if owner_match:
        signals["owner_nickname"] = owner_match.group(1)

    return signals


class JsonlLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")

    def write(self, event: dict):
        self._fh.write(json.dumps(event, ensure_ascii=True) + "\n")
        self._fh.flush()

    def close(self):
        self._fh.close()


def event_matches(url: str, filters):
    text = (url or "").lower()
    return any(token in text for token in filters)


def build_parser():
    parser = argparse.ArgumentParser(description="Probe TikTok LIVE network and websocket traffic.")
    parser.add_argument("url", nargs="?", help="TikTok LIVE URL")
    parser.add_argument("--seconds", type=int, default=45, help="How long to observe after navigation")
    parser.add_argument("--headed", action="store_true", help="Run browser with UI")
    parser.add_argument("--profile-dir", default=os.getenv("TIKTOK_PROFILE_DIR", ""), help="Persistent Playwright profile directory")
    parser.add_argument("--cookies", default=os.getenv("TIKTOK_COOKIES_PATH", ""), help="Cookie export JSON path")
    parser.add_argument("--output-dir", default="tmp", help="Directory for probe output files")
    parser.add_argument("--filter", action="append", dest="filters", help="URL substring to capture; repeatable")
    parser.add_argument("--dump-body", action="store_true", help="Attempt to log text response bodies for matching responses")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Browser user agent")
    return parser


def main():
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    url = args.url or os.getenv("TIKTOK_LIVE_URL", "").strip()
    if not url:
        raise SystemExit("Pass a TikTok LIVE URL or set TIKTOK_LIVE_URL.")

    filters = tuple((args.filters or []) or DEFAULT_FILTERS)
    started_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir)
    slug = safe_name(url.split("/@")[-1].split("?")[0].replace("/", "_"))
    jsonl_path = out_dir / f"tiktok_probe_{slug}_{stamp}.jsonl"
    summary_path = out_dir / f"tiktok_probe_{slug}_{stamp}_summary.json"
    logger = JsonlLogger(jsonl_path)

    counts = {
        "request": 0,
        "response": 0,
        "websocket": 0,
        "ws_frame_received": 0,
        "ws_frame_sent": 0,
        "console": 0,
        "page_error": 0,
    }
    summary = {
        "started_at": started_at,
        "url": url,
        "filters": list(filters),
        "jsonl_path": str(jsonl_path),
        "html_signals": {},
        "matching_urls": [],
        "matching_ws_urls": [],
    }
    matching_urls = set()
    matching_ws_urls = set()

    logger.write({"type": "session_start", "ts": started_at, "url": url, "filters": filters})

    with sync_playwright() as p:
        browser_launch_kwargs = {
            "headless": not args.headed,
        }
        context_kwargs = {
            "user_agent": args.user_agent,
            "viewport": {"width": 1440, "height": 1200},
        }

        if args.profile_dir:
            context = p.chromium.launch_persistent_context(
                user_data_dir=args.profile_dir,
                channel="chrome",
                **browser_launch_kwargs,
                **context_kwargs,
            )
        else:
            browser = p.chromium.launch(channel="chrome", **browser_launch_kwargs)
            context = browser.new_context(**context_kwargs)

        try:
            if args.cookies and Path(args.cookies).exists():
                context.add_cookies(load_cookies(args.cookies))

            page = context.new_page()

            def log_event(event):
                logger.write(event)

            def on_console(msg):
                counts["console"] += 1
                log_event(
                    {
                        "type": "console",
                        "ts": utc_now(),
                        "level": msg.type,
                        "text": shorten_text(msg.text),
                    }
                )

            def on_page_error(exc):
                counts["page_error"] += 1
                log_event(
                    {
                        "type": "page_error",
                        "ts": utc_now(),
                        "message": shorten_text(exc),
                    }
                )

            def on_request(request):
                if not event_matches(request.url, filters):
                    return
                counts["request"] += 1
                matching_urls.add(request.url)
                post_data = request.post_data or ""
                log_event(
                    {
                        "type": "request",
                        "ts": utc_now(),
                        "method": request.method,
                        "resource_type": request.resource_type,
                        "url": request.url,
                        "headers": dict(request.headers),
                        "post_data": shorten_text(post_data, limit=2000) if post_data else "",
                    }
                )

            def on_response(response):
                if not event_matches(response.url, filters):
                    return
                counts["response"] += 1
                matching_urls.add(response.url)
                event = {
                    "type": "response",
                    "ts": utc_now(),
                    "url": response.url,
                    "status": response.status,
                    "ok": response.ok,
                    "content_type": response.headers.get("content-type", ""),
                    "headers": dict(response.headers),
                }
                if args.dump_body:
                    try:
                        body = response.text()
                        event["body_preview"] = shorten_text(body, limit=4000)
                    except Exception as exc:
                        event["body_preview_error"] = str(exc)
                log_event(event)

            def on_websocket(ws):
                counts["websocket"] += 1
                matching_ws_urls.add(ws.url)
                log_event({"type": "websocket", "ts": utc_now(), "url": ws.url})

                def on_frame_sent(payload):
                    counts["ws_frame_sent"] += 1
                    log_event(
                        {
                            "type": "ws_frame_sent",
                            "ts": utc_now(),
                            "url": ws.url,
                            "payload": shorten_text(payload, limit=4000),
                        }
                    )

                def on_frame_received(payload):
                    counts["ws_frame_received"] += 1
                    log_event(
                        {
                            "type": "ws_frame_received",
                            "ts": utc_now(),
                            "url": ws.url,
                            "payload": shorten_text(payload, limit=4000),
                        }
                    )

                def on_ws_close():
                    log_event({"type": "websocket_close", "ts": utc_now(), "url": ws.url})

                ws.on("framesent", on_frame_sent)
                ws.on("framereceived", on_frame_received)
                ws.on("close", on_ws_close)

            page.on("console", on_console)
            page.on("pageerror", on_page_error)
            page.on("request", on_request)
            page.on("response", on_response)
            page.on("websocket", on_websocket)

            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(4000)

            html = page.content()
            html_signals = extract_html_signals(html)
            summary["html_signals"] = html_signals
            log_event({"type": "html_signals", "ts": utc_now(), "signals": html_signals})

            end_at = time.time() + max(5, args.seconds)
            while time.time() < end_at:
                page.wait_for_timeout(1000)

            summary["matching_urls"] = sorted(matching_urls)
            summary["matching_ws_urls"] = sorted(matching_ws_urls)
            summary["counts"] = counts
            summary["finished_at"] = utc_now()
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(summary, indent=2))
        except PlaywrightError as exc:
            summary["finished_at"] = utc_now()
            summary["error"] = str(exc)
            summary["counts"] = counts
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(summary, indent=2))
            return 1
        finally:
            logger.close()
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
