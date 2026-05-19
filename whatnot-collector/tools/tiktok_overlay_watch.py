#!/usr/bin/env python3
"""
Lightweight TikTok LIVE overlay watcher (no root).

Strategy:
- Take periodic screenshots via `adb exec-out screencap -p`
- Crop only the lower overlay area(s) where lot/winner/price appears
- OCR the crops with RapidOCR first and Tesseract as fallback
- Emit JSON only when parsed values change

Prereqs (Ubuntu):
  sudo apt update
  sudo apt install -y tesseract-ocr
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image, ImageEnhance, ImageOps

try:
  import numpy as np
except Exception:
  np = None

try:
  from rapidocr_onnxruntime import RapidOCR
except Exception:
  RapidOCR = None


SCRIPT_VERSION = "2026-04-08.3"
_RAPID_OCR_ENGINE = None

def _default_db_path() -> str:
  return ""


def _db_connect(db_path: str):
  _ = db_path
  here = os.path.dirname(os.path.abspath(__file__))
  root = os.path.normpath(os.path.join(here, ".."))
  if root not in sys.path:
    sys.path.insert(0, root)
  from server.postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, postgres_available
  if not postgres_available():
    raise RuntimeError("postgres_required: tiktok_overlay_watch --write-db no longer writes SQLite")
  ensure_wave1_postgres_schema()
  return _pg_connect()


def _utc_now_iso() -> str:
  from datetime import datetime, timezone
  return datetime.now(timezone.utc).isoformat()


def _db_create_stream(conn, stream_url: str, streamer_name: str | None) -> int:
  here = os.path.dirname(os.path.abspath(__file__))
  root = os.path.normpath(os.path.join(here, ".."))
  if root not in sys.path:
    sys.path.insert(0, root)
  from server.ingest_cutover import ensure_ingest_stream
  stream_id = ensure_ingest_stream(
    stream_url,
    streamer_name=(streamer_name or "").strip() or None,
    title="TikTok LIVE (OCR)",
    started_at=_utc_now_iso(),
  )
  if not stream_id:
    raise RuntimeError("failed to create ingest stream")
  return int(stream_id)


def _db_find_recent_stream(conn, stream_url: str) -> Optional[int]:
  here = os.path.dirname(os.path.abspath(__file__))
  root = os.path.normpath(os.path.join(here, ".."))
  if root not in sys.path:
    sys.path.insert(0, root)
  from server.config import POSTGRES_SIDECAR_SCHEMA
  cur = conn.cursor()
  cur.execute(
    f"SELECT id, started_at FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE stream_url = %s ORDER BY id DESC LIMIT 1",
    (stream_url,),
  )
  row = cur.fetchone()
  if not row:
    return None
  stream_id, started_at = row[0], row[1]
  try:
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    if age < 6 * 3600:
      return int(stream_id)
  except Exception:
    return int(stream_id)
  return None


def _db_insert_event(conn, stream_id: int, event_type: str, payload: dict) -> None:
  here = os.path.dirname(os.path.abspath(__file__))
  root = os.path.normpath(os.path.join(here, ".."))
  if root not in sys.path:
    sys.path.insert(0, root)
  from server.ingest_cutover import insert_event as cutover_insert_event
  cutover_insert_event(
    int(stream_id),
    event_type,
    json.dumps(payload, ensure_ascii=True),
    created_at=_utc_now_iso(),
  )


def _db_latest_won_lot_int(conn, stream_id: int) -> Optional[int]:
  """
  When restarting the watcher mid-stream, seed the lot lock from the last known
  'won' event so we don't accept a random small lot number due to OCR glitches.
  """
  try:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(here, ".."))
    if root not in sys.path:
      sys.path.insert(0, root)
    from server.config import POSTGRES_SIDECAR_SCHEMA
    cur = conn.cursor()
    cur.execute(
      f"""
      SELECT payload
      FROM {POSTGRES_SIDECAR_SCHEMA}.events
      WHERE stream_id = %s
        AND event_type = 'tiktok_auction_won'
      ORDER BY id DESC
      LIMIT 1
      """,
      (int(stream_id),),
    )
    row = cur.fetchone()
    if not row:
      return None
    try:
      p = json.loads(row[0] or "{}")
    except Exception:
      p = {}
    lot = str(p.get("lot_number") or "").strip()
    if not lot:
      return None
    v = int(lot)
    return v if v > 0 else None
  except Exception:
    return None


def _db_latest_won_lot_for_stream_url(conn, stream_url: str) -> Optional[int]:
  """
  Seed a fresh TikTok stream from the seller's most recent observed lot, even if
  this run was started with --new-stream. This helps when OCR drops a leading
  digit and the parser needs sequence context (e.g. 294 -> 24).
  """
  try:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(here, ".."))
    if root not in sys.path:
      sys.path.insert(0, root)
    from server.config import POSTGRES_SIDECAR_SCHEMA
    cur = conn.cursor()
    cur.execute(
      f"""
      SELECT e.payload
      FROM {POSTGRES_SIDECAR_SCHEMA}.events e
      JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = e.stream_id
      WHERE s.stream_url = %s
        AND e.event_type = 'tiktok_auction_won'
      ORDER BY e.id DESC
      LIMIT 1
      """,
      (stream_url,),
    )
    row = cur.fetchone()
    if not row:
      return None
    try:
      p = json.loads(row[0] or "{}")
    except Exception:
      p = {}
    lot = str(p.get("lot_number") or "").strip()
    if not lot:
      return None
    v = int(lot)
    return v if v > 0 else None
  except Exception:
    return None


def _normalize_streamer_handle(value: str | None) -> str:
  s = (value or "").strip()
  if s.startswith("@"):
    s = s[1:]
  return re.sub(r"[^A-Za-z0-9_.]+", "", s)


def _run(cmd: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess:
  return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def ensure_adb_device() -> None:
  p = _run(["adb", "devices"])
  out = p.stdout.decode("utf-8", "ignore")
  if "device" not in out.splitlines()[-1:][0] and "\tdevice" not in out:
    print("No ADB device detected. Run: adb devices -l", file=sys.stderr)
    sys.exit(2)


def ensure_tesseract() -> None:
  if shutil.which("tesseract"):
    return
  print(
    "Missing `tesseract` binary.\n"
    "Install:\n"
    "  sudo apt update\n"
    "  sudo apt install -y tesseract-ocr\n",
    file=sys.stderr,
  )
  sys.exit(2)


def ensure_ocr_backend() -> None:
  if RapidOCR is not None and np is not None:
    return
  ensure_tesseract()


def screencap_png() -> bytes:
  # `adb exec-out` streams binary PNG without writing to the device.
  p = _run(["adb", "exec-out", "screencap", "-p"], timeout=40)
  if p.returncode != 0 or not p.stdout:
    err = p.stderr.decode("utf-8", "ignore").strip()
    raise RuntimeError(f"screencap failed: {err or 'unknown error'}")
  return p.stdout


def dump_ui_xml() -> str:
  remote_path = "/sdcard/ui.xml"
  p = _run(["adb", "shell", "uiautomator", "dump", "--compressed", remote_path], timeout=25)
  if p.returncode != 0:
    err = p.stderr.decode("utf-8", "ignore").strip() or p.stdout.decode("utf-8", "ignore").strip()
    raise RuntimeError(f"uiautomator dump failed: {err or 'unknown error'}")
  pull = _run(["adb", "exec-out", "cat", remote_path], timeout=25)
  if pull.returncode != 0 or not pull.stdout:
    err = pull.stderr.decode("utf-8", "ignore").strip()
    raise RuntimeError(f"uiautomator cat failed: {err or 'unknown error'}")
  return pull.stdout.decode("utf-8", "ignore")


def img_hash(img: Image.Image) -> str:
  # Hash raw RGB bytes for cheap change detection.
  b = img.convert("RGB").tobytes()
  return hashlib.sha1(b).hexdigest()


def preprocess(img: Image.Image) -> Image.Image:
  # OCR-friendly: grayscale, auto-contrast, 2x scale, slight sharpening.
  g = ImageOps.grayscale(img)
  g = ImageOps.autocontrast(g)
  g = g.resize((g.size[0] * 2, g.size[1] * 2), Image.Resampling.BICUBIC)
  g = ImageEnhance.Sharpness(g).enhance(1.4)
  return g


def preprocess_digits(img: Image.Image) -> Image.Image:
  """
  Stronger preprocessing for small numeric regions (lot number).
  """
  g = ImageOps.grayscale(img)
  g = ImageOps.autocontrast(g)
  g = g.resize((g.size[0] * 3, g.size[1] * 3), Image.Resampling.BICUBIC)
  g = ImageEnhance.Sharpness(g).enhance(1.8)
  g = ImageEnhance.Contrast(g).enhance(1.6)
  # simple binarization; helps separate '#253' from background
  g = g.point(lambda p: 255 if p > 165 else 0)
  return g


def preprocess_toast(img: Image.Image) -> Image.Image:
  """
  Stronger preprocessing for the white winner toast card.
  """
  g = ImageOps.grayscale(img)
  g = ImageOps.autocontrast(g)
  g = g.resize((g.size[0] * 3, g.size[1] * 3), Image.Resampling.BICUBIC)
  g = ImageEnhance.Sharpness(g).enhance(1.9)
  g = ImageEnhance.Contrast(g).enhance(1.8)
  return g


def preprocess_binary(img: Image.Image, *, scale: int = 3, threshold: int = 160, contrast: float = 1.8, sharpen: float = 1.8) -> Image.Image:
  g = ImageOps.grayscale(img)
  g = ImageOps.autocontrast(g)
  g = g.resize((g.size[0] * scale, g.size[1] * scale), Image.Resampling.BICUBIC)
  g = ImageEnhance.Sharpness(g).enhance(sharpen)
  g = ImageEnhance.Contrast(g).enhance(contrast)
  return g.point(lambda p: 255 if p > threshold else 0)


def preprocess_inverted_binary(img: Image.Image, *, scale: int = 3, threshold: int = 160, contrast: float = 1.8, sharpen: float = 1.8) -> Image.Image:
  return ImageOps.invert(preprocess_binary(img, scale=scale, threshold=threshold, contrast=contrast, sharpen=sharpen))


def ocr_tesseract(img: Image.Image, *, psm: int = 6, whitelist: str | None = None) -> str:
  # Use a temp file to keep dependencies minimal.
  import tempfile

  with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    path = f.name
    img.save(f, format="PNG")

  try:
    cmd = ["tesseract", path, "stdout", "--psm", str(psm), "-l", "eng"]
    if whitelist:
      cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    p = _run(cmd, timeout=25)
    txt = (p.stdout or b"").decode("utf-8", "ignore")
    return txt
  finally:
    try:
      os.unlink(path)
    except OSError:
      pass


def _get_rapidocr():
  global _RAPID_OCR_ENGINE
  if _RAPID_OCR_ENGINE is None and RapidOCR is not None and np is not None:
    _RAPID_OCR_ENGINE = RapidOCR()
  return _RAPID_OCR_ENGINE


def _apply_whitelist(txt: str, whitelist: str | None) -> str:
  if not whitelist:
    return txt
  allowed = set(whitelist) | {" ", "\n", "\t", "\r"}
  return "".join(ch for ch in txt if ch in allowed)


def ocr_rapid(img: Image.Image, *, whitelist: str | None = None) -> str:
  engine = _get_rapidocr()
  if engine is None or np is None:
    return ""
  arr = np.array(img.convert("RGB"))
  try:
    res, _elapsed = engine(arr)
  except Exception:
    return ""
  parts: list[str] = []
  for row in res or []:
    if len(row) < 2:
      continue
    text = str(row[1]).strip()
    if text:
      parts.append(text)
  return _apply_whitelist("\n".join(parts), whitelist)


def ocr_best(img: Image.Image, *, psm: int = 6, whitelist: str | None = None) -> str:
  rapid_txt = ocr_rapid(img, whitelist=whitelist).strip()
  tess_txt = ""
  if rapid_txt:
    try:
      tess_txt = ocr_tesseract(img, psm=psm, whitelist=whitelist).strip()
    except Exception:
      tess_txt = ""
    if tess_txt and tess_txt.lower() != rapid_txt.lower():
      return rapid_txt + "\n" + tess_txt
    return rapid_txt
  return ocr_tesseract(img, psm=psm, whitelist=whitelist)


def _dedupe_text_parts(parts: list[str]) -> str:
  seen: set[str] = set()
  kept: list[str] = []
  for raw in parts:
    txt = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not txt:
      continue
    key = txt.lower()
    if key in seen:
      continue
    seen.add(key)
    kept.append(txt)
  return "\n".join(kept)


def _ocr_variants(img: Image.Image, *, region: str) -> list[tuple[Image.Image, int, str | None]]:
  if region == "lot":
    return [
      (preprocess_digits(img), 7, "#0123456789"),
      (preprocess_binary(img, scale=4, threshold=145, contrast=2.1, sharpen=2.0), 7, "#0123456789"),
      (preprocess_binary(img, scale=4, threshold=175, contrast=2.2, sharpen=2.0), 7, "#0123456789"),
      (preprocess_inverted_binary(img, scale=4, threshold=165, contrast=2.0, sharpen=2.0), 7, "#0123456789"),
    ]
  if region == "toast":
    return [
      (preprocess_toast(img), 6, None),
      (preprocess_binary(img, scale=3, threshold=170, contrast=1.9, sharpen=1.9), 6, None),
      (preprocess_inverted_binary(img, scale=3, threshold=185, contrast=1.9, sharpen=1.9), 6, None),
    ]
  return [
    (preprocess(img), 6, None),
    (preprocess_binary(img, scale=2, threshold=165, contrast=1.8, sharpen=1.6), 6, None),
    (preprocess_inverted_binary(img, scale=2, threshold=180, contrast=1.8, sharpen=1.6), 6, None),
  ]


def ocr_aggressive(img: Image.Image, *, region: str) -> str:
  parts: list[str] = []
  for variant, psm, whitelist in _ocr_variants(img, region=region):
    try:
      txt = ocr_best(variant, psm=psm, whitelist=whitelist).strip()
    except Exception:
      txt = ""
    if txt:
      parts.append(txt)
  return _dedupe_text_parts(parts)


@dataclass(frozen=True)
class Parsed:
  lot: Optional[str] = None
  winner: Optional[str] = None
  price: Optional[str] = None
  kind: Optional[str] = None  # "winning" | "won"


@dataclass(frozen=True)
class UiDumpSignals:
  lot: Optional[str] = None
  price: Optional[str] = None
  winner: Optional[str] = None
  kind: Optional[str] = None  # "winning" | "won"
  shopping_no: Optional[str] = None
  raw_text: str = ""


# Lot is shown as "#253" in the auction bar; read it from a tight crop for stability.
# OCR may confuse '#' with '§' on small text.
_RE_LOT = re.compile(r"[#§]\s*([0-9]{1,4})")
_RE_PRICE_ANY = re.compile(r"[$S§]\s*([0-9]+(?:\.[0-9]{2})?)")
_RE_WINNING_BID = re.compile(r"Winning\s+bid\s*(?:[$S§]\s*)?([0-9]+(?:[.,][0-9]{2})?)", re.IGNORECASE)
# "is winning" usually shows the handle (no spaces).
# "is winning" can be a handle (sometimes prefixed with @) or a display name.
# Also tolerate OCR typos like "winnina"/"winnin".
_RE_WINNING = re.compile(r"@?\s*([A-Za-z0-9_.][A-Za-z0-9_. ]{0,60}?)\s+is\s+winn\w+\b", re.IGNORECASE)
# "won!" toast often shows a display name with spaces.
_RE_WON = re.compile(r"\b([A-Za-z0-9_.][A-Za-z0-9_. ]{0,60}?)\s+won\b", re.IGNORECASE)
_RE_SHOPPING_NO = re.compile(r"Shopping\s+No\.?\s*(\d+)", re.IGNORECASE)
_RE_LIVE_BID = re.compile(r"Bid\s*[$S§]\s*([0-9]+(?:[.,][0-9]{2})?)", re.IGNORECASE)

# Lot numbers in TikTok auctions are typically sequential. Allow a small forward
# jump for missed frames but reject large leaps (usually OCR glitches).
_MAX_LOT_FORWARD_JUMP = 6


def parse_text(txt: str) -> Parsed:
  # Strip noisy overlays that can be mis-parsed as lot numbers.
  txt = re.sub(r"Shopping\s+No\.?\s*\d+", " ", txt, flags=re.IGNORECASE)

  lot = None
  price = None
  winner = None
  kind = None

  m = _RE_LOT.search(txt)
  if m:
    lot = m.group(1)

  # Prefer explicit "Winning bid $X" if present.
  m = _RE_WINNING_BID.search(txt)
  if m:
    price = m.group(1).replace(",", ".")
  else:
    # Otherwise pick the first $-price that is NOT part of the "Bid $X" button.
    matches = list(_RE_PRICE_ANY.finditer(txt))
    for mm in matches:
      start = mm.start()
      ctx = txt[max(0, start - 10):start].lower()
      if "bid" in ctx:
        continue
      price = mm.group(1).replace(",", ".")
      break

  m = _RE_WON.search(txt)
  if m:
    winner = m.group(1).strip()
    kind = "won"
  else:
    m = _RE_WINNING.search(txt)
    if m:
      winner = m.group(1)
      kind = "winning"

  return Parsed(lot=lot, winner=winner, price=price, kind=kind)


def _clean_winner_name(value: str | None) -> str:
  s = re.sub(r"\s+", " ", str(value or "")).strip()
  s = s.lstrip("@").strip()
  s = re.sub(r"^[^A-Za-z0-9_.]+", "", s)
  s = re.sub(r"[^A-Za-z0-9_. ]+$", "", s)
  return s.strip()


def parse_winner_toast_text(txt: str) -> Parsed:
  """
  Specialized parser for the final TikTok winner toast.
  The toast usually looks like:
    crackrus999 won!
    Winning bid $51.00
  """
  price = None
  winner = None

  m = _RE_WINNING_BID.search(txt)
  if m:
    price = m.group(1).replace(",", ".")

  lines = [re.sub(r"\s+", " ", part).strip() for part in txt.splitlines() if part.strip()]
  for line in lines:
    m = _RE_WON.search(line)
    if m:
      winner = _clean_winner_name(m.group(1))
      break

  if not winner:
    m = _RE_WON.search(txt)
    if m:
      winner = _clean_winner_name(m.group(1))

  kind = "won" if winner else None
  return Parsed(lot=None, winner=winner or None, price=price, kind=kind)


def _ui_text_lines(xml_text: str) -> list[str]:
  lines: list[str] = []
  try:
    root = ET.fromstring(xml_text)
  except Exception:
    return lines
  for node in root.iter("node"):
    for key in ("text", "content-desc"):
      value = (node.attrib.get(key) or "").strip()
      if not value:
        continue
      value = re.sub(r"\s+", " ", value).strip()
      if value:
        lines.append(value)
  return lines


def parse_ui_dump(xml_text: str) -> UiDumpSignals:
  lines = _ui_text_lines(xml_text)
  if not lines:
    return UiDumpSignals()

  shopping_no = None
  for line in lines:
    m = _RE_SHOPPING_NO.search(line)
    if m:
      shopping_no = m.group(1)
      break

  text_blob = "\n".join(lines)
  parsed = parse_text(text_blob)
  price = None
  # Trust UI-dump price only for explicit winner toasts.
  # Generic live-screen text often includes promo copy like "$1 starts..."
  # or the next-bid button price, which are not the sold price.
  if parsed.kind == "won":
    m = _RE_WINNING_BID.search(text_blob)
    if m:
      price = m.group(1).replace(",", ".")
    else:
      price = parsed.price

  return UiDumpSignals(
    lot=parsed.lot,
    price=price,
    winner=parsed.winner,
    kind=parsed.kind,
    shopping_no=shopping_no,
    raw_text=text_blob,
  )

def _update_lot_candidate(
  raw_lot: str | None,
  *,
  last_confirmed_lot_int: Optional[int],
  lot_candidate: Optional[str],
  lot_candidate_frames: int,
  stable_frames: int,
) -> tuple[Optional[str], int, Optional[str], Optional[int]]:
  """
  Shared lot-candidate stabilizer. Returns:
    (next_lot_candidate, next_frames, newly_confirmed_lot, confirmed_lot_int)
  """
  if not raw_lot:
    return lot_candidate, lot_candidate_frames, None, None
  # Reject obviously invalid lot ids.
  try:
    raw_int = int(str(raw_lot).strip())
    if raw_int <= 0 or raw_int > 999:
      return lot_candidate, lot_candidate_frames, None, None
  except Exception:
    pass
  best = _best_lot_candidate(raw_lot, last_confirmed_lot_int)
  if not best:
    return lot_candidate, lot_candidate_frames, None, None
  best_lot, best_int = best
  if best_lot == lot_candidate:
    lot_candidate_frames += 1
  else:
    lot_candidate = best_lot
    lot_candidate_frames = 1
  if lot_candidate_frames >= max(1, stable_frames):
    return lot_candidate, lot_candidate_frames, lot_candidate, best_int
  return lot_candidate, lot_candidate_frames, None, None


def _best_lot_candidate(raw_lot: str, last_int: Optional[int]) -> Optional[tuple[str, Optional[int]]]:
  """
  OCR can glue digits from nearby text, e.g. '#292 1$' -> '2921'.
  If we have a last confirmed lot, choose the most plausible candidate close to it.
  """
  if not raw_lot:
    return None
  try:
    raw_int = int(raw_lot)
  except ValueError:
    return None

  # Keep the raw OCR value as the primary candidate.
  # Only derive trimmed variants for obviously glued multi-digit reads.
  cands = [raw_int]
  if raw_int >= 100:
    cands.append(raw_int // 10)
  if raw_int >= 1000:
    cands.append(raw_int % 1000)
  if raw_int >= 100:
    cands.append(raw_int % 100)
  if last_int is not None:
    raw_s = str(raw_int)
    last_s = str(last_int)
    # OCR sometimes drops one digit from the lot card, e.g. "294" -> "24".
    # Generate candidates by inserting a missing digit and choose the closest
    # plausible value near the last confirmed lot.
    if len(raw_s) + 1 == len(last_s) and len(raw_s) >= 1:
      for pos in range(len(raw_s) + 1):
        for digit in "0123456789":
          cand_s = raw_s[:pos] + digit + raw_s[pos:]
          try:
            cand = int(cand_s)
          except ValueError:
            continue
          if 1 <= cand <= 999:
            cands.append(cand)

  seen = set()
  uniq: list[int] = []
  for c in cands:
    if c in seen:
      continue
    uniq.append(c)
    seen.add(c)

  if last_int is None:
    # Starting cold:
    # - trust a normal 1..999 raw lot as-is
    # - only fall back to trimmed variants when the OCR read is too large
    if 1 <= raw_int <= 999:
      return (str(raw_int), raw_int)
    preferred = [c for c in uniq if 1 <= c <= 999]
    if not preferred:
      return None
    best = preferred[0]
    return (str(best), best)

  plausible: list[int] = []
  for c in uniq:
    # User workflow expects lots to be monotonic/incremental.
    # Once we have a confirmed lot, never accept a lower lot id.
    if c < last_int:
      continue
    if c > last_int + 40:
      continue
    plausible.append(c)

  if not plausible:
    return None

  best = min(plausible, key=lambda c: abs(c - last_int))
  return (str(best), best)


def _try_lot_from_badge(lot_crop: Image.Image) -> Optional[str]:
  """
  Fallback OCR on the tight lot-badge crop using a digit-only whitelist.
  Used when _RE_LOT fails because Tesseract garbles '#' into garbage characters.
  """
  try:
    txt = ocr_best(preprocess_digits(lot_crop), psm=7, whitelist="#0123456789")
    m = re.search(r"#?\s*([0-9]{1,3})", txt.strip())
    if m:
      v = int(m.group(1))
      if 1 <= v <= 999:
        return str(v)
  except Exception:
    pass
  return None


def _lot_has_explicit_hash(raw_txt: str) -> bool:
  return bool(re.search(r"[#§]\s*[0-9]{1,4}", raw_txt or ""))


def _is_complete_won_event(event: Optional[Parsed]) -> bool:
  if not event:
    return False
  return bool(event.kind == "won" and event.lot and event.winner and event.price)


def crop_regions(img: Image.Image) -> Tuple[Image.Image, Image.Image, Image.Image]:
  """
  Returns (lot_crop, auction_text_crop, winner_toast_crop).

  Crops are ratio-based for 1080x1920 but should work on nearby sizes too.
  """
  w, h = img.size
  aspect = (float(h) / float(w)) if w else 0.0

  # NOTE: We intentionally do NOT rely on the tiny lot badge OCR for correctness.
  # We still return a lot crop for debugging only (can help tune ratios).
  lot_left = int(w * 0.06)
  lot_right = int(w * 0.34)
  lot_top = int(h * 0.74)
  lot_bot = int(h * 0.83)
  lot_crop = img.crop((lot_left, lot_top, lot_right, lot_bot))

  # Auction text crop (lot + price + "is winning"), excluding the red bid button area.
  # TikTok's auction card sits higher on tall devices (e.g. 1080x2408).
  if aspect >= 2.05:
    # Tight to the card to avoid chat overlays confusing OCR.
    a_left = int(w * 0.00)
    a_right = int(w * 0.86)
    a_top = int(h * 0.74)
    a_bot = int(h * 0.90)
  else:
    a_left = int(w * 0.00)
    a_right = int(w * 0.74)
    # Keep this anchored to the bottom bar (avoid overlapping the winner toast).
    a_top = int(h * 0.79)
    a_bot = int(h * 0.965)
  auction_text = img.crop((a_left, a_top, a_right, a_bot))

  # Winner toast: mid-lower white card "X won! Winning bid $Y".
  # Tighten to the bottom toast area (avoids chat text and product title noise).
  # Tuned for 1080x1920 TikTok LIVE UI where the toast sits near the bottom.
  t_left = int(w * 0.03)
  t_right = int(w * 0.97)
  if aspect >= 2.05:
    # Winner toast sits higher on tall screens; keep this mostly toast-only.
    t_top = int(h * 0.70)
    t_bot = int(h * 0.90)
  else:
    t_top = int(h * 0.72)
    t_bot = int(h * 0.92)
  toast = img.crop((t_left, t_top, t_right, t_bot))

  return lot_crop, auction_text, toast


def main() -> None:
  import argparse

  ap = argparse.ArgumentParser()
  ap.add_argument("--fps", type=float, default=1.0, help="Screenshot rate. Keep low to reduce load.")
  ap.add_argument("--print-raw", action="store_true", help="Also print raw OCR text for debugging.")
  ap.add_argument("--emit-winning", action="store_true", help="Emit 'winning' updates (noisy). Default is won-only.")
  ap.add_argument("--close-on-lot-change", action="store_true", help="If enabled, guess a 'won' when the lot increments (less accurate).")
  ap.add_argument("--lot-stable-frames", type=int, default=2, help="Confirm lot after N identical reads.")
  ap.add_argument("--aggressive", action="store_true", help="Try multiple OCR preprocess variants per region for harder TikTok reads.")
  ap.add_argument("--format", choices=["simple", "json"], default="simple", help="Output format for events.")
  ap.add_argument("--dump-crops", default="", help="Directory to write crop PNGs for debugging (optional).")
  ap.add_argument("--streamer", default="", help="TikTok streamer handle (e.g. giftexpress). Used for DB + UI.")
  ap.add_argument("--stream-url", default="", help="Override stream URL identity (advanced).")
  ap.add_argument("--new-stream", action="store_true", help="Force a new DB stream run (use when TikTok lot counter resets).")
  ap.add_argument("--write-db", action="store_true", help="Write parsed events into the dashboard Postgres DB.")
  ap.add_argument("--db-path", default="", help="Legacy ignored SQLite DB path; --write-db now uses Postgres.")
  args = ap.parse_args()

  ensure_adb_device()
  ensure_ocr_backend()

  print(f"[tiktok_overlay_watch] version={SCRIPT_VERSION}", file=sys.stderr, flush=True)

  interval = max(0.2, 1.0 / max(0.1, args.fps))

  streamer = _normalize_streamer_handle(args.streamer)
  stream_url = (args.stream_url or "").strip() or f"tiktok:{streamer or 'unknown'}"
  db_path = (args.db_path or "").strip() or _default_db_path()
  db_conn = None
  db_stream_id = None
  if args.write_db:
    for attempt in range(1, 9):
      try:
        db_conn = _db_connect(db_path)
        db_stream_id = _db_create_stream(db_conn, stream_url, streamer or None) if args.new_stream else (
          _db_find_recent_stream(db_conn, stream_url) or _db_create_stream(db_conn, stream_url, streamer or None)
        )
        _db_insert_event(db_conn, db_stream_id, "tiktok_session_start", {"stream_url": stream_url, "streamer": streamer, "ver": SCRIPT_VERSION})
        print(f"[tiktok_overlay_watch] db_write=on stream_url={stream_url} stream_id={db_stream_id}", file=sys.stderr, flush=True)
        break
      except Exception as exc:
        msg = str(exc)
        if any(token in msg.lower() for token in ("timeout", "deadlock", "could not serialize")) and attempt < 8:
          time.sleep(0.25 * attempt)
          continue
        print(f"[tiktok_overlay_watch] db_write failed: {exc}", file=sys.stderr, flush=True)
        db_conn = None
        db_stream_id = None
        break

  last_hashes = {"lot": None, "auction_text": None, "toast": None, "ui": None}
  last_emitted: Optional[Parsed] = None
  confirmed_lot: Optional[str] = None
  last_confirmed_lot_int: Optional[int] = None
  last_confirmed_lot_at: float = 0.0
  last_confirmed_lot_explicit: bool = False
  lot_context_price: Optional[str] = None
  lot_context_winner: Optional[str] = None
  lot_candidate: Optional[str] = None
  lot_candidate_frames: int = 0
  emitted_lots: set[str] = set()
  last_db_won_key: Optional[str] = None
  last_db_warn_at: float = 0.0

  # Seed the lot lock if we restarted mid-stream (helps avoid random low lots like "3").
  if db_conn and db_stream_id and (not args.new_stream):
    seeded = _db_latest_won_lot_int(db_conn, db_stream_id)
    if seeded is not None:
      last_confirmed_lot_int = seeded

  while True:
    ui_signals = UiDumpSignals()
    ui_xml = ""
    try:
      ui_xml = dump_ui_xml()
      ui_hash = hashlib.sha1(ui_xml.encode("utf-8", "ignore")).hexdigest()
      if ui_hash != last_hashes["ui"]:
        last_hashes["ui"] = ui_hash
        ui_signals = parse_ui_dump(ui_xml)
        if args.print_raw and ui_signals.raw_text:
          print(json.dumps({"ver": SCRIPT_VERSION, "raw_ui": ui_signals.raw_text[:2000]}, ensure_ascii=True))
      else:
        ui_signals = parse_ui_dump(ui_xml)
    except Exception as e:
      if args.print_raw:
        print(json.dumps({"ver": SCRIPT_VERSION, "ui_error": str(e)}, ensure_ascii=True))

    try:
      png = screencap_png()
      img = Image.open(io.BytesIO(png))
    except Exception as e:
      print(f"[error] {e}", file=sys.stderr)
      time.sleep(1.0)
      continue

    lot_crop, auction_text, toast = crop_regions(img)

    event: Optional[Parsed] = None

    # Step A (LOT screenshot): read the auction bar for #lot + "is winning" + current price.
    a_h = img_hash(auction_text)
    if a_h != last_hashes["auction_text"]:
      last_hashes["auction_text"] = a_h
      if args.dump_crops:
        os.makedirs(args.dump_crops, exist_ok=True)
        auction_text.save(os.path.join(args.dump_crops, "auction.png"))
      txt = ocr_aggressive(auction_text, region="auction") if args.aggressive else ocr_best(preprocess(auction_text), psm=6)
      if args.print_raw:
        print(json.dumps({"ver": SCRIPT_VERSION, "raw_auction": txt.strip()}, ensure_ascii=True))
      p = parse_text(txt)
      raw_lot_is_explicit = _lot_has_explicit_hash(txt)
      if ui_signals.lot or ui_signals.price or ui_signals.winner or ui_signals.kind:
        p = Parsed(
          lot=ui_signals.lot or p.lot,
          winner=ui_signals.winner or p.winner,
          price=ui_signals.price or p.price,
          kind=ui_signals.kind or p.kind,
        )
      # TikTok rule: if the auction card visibly shows "#lot", trust that visible lot
      # and remember it immediately for the next winner toast.
      if p.lot and raw_lot_is_explicit:
        newly_confirmed = str(p.lot).strip()
        newly_confirmed_int = None
        try:
          newly_confirmed_int = int(newly_confirmed)
        except Exception:
          newly_confirmed_int = None
        if newly_confirmed != confirmed_lot:
          confirmed_lot = newly_confirmed
          last_confirmed_lot_int = newly_confirmed_int
          last_confirmed_lot_at = time.time()
          last_confirmed_lot_explicit = True
          lot_candidate = newly_confirmed
          lot_candidate_frames = 1
          lot_context_price = None
          lot_context_winner = None
          print(
            f"[tiktok_overlay_watch] visible_lot={confirmed_lot}",
            file=sys.stderr, flush=True,
          )
      elif p.lot and not raw_lot_is_explicit:
        print(
          f"[tiktok_overlay_watch] skipped_non_explicit_lot lot={p.lot}",
          file=sys.stderr,
          flush=True,
        )

      # Context fields for the current lot.
      if p.kind == "winning" and p.price:
        lot_context_price = p.price
      if p.kind == "winning" and p.winner:
        lot_context_winner = p.winner
      if event is None and confirmed_lot and args.emit_winning and p.kind == "winning" and p.winner and p.price:
        event = Parsed(lot=confirmed_lot, winner=p.winner, price=p.price, kind="winning")

    # Optional debug only: dump lot badge crop (do not use for assignment).
    lot_h = img_hash(lot_crop)
    if lot_h != last_hashes["lot"]:
      last_hashes["lot"] = lot_h
      if args.dump_crops:
        os.makedirs(args.dump_crops, exist_ok=True)
        lot_crop.save(os.path.join(args.dump_crops, "lot.png"))
      if args.print_raw:
        lot_txt = ocr_aggressive(lot_crop, region="lot") if args.aggressive else ocr_best(preprocess_digits(lot_crop), psm=7, whitelist="#0123456789")
        print(json.dumps({"ver": SCRIPT_VERSION, "raw_lot_debug": lot_txt.strip()}, ensure_ascii=True))

    # Step B (WINNER screenshot): read the winner toast for "X won!" + "Winning bid $Y".
    toast_h = img_hash(toast)
    if toast_h != last_hashes["toast"]:
      last_hashes["toast"] = toast_h
      if args.dump_crops:
        os.makedirs(args.dump_crops, exist_ok=True)
        toast.save(os.path.join(args.dump_crops, "toast.png"))
      txt = ocr_aggressive(toast, region="toast") if args.aggressive else ocr_best(preprocess_toast(toast), psm=6)
      if args.print_raw:
        print(json.dumps({"ver": SCRIPT_VERSION, "raw_toast": txt.strip()}, ensure_ascii=True))
      p = parse_winner_toast_text(txt)
      if ui_signals.kind == "won" and (ui_signals.winner or ui_signals.price):
        p = Parsed(
          lot=p.lot,
          winner=ui_signals.winner or p.winner,
          price=ui_signals.price or p.price,
          kind=ui_signals.kind or p.kind,
        )
      # Require BOTH:
      #  - "X won" (winner toast)
      #  - an explicit "Winning bid $Y" price inside the toast itself
      # This prevents random chat lines like "who won" from being treated as a winner.
      has_won = bool(_RE_WON.search(txt))
      has_winning_bid = bool(_RE_WINNING_BID.search(txt))
      if has_won and has_winning_bid and p.kind == "won" and p.winner and p.price:
        # Winner card usually omits lot; attach to the most recently confirmed lot.
        lot_for_toast = None
        if p.lot:
          lot_for_toast = p.lot
        else:
          # Winner card often omits lot; use last confirmed lot if it was seen recently.
          # Allow some delay between the auction card and the winner toast.
          # TikTok can pause briefly on "auction ended" before showing the win card.
          if confirmed_lot and last_confirmed_lot_explicit and (time.time() - last_confirmed_lot_at) <= 20:
            lot_for_toast = confirmed_lot
        if lot_for_toast:
          event = Parsed(lot=lot_for_toast, winner=p.winner, price=p.price, kind="won")
        else:
          print(
            "[tiktok_overlay_watch] winner_toast_seen_without_locked_lot"
            f" winner={p.winner} price={p.price}",
            file=sys.stderr,
            flush=True,
          )

    if event and not _is_complete_won_event(event) and event.kind != "winning":
      event = None

    if event and event != last_emitted:
      last_emitted = event
      if event.kind == "won":
        # Consume the lot: next toast should not reuse it.
        if event.lot:
          emitted_lots.add(event.lot)
        confirmed_lot = None
        lot_candidate = None
        lot_candidate_frames = 0
        last_confirmed_lot_explicit = False
        lot_context_price = None
        lot_context_winner = None
      if args.format == "json":
        print(
          json.dumps(
            {
              "ver": SCRIPT_VERSION,
              "ts": time.time(),
              "lot": event.lot,
              "winner": event.winner,
              "price": event.price,
              "kind": event.kind,
            },
            ensure_ascii=True,
          ),
          flush=True,
        )
      else:
        # Simple: lot<TAB>winner<TAB>price
        lot = event.lot or ""
        winner = (event.winner or "").strip()
        price = event.price or ""
        print(f"{lot}\t{winner}\t{price}", flush=True)

      # Write to Postgres for the dashboard (optional).
      if db_conn and db_stream_id and event.lot:
        try:
          sale_price = None
          if event.price not in (None, ""):
            try:
              sale_price = float(str(event.price).replace("$", "").replace(",", "").strip())
            except Exception:
              sale_price = None
          payload = {
            "lot_number": event.lot,
            "winner_username": (event.winner or "").strip(),
            "sale_price": sale_price,
            "raw_price": event.price,
            "kind": event.kind,
            "streamer": streamer,
            "ver": SCRIPT_VERSION,
          }
          if event.kind == "won":
            won_key = f"{event.lot}|{payload.get('winner_username') or ''}|{payload.get('raw_price') or ''}"
            if won_key != last_db_won_key:
              _db_insert_event(db_conn, db_stream_id, "tiktok_auction_won", payload)
              last_db_won_key = won_key
              print(
                f"[tiktok_overlay_watch] wrote tiktok_auction_won"
                f" lot={event.lot} winner={event.winner} price={event.price}",
                file=sys.stderr, flush=True,
              )
          else:
            _db_insert_event(db_conn, db_stream_id, "tiktok_auction_winning", payload)
        except Exception as exc:
          # Don't crash the watcher; just surface the issue so the operator can restart.
          if (time.time() - last_db_warn_at) >= 5.0:
            print(f"[tiktok_overlay_watch] db_write failed (will retry on next frame): {exc}", file=sys.stderr, flush=True)
            last_db_warn_at = time.time()

    time.sleep(interval)


if __name__ == "__main__":
  main()
