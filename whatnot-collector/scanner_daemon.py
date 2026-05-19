import json
import os
import sys
import time
from urllib.request import Request, urlopen

try:
    from evdev import InputDevice, ecodes, list_devices
except Exception as exc:
    print("evdev not available:", exc)
    sys.exit(1)


API_URL = os.getenv("SCAN_API_URL", "http://localhost:8088/api/scan")
DEVICE_PATH = os.getenv("SCANNER_DEVICE", "")
MIN_LENGTH = int(os.getenv("SCAN_MIN_LEN", "4"))
IDLE_FLUSH_MS = int(os.getenv("SCAN_IDLE_FLUSH_MS", "300"))


def post_scan(code: str) -> None:
    payload = json.dumps({"barcode": code}).encode("utf-8")
    req = Request(API_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=3) as resp:
            resp.read()
    except Exception as exc:
        print("post failed:", exc)


def pick_device() -> str:
    if DEVICE_PATH and os.path.exists(DEVICE_PATH):
        return DEVICE_PATH
    candidates = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            if "keyboard" in (dev.name or "").lower() or "scanner" in (dev.name or "").lower():
                candidates.append(path)
            dev.close()
        except Exception:
            continue
    if not candidates:
        # try by-id paths
        by_id = "/dev/input/by-id"
        if os.path.isdir(by_id):
            for name in os.listdir(by_id):
                if name.endswith("-event-kbd"):
                    candidates.append(os.path.join(by_id, name))
    return candidates[0] if candidates else ""


def main() -> int:
    device_path = pick_device()
    if not device_path:
        print("No input device found. Set SCANNER_DEVICE to /dev/input/eventX")
        return 2

    dev = InputDevice(device_path)
    try:
        dev.grab()
        grabbed = True
    except Exception as exc:
        grabbed = False
        print("warning: could not grab device (keystrokes will still go to focused app):", exc)
    print(f"Listening on {device_path} ({dev.name}) -> {API_URL} (grabbed={grabbed})")

    buffer = []
    last_ts = 0.0

    try:
        for event in dev.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            if event.value != 1:
                continue

            key = ecodes.KEY[event.code]
            now = time.time()
            if last_ts and (now - last_ts) * 1000 > IDLE_FLUSH_MS:
                buffer = []
            last_ts = now

            if key == "KEY_ENTER":
                code = "".join(buffer).strip()
                buffer = []
                if len(code) >= MIN_LENGTH:
                    post_scan(code)
                continue

            if key.startswith("KEY_"):
                char = key.replace("KEY_", "")
                if len(char) == 1:
                    buffer.append(char)
                elif char in ["MINUS", "SLASH", "DOT"]:
                    buffer.append({"MINUS": "-", "SLASH": "/", "DOT": "."}[char])

    finally:
        try:
            if grabbed:
                dev.ungrab()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
