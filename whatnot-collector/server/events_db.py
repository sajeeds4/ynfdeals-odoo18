"""
Event database query functions.
"""

import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher

from .config import (
    EVENTS_DB_READ_BACKEND,
    EVENTS_DB_VALIDATE_READS,
    POSTGRES_SIDECAR_SCHEMA,
)
from .postgres_cutover import (
    _pg_connect,
    ensure_wave1_postgres_schema,
    log_cutover_event,
    postgres_available,
)

_AUDIENCE_CACHE = {}
_AUDIENCE_CACHE_TTL = 60
_TARGET_BUYER_CACHE = {}
_TARGET_BUYER_CACHE_TTL = 90
_TITLE_QUALITY_CACHE = {}
_TITLE_QUALITY_CACHE_TTL = 120


def _events_cache_backend_key(db_path=None):
    if db_path:
        return "postgres"
    return "postgres"


_GENERIC_TITLE_PATTERNS = [
    r"^#?\d{1,4}$",
    r"^lot\s*#?\d+$",
    r"^bookmark listing$",
    r"bookmark listing",
    r"^random perfume",
    r"^fragrance\s*#?\d+$",
    r"^women'?s fragrance",
    r"^men'?s fragrance",
    r"^unisex fragrance",
    r"^designer & arabian fragrances!?$",
    r"^giveaway",
    r"^mystery",
    r"^bundle",
    r"^tray\s*#?\d+$",
    r"^\$?\d+\s+perfumes?",
    r"^\$?\d+\s+designer perfumes?",
    r"fav show",
    r"\bwith\s+(sam|dean|veer|gift ?express)\b",
    r"\bbless (?:a|the)\b",
]
_PERFUME_BRAND_HINTS = {
    "lattafa", "afnan", "armaf", "rasasi", "al rehab", "fragrance world", "maison alhambra",
    "dior", "ysl", "gucci", "versace", "valentino", "burberry", "prada", "armani",
    "azzaro", "mind games", "tom ford", "creed", "maison francis kurkdjian", "mfk",
    "dolce", "gabbana", "jpg", "jean paul", "lancome", "marc jacobs", "byredo",
    "xerjoff", "mancera", "montale", "givenchy", "carolina herrera", "paco rabanne",
}


def _ensure_detection_tables(conn):
    raise RuntimeError("events_db_sqlite_detection_tables_retired")


def _pg_fetchall_dict(cur):
    cols = [desc[0] for desc in (cur.description or [])]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _ensure_pg_id_default(cur, table_name):
    sequence_name = f"{table_name}_id_seq"
    cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.{sequence_name}")
    cur.execute(
        f"""
        ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.{table_name}
        ALTER COLUMN id SET DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.{sequence_name}'::regclass)
        """
    )
    cur.execute(
        f"""
        SELECT setval(
            '{POSTGRES_SIDECAR_SCHEMA}.{sequence_name}'::regclass,
            GREATEST(1, COALESCE((SELECT MAX(id) FROM {POSTGRES_SIDECAR_SCHEMA}.{table_name}), 0) + 1),
            false
        )
        """
    )


def _ensure_detection_tables_pg():
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.stream_ocr_frames (
                    id BIGSERIAL PRIMARY KEY,
                    stream_id BIGINT NOT NULL,
                    captured_at TEXT NOT NULL,
                    image_path TEXT,
                    ocr_text_raw TEXT,
                    ocr_confidence DOUBLE PRECISION DEFAULT 0,
                    source TEXT DEFAULT 'manual'
                )
                """
            )
            _ensure_pg_id_default(cur, "stream_ocr_frames")
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_stream_ocr_frames_stream_id ON {POSTGRES_SIDECAR_SCHEMA}.stream_ocr_frames(stream_id)"
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_stream_ocr_frames_captured_at ON {POSTGRES_SIDECAR_SCHEMA}.stream_ocr_frames(captured_at DESC)"
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.stream_caption_windows (
                    id BIGSERIAL PRIMARY KEY,
                    stream_id BIGINT NOT NULL,
                    captured_at TEXT NOT NULL,
                    caption_text TEXT,
                    confidence DOUBLE PRECISION DEFAULT 0,
                    source TEXT DEFAULT 'manual'
                )
                """
            )
            _ensure_pg_id_default(cur, "stream_caption_windows")
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_stream_caption_windows_stream_id ON {POSTGRES_SIDECAR_SCHEMA}.stream_caption_windows(stream_id)"
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_stream_caption_windows_captured_at ON {POSTGRES_SIDECAR_SCHEMA}.stream_caption_windows(captured_at DESC)"
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.resolved_lot_products (
                    id BIGSERIAL PRIMARY KEY,
                    stream_id BIGINT NOT NULL,
                    lot_number TEXT NOT NULL,
                    winner_event_id BIGINT,
                    resolved_product_name TEXT,
                    resolved_brand TEXT,
                    confidence DOUBLE PRECISION DEFAULT 0,
                    evidence_summary TEXT,
                    resolution_status TEXT DEFAULT 'resolved',
                    resolved_at TEXT NOT NULL
                )
                """
            )
            _ensure_pg_id_default(cur, "resolved_lot_products")
            cur.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_resolved_lot_products_stream_lot ON {POSTGRES_SIDECAR_SCHEMA}.resolved_lot_products(stream_id, lot_number)"
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_resolved_lot_products_stream_id ON {POSTGRES_SIDECAR_SCHEMA}.resolved_lot_products(stream_id)"
            )
        conn.commit()


def _normalize_username(value):
    username = str(value or "").strip().lstrip("@").lower()
    return username if username else ""


def _parse_winner_price(p):
    """Extract sale price from an auction_winner event payload dict."""
    pv = p.get("price_value") or p.get("winning_price") or p.get("sale_price")
    if pv is not None:
        try:
            return float(pv)
        except Exception:
            pass
    raw = str(p.get("price") or p.get("footer_text") or "")
    m = re.findall(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)", raw)
    if m:
        try:
            return float(m[-1].replace(",", ""))
        except Exception:
            pass
    return 0.0


def _extract_event_user_roles(event_type, payload):
    roles = []
    if not isinstance(payload, dict):
        return roles

    if event_type == "chat_message":
        username = _normalize_username(payload.get("username") or payload.get("user"))
        if username:
            roles.append((username, "chat"))
        return roles

    if event_type == "auction_winner":
        username = _normalize_username(
            payload.get("winner") or payload.get("winner_username") or payload.get("username")
        )
        if username:
            roles.append((username, "winner"))
        return roles

    if event_type == "bid_update":
        for key in ("bidder", "bidder_username", "username", "user", "top_bidder", "current_bidder"):
            username = _normalize_username(payload.get(key))
            if username:
                roles.append((username, "bidder"))
                break
        return roles

    for key in ("winner", "winner_username", "bidder", "bidder_username", "username", "user"):
        username = _normalize_username(payload.get(key))
        if username:
            roles.append((username, "other"))
            break
    return roles


def _parse_generic_price(p):
    """Extract the most useful price we can from any auction-related payload."""
    for key in ("price_value", "winning_price", "sale_price", "amount"):
        value = p.get(key)
        if value is not None:
            try:
                return float(value)
            except Exception:
                pass
    raw = str(p.get("price") or p.get("raw_amount") or p.get("footer_text") or "")
    matches = re.findall(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)", raw)
    if matches:
        try:
            return float(matches[-1].replace(",", ""))
        except Exception:
            pass
    return 0.0


def _reconstruct_sold_lots(event_rows):
    """Rebuild sold-lot history from the full spectator event timeline.

    This is more reliable than using auction_winner rows alone because some
    streams expose the final winner/price only briefly or omit lot_number on the
    winner payload. We stitch together lot_update, bid_update, auction_state,
    and auction_winner events into a best-effort sold-lot record.
    """
    sold = []
    active = None
    _ctx = {"last_lot_product": "", "last_lot_at": None}  # mutable container so the loop body can update it

    def _parse_local_iso(ts):
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            return None

    def new_lot(payload, created_at):
        lot_number = payload.get("lot_number")
        return {
            "lot": str(lot_number).strip() if lot_number not in (None, "") else "",
            "product": (payload.get("product_name") or payload.get("title") or payload.get("item_name") or "").strip(),
            "winner": "",
            "price": 0.0,
            "time": created_at,
            "opened_at": created_at,
            "closed": False,
            "source": set(),
        }

    def close_active(created_at, reason=None):
        nonlocal active
        if not active or active.get("closed"):
            active = None
            return
        has_signal = bool(active.get("winner") or active.get("price") or active.get("product") or active.get("lot"))
        if has_signal:
            row = {
                "username": active.get("winner") or "",
                "price": round(float(active.get("price") or 0), 2),
                "product": active.get("product") or "",
                "lot": active.get("lot") or "",
                "time": created_at or active.get("time") or active.get("opened_at"),
                "source": ",".join(sorted(active.get("source") or [])),
                "reason": reason or "",
            }
            sold.append(row)
        active = None

    for event_type, raw_payload, created_at in event_rows:
        try:
            p = json.loads(raw_payload or "{}")
        except Exception:
            p = {}

        if event_type == "lot_update":
            next_lot = str(p.get("lot_number") or "").strip()
            next_product = (p.get("product_name") or p.get("title") or p.get("item_name") or "").strip()
            if next_product:
                _ctx["last_lot_product"] = next_product
                _ctx["last_lot_at"] = created_at
            # A new lot_update usually means the previous lot has already ended.
            if active and (
                (next_lot and next_lot != active.get("lot")) or
                (next_product and active.get("product") and next_product != active.get("product"))
            ):
                close_active(created_at, reason="next_lot_started")
            if not active:
                active = new_lot(p, created_at)
            else:
                if next_lot:
                    active["lot"] = next_lot
                if next_product:
                    active["product"] = next_product
                active["time"] = created_at
            active["source"].add("lot_update")

        elif event_type == "bid_update":
            if not active:
                active = new_lot(p, created_at)
            price = _parse_generic_price(p)
            if price:
                active["price"] = price
            lot_number = str(p.get("lot_number") or "").strip()
            product = (p.get("product_name") or "").strip()
            if lot_number:
                active["lot"] = lot_number
            if product:
                active["product"] = product
            active["time"] = created_at
            active["source"].add("bid_update")

        elif event_type == "auction_winner":
            if not active:
                active = new_lot(p, created_at)
            winner = (p.get("winner") or p.get("winner_username") or p.get("username") or "").strip()
            price = _parse_winner_price(p)
            lot_number = str(p.get("lot_number") or p.get("lot") or "").strip()
            product = (p.get("product_name") or p.get("title") or p.get("item_name") or "").strip()
            if winner:
                active["winner"] = winner
            if price:
                active["price"] = price
            if lot_number:
                active["lot"] = lot_number
            # Use product from winner payload; fall back to whatever active already has
            # (populated from the preceding lot_update / bid_update events).
            if product:
                active["product"] = product
            # Only carry the last lot product forward when the winner landed
            # immediately after a lot_update; otherwise we risk stale product bleed.
            if not active.get("product") and _ctx["last_lot_product"] and _ctx.get("last_lot_at"):
                winner_dt = _parse_local_iso(created_at)
                lot_dt = _parse_local_iso(_ctx.get("last_lot_at"))
                if winner_dt and lot_dt and abs((winner_dt - lot_dt).total_seconds()) <= 20:
                    active["product"] = _ctx["last_lot_product"]
            active["time"] = created_at
            active["source"].add("auction_winner")

        elif event_type == "auction_state":
            state = (p.get("state") or "").strip().lower()
            if not active:
                continue
            active["source"].add(f"auction_state:{state}" if state else "auction_state")
            # If the UI rolled forward to the next item after we saw pricing/winner
            # signals, treat the current lot as closed even if the explicit winner row
            # was missed.
            if state in {"awaiting_next_item", "shipping_shown"} and (active.get("winner") or active.get("price")):
                close_active(created_at, reason=state)

    close_active(None, reason="end_of_stream_window")

    def _parse_iso(ts):
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            return None

    # Pass 1: dedupe exact lot/fallback duplicates.
    coarse = []
    seen = set()
    for row in sold:
        lot = str(row.get("lot") or "").strip()
        if lot:
            key = ("lot", lot)
        else:
            key = (
                "fallback",
                round(float(row.get("price") or 0), 2),
                (row.get("product") or "").strip().lower(),
                str(row.get("time") or "").strip(),
            )
        if key in seen:
            continue
        seen.add(key)
        coarse.append(row)

    # Pass 2: merge near-duplicate no-lot records for the same product/price window.
    merged = []
    for row in coarse:
        row_dt = _parse_iso(row.get("time"))
        product_key = (row.get("product") or "").strip().lower()
        lot_key = str(row.get("lot") or "").strip()
        username_key = (row.get("username") or "").strip().lower()
        row_price = round(float(row.get("price") or 0), 2)
        matched = None
        for existing in reversed(merged):
            if lot_key and str(existing.get("lot") or "").strip() == lot_key:
                matched = existing
                break
            existing_dt = _parse_iso(existing.get("time"))
            existing_product = (existing.get("product") or "").strip().lower()
            existing_username = (existing.get("username") or "").strip().lower()
            existing_price = round(float(existing.get("price") or 0), 2)
            if row_dt and existing_dt:
                delta = abs((row_dt - existing_dt).total_seconds())
                # Late stripped-down winner UI events often repeat the same winner/price
                # but omit lot/product. Fold them into the richer earlier record.
                if (
                    delta <= 120
                    and username_key
                    and username_key == existing_username
                    and row_price > 0
                    and row_price == existing_price
                    and (not lot_key or not row.get("product"))
                    and (existing.get("lot") or existing.get("product"))
                ):
                    matched = existing
                    break
            if not product_key or product_key != existing_product:
                continue
            if not row_dt or not existing_dt:
                continue
            same_price = round(float(existing.get("price") or 0), 2) == round(float(row.get("price") or 0), 2)
            # Same product within 45s is usually the same sold lot being observed
            # first from bid/shipping state and then again from the explicit winner UI.
            if delta <= 45 and (same_price or not existing.get("username") or not row.get("username")):
                matched = existing
                break
            # Some streams emit a richer winner row minutes after the shipping-state
            # closure. If the product matches and the price matches, prefer merging
            # into the richer record instead of counting both as separate sales.
            if (
                delta <= 600
                and same_price
                and product_key
                and product_key == existing_product
                and ((row.get("username") and not existing.get("username")) or (existing.get("username") and not row.get("username")))
            ):
                matched = existing
                break
        if not matched:
            merged.append(dict(row))
            continue

        # Prefer richer data when merging.
        if row.get("username") and not matched.get("username"):
            matched["username"] = row["username"]
        if row.get("lot") and not matched.get("lot"):
            matched["lot"] = row["lot"]
        if row.get("product") and not matched.get("product"):
            matched["product"] = row["product"]
        if row.get("price") and ((not matched.get("price")) or row.get("price", 0) > matched.get("price", 0)):
            matched["price"] = row["price"]
        if row.get("time") and row.get("username"):
            matched["time"] = row["time"]
        matched["source"] = ",".join(sorted(set(
            str(matched.get("source") or "").split(",") + str(row.get("source") or "").split(",")
        ) - {""}))
        if row.get("reason") and not matched.get("reason"):
            matched["reason"] = row["reason"]

    return merged


_OUR_STREAMER_NAMES = {"ynfdeals"}  # Always treat these as ours, regardless of collector state


def _use_postgres_read_path(db_path=None) -> bool:
    return not db_path and EVENTS_DB_READ_BACKEND == "postgres"


def _require_postgres_runtime(db_path=None):
    if db_path:
        raise RuntimeError("events_db_sqlite_runtime_retired")
    if EVENTS_DB_READ_BACKEND != "postgres":
        raise RuntimeError("events_db_postgres_runtime_required")
    if not postgres_available():
        raise RuntimeError("events_db_postgres_unavailable")


def _manual_events_compat_call(operation: str, *args, db_path=None, **kwargs):
    raise RuntimeError("events_db_sqlite_runtime_retired")


def _pg_get_stream_id(stream_url):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE stream_url = %s ORDER BY id DESC LIMIT 1",
                (stream_url,),
            )
            row = cur.fetchone()
            return row[0] if row else None


def _pg_get_all_streams():
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, stream_url, streamer_name, title, started_at, ended_at FROM {POSTGRES_SIDECAR_SCHEMA}.streams ORDER BY id DESC"
            )
            return [
                {
                    "id": row[0],
                    "stream_url": row[1],
                    "streamer_name": row[2],
                    "title": row[3],
                    "started_at": row[4],
                    "ended_at": row[5],
                }
                for row in cur.fetchall()
            ]


def _pg_get_latest_id():
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {POSTGRES_SIDECAR_SCHEMA}.events")
            row = cur.fetchone()
            return row[0] or 0


def _pg_get_latest_id_for_stream(stream_id):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COALESCE(MAX(id), 0) FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = %s",
                (int(stream_id),),
            )
            row = cur.fetchone()
            return row[0] or 0


def _pg_get_events_since(since_id, stream_id=None, limit=500):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if stream_id:
                cur.execute(
                    f"""
                    SELECT id, created_at, event_type, payload
                    FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE id > %s AND stream_id = %s
                    ORDER BY id ASC
                    LIMIT %s
                    """,
                    (since_id, stream_id, limit),
                )
            else:
                cur.execute(
                    f"""
                    SELECT id, created_at, event_type, payload
                    FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE id > %s
                    ORDER BY id ASC
                    LIMIT %s
                    """,
                    (since_id, limit),
                )
            return [
                {"id": row[0], "created_at": row[1], "event_type": row[2], "payload": row[3]}
                for row in cur.fetchall()
            ]


def _pg_get_latest_lot_update_product_name(stream_id):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT payload
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE stream_id = %s AND event_type = 'lot_update'
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(stream_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            payload = json.loads((row[0] or "{}")) if isinstance(row[0], str) else {}
            return payload.get("product_name") or None


def _pg_get_event_by_id(event_id):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, stream_id, created_at, event_type, payload
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE id = %s
                LIMIT 1
                """,
                (int(event_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "stream_id": row[1],
                "created_at": row[2],
                "event_type": row[3],
                "payload": row[4],
            }


def _pg_get_recent_events(limit=200, stream_id=None):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if stream_id:
                cur.execute(
                    f"""
                    SELECT id, created_at, event_type, payload
                    FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE event_type != 'live_viewers' AND stream_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (stream_id, limit),
                )
                rows = cur.fetchall()
                cur.execute(
                    f"""
                    SELECT id, created_at, event_type, payload
                    FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE event_type = 'live_viewers' AND stream_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (stream_id,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT id, created_at, event_type, payload
                    FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE event_type != 'live_viewers'
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                cur.execute(
                    f"""
                    SELECT id, created_at, event_type, payload
                    FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE event_type = 'live_viewers'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            viewer_row = cur.fetchone()
            if viewer_row:
                rows.append(viewer_row)
            return [
                {"id": r[0], "created_at": r[1], "event_type": r[2], "payload": r[3]}
                for r in sorted(rows, key=lambda r: r[0])
            ]


def _pg_latest_db_event(event_type, stream_id=None):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if stream_id:
                cur.execute(
                    f"""
                    SELECT id, created_at, payload FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE event_type = %s AND stream_id = %s
                    ORDER BY id DESC LIMIT 1
                    """,
                    (event_type, stream_id),
                )
            else:
                cur.execute(
                    f"""
                    SELECT id, created_at, payload FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE event_type = %s
                    ORDER BY id DESC LIMIT 1
                    """,
                    (event_type,),
                )
            row = cur.fetchone()
            if not row:
                return {}
            try:
                payload = json.loads(row[2] or "{}")
            except Exception:
                payload = {}
            if event_type == "auction_winner" and not (payload.get("product_name") or "").strip():
                winner_event_id = row[0]
                sid = stream_id
                if not sid:
                    cur.execute(
                        f"SELECT stream_id FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE id = %s",
                        (winner_event_id,),
                    )
                    sid_row = cur.fetchone()
                    sid = sid_row[0] if sid_row else None
                if sid:
                    cur.execute(
                        f"""SELECT payload FROM {POSTGRES_SIDECAR_SCHEMA}.events
                            WHERE stream_id = %s AND event_type = 'lot_update' AND id <= %s
                            ORDER BY id DESC LIMIT 1""",
                        (sid, winner_event_id),
                    )
                    lot_row = cur.fetchone()
                    if lot_row:
                        try:
                            lot_payload = json.loads(lot_row[0] or "{}")
                            backfill = (lot_payload.get("product_name") or "").strip()
                            if backfill:
                                payload["product_name"] = backfill
                        except Exception:
                            pass
    payload["_event_id"] = row[0]
    payload["_created_at"] = row[1]
    return payload


def _pg_get_stream_event_rows(stream_id):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, event_type, payload, created_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE stream_id = %s
                ORDER BY id ASC
                """,
                (stream_id,),
            )
            return cur.fetchall()


def _pg_get_collector_health(stream_id=None):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            types_of_interest = ["chat_message", "lot_update", "bid_update", "auction_winner", "live_viewers"]
            health = {}
            for etype in types_of_interest:
                if stream_id:
                    cur.execute(
                        f"SELECT MAX(created_at) FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE event_type = %s AND stream_id = %s",
                        (etype, int(stream_id)),
                    )
                else:
                    cur.execute(
                        f"SELECT MAX(created_at) FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE event_type = %s",
                        (etype,),
                    )
                row = cur.fetchone()
                health[etype] = row[0] if row else None
            if stream_id:
                cur.execute(
                    f"SELECT MAX(created_at), COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = %s",
                    (int(stream_id),),
                )
            else:
                cur.execute(
                    f"SELECT MAX(created_at), COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.events"
                )
            total_row = cur.fetchone()
            health["last_event_at"] = total_row[0] if total_row else None
            health["total_events"] = total_row[1] if total_row else 0
            return health


def _our_stream_ids(our_stream_urls, our_streamer_names, conn):
    """Return set of stream IDs that belong to us (to exclude from competitor queries)."""
    raise RuntimeError("events_db_sqlite_runtime_retired")


def _our_stream_ids_pg(our_stream_urls, our_streamer_names):
    ids = set()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if our_stream_urls:
                for url in our_stream_urls:
                    cur.execute(
                        f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE stream_url=%s OR stream_url=%s",
                        (url, url.split("?")[0]),
                    )
                    ids.update(int(row[0]) for row in cur.fetchall())
            all_names = _OUR_STREAMER_NAMES | {n.lower() for n in (our_streamer_names or [])}
            for name in all_names:
                cur.execute(
                    f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE LOWER(streamer_name)=%s",
                    (name,),
                )
                ids.update(int(row[0]) for row in cur.fetchall())
    return ids


def get_stream_id(stream_url, db_path=None):
    """Return the stream_id for a given stream URL."""
    if not stream_url:
        return None
    if db_path:
        return _manual_events_compat_call("get_stream_id", stream_url, db_path=db_path)
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_stream_id(stream_url)


def get_latest_id(db_path=None):
    """Return the highest event id."""
    if db_path:
        return _manual_events_compat_call("get_latest_id", db_path=db_path)
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_latest_id()


def get_latest_id_for_stream(stream_id, db_path=None):
    """Return the highest event id for one stream."""
    if not stream_id:
        return 0
    if db_path:
        return _manual_events_compat_call("get_latest_id_for_stream", stream_id, db_path=db_path)
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_latest_id_for_stream(stream_id)


def get_events_since(since_id, stream_id=None, limit=500, db_path=None):
    """Return events with id > since_id, ordered ascending. Filter by stream_id if given."""
    if db_path:
        return _manual_events_compat_call(
            "get_events_since",
            since_id,
            stream_id=stream_id,
            limit=limit,
            db_path=db_path,
        )
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_events_since(since_id, stream_id=stream_id, limit=limit)


def get_event_by_id(event_id, db_path=None):
    """Return a single event row by id, including stream identity."""
    if db_path:
        return _manual_events_compat_call("get_event_by_id", event_id, db_path=db_path)
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_event_by_id(event_id)


def get_latest_lot_update_product_name(stream_id, db_path=None):
    if db_path:
        return _manual_events_compat_call("get_latest_lot_update_product_name", stream_id, db_path=db_path)
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_latest_lot_update_product_name(stream_id)


def get_recent_events(limit=200, stream_id=None, db_path=None):
    """Return recent events in chronological order, mixing all useful types.

    live_viewers events are high-frequency and crowd out chat/winner events
    when fetching a fixed-size window. We return up to `limit` non-viewer
    events PLUS the single most recent live_viewers event so the viewer
    count stays current without drowning everything else.
    """
    if db_path:
        return _manual_events_compat_call(
            "get_recent_events",
            limit=limit,
            stream_id=stream_id,
            db_path=db_path,
        )
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_recent_events(limit=limit, stream_id=stream_id)


def latest_db_event(event_type, stream_id=None, db_path=None):
    """Return the latest event of a given type with parsed payload.

    Filters by stream_id when provided so stale events from previous streams
    are not surfaced during a new session.

    For auction_winner events: if product_name is missing, backfills it from
    the most recent lot_update that occurred before the winner event.
    """
    if db_path:
        return _manual_events_compat_call(
            "latest_db_event",
            event_type,
            stream_id=stream_id,
            db_path=db_path,
        )
    _require_postgres_runtime(db_path=db_path)
    return _pg_latest_db_event(event_type, stream_id=stream_id)


def get_all_streams(db_path=None):
    """Return all known streams (id, stream_url, streamer_name, title, started_at, ended_at) newest first."""
    if db_path:
        return _manual_events_compat_call("get_all_streams", db_path=db_path)
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_all_streams()


def get_streamer_name_for_stream(stream_id, db_path=None):
    stream_id = int(stream_id or 0)
    if not stream_id:
        return None
    streams = get_all_streams(db_path=db_path)
    for row in streams:
        if int(row.get("id") or 0) == stream_id:
            return row.get("streamer_name")
    return None


def _pg_fetch_cross_stream_winner_rows():
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT e.payload, e.created_at, s.id AS stream_id, s.streamer_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.events e
                JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = e.stream_id
                WHERE e.event_type = 'auction_winner'
                ORDER BY e.id ASC
                """
            )
            return [
                {
                    "payload": row[0],
                    "created_at": row[1],
                    "stream_id": row[2],
                    "streamer_name": row[3],
                }
                for row in cur.fetchall()
            ]


def _build_cross_stream_users(rows, min_streams=2, limit=500, q=""):
    query = (q or "").strip().lower()
    user_map = {}
    for row in rows:
        try:
            payload = json.loads(row.get("payload") or "{}")
        except Exception:
            payload = {}
        username = _normalize_username(payload.get("winner"))
        if not username:
            continue
        item = user_map.setdefault(username, {
            "username": username,
            "total_wins": 0,
            "total_spent": 0.0,
            "stream_count": 0,
            "streams": {},
            "first_seen": None,
            "last_seen": None,
        })
        stream_id = row.get("stream_id")
        stream_rec = item["streams"].setdefault(stream_id, {
            "stream_id": stream_id,
            "streamer_name": row.get("streamer_name"),
            "wins": 0,
            "spent": 0.0,
            "first_seen": None,
            "last_seen": None,
        })
        price = _parse_winner_price(payload)
        created_at = row.get("created_at")
        item["total_wins"] += 1
        item["total_spent"] = round(item["total_spent"] + price, 2)
        stream_rec["wins"] += 1
        stream_rec["spent"] = round(stream_rec["spent"] + price, 2)
        if not item["first_seen"] or (created_at and created_at < item["first_seen"]):
            item["first_seen"] = created_at
        if not item["last_seen"] or (created_at and created_at > item["last_seen"]):
            item["last_seen"] = created_at
        if not stream_rec["first_seen"] or (created_at and created_at < stream_rec["first_seen"]):
            stream_rec["first_seen"] = created_at
        if not stream_rec["last_seen"] or (created_at and created_at > stream_rec["last_seen"]):
            stream_rec["last_seen"] = created_at

    users = []
    for item in user_map.values():
        streams = list(item["streams"].values())
        item["stream_count"] = len(streams)
        item["streams"] = streams
        if item["stream_count"] >= int(min_streams or 1):
            users.append(item)
    if query:
        users = [item for item in users if query in item["username"].lower()]
    users.sort(key=lambda item: (-item["stream_count"], -item["total_spent"]))
    return users[: int(limit or 500)]


def get_cross_stream_users(min_streams=2, limit=500, q="", db_path=None):
    if db_path:
        sqlite_value = _manual_events_compat_call(
            "get_cross_stream_users",
            min_streams=min_streams,
            limit=limit,
            q=q,
            db_path=db_path,
        )
        return {"users": sqlite_value, "total": len(sqlite_value)}
    _require_postgres_runtime(db_path=db_path)
    postgres_value = _build_cross_stream_users(
        _pg_fetch_cross_stream_winner_rows(),
        min_streams=min_streams,
        limit=limit,
        q=q,
    )
    return {"users": postgres_value, "total": len(postgres_value)}


def _build_competitor_price_products(rows, limit=200, q=""):
    query = (q or "").strip().lower()
    grouped_rows = []
    for row in rows:
        try:
            payload = json.loads(row.get("payload") or "{}")
        except Exception:
            payload = {}
        product_name = str(payload.get("footer_text") or "").strip()
        if not product_name:
            continue
        price = _parse_winner_price(payload)
        if price <= 0:
            continue
        grouped_rows.append({
            "product_name": product_name,
            "streamer_name": row.get("streamer_name"),
            "stream_id": row.get("stream_id"),
            "price": float(price),
        })

    per_stream_product = {}
    for row in grouped_rows:
        key = (row["product_name"], row["stream_id"])
        rec = per_stream_product.setdefault(key, {
            "product_name": row["product_name"],
            "streamer_name": row.get("streamer_name"),
            "stream_id": row.get("stream_id"),
            "times_sold": 0,
            "prices": [],
        })
        rec["times_sold"] += 1
        rec["prices"].append(float(row["price"]))

    items = []
    for rec in per_stream_product.values():
        prices = rec["prices"]
        items.append({
            "product_name": rec["product_name"],
            "streamer_name": rec["streamer_name"],
            "stream_id": rec["stream_id"],
            "times_sold": rec["times_sold"],
            "avg_price": round(sum(prices) / len(prices), 2) if prices else 0.0,
            "min_price": round(min(prices), 2) if prices else 0.0,
            "max_price": round(max(prices), 2) if prices else 0.0,
        })
    items.sort(key=lambda item: (-item["times_sold"], item["product_name"].lower(), int(item["stream_id"] or 0)))
    items = items[: max(1, int(limit or 200)) * 3]

    if query:
        items = [
            row for row in items
            if query in str(row.get("product_name") or "").lower()
            or query in str(row.get("streamer_name") or "").lower()
        ]

    prod_map = {}
    for row in items:
        key = (row.get("product_name") or "").strip()
        if not key:
            continue
        rec = prod_map.setdefault(key, {
            "product_name": key,
            "total_sold": 0,
            "streamers": [],
            "all_avg": 0.0,
            "min_price": None,
            "max_price": None,
        })
        rec["total_sold"] += int(row.get("times_sold") or 0)
        rec["streamers"].append({
            "streamer": row.get("streamer_name"),
            "stream_id": row.get("stream_id"),
            "times_sold": row.get("times_sold"),
            "avg_price": row.get("avg_price"),
            "min_price": row.get("min_price"),
            "max_price": row.get("max_price"),
        })
        if rec["min_price"] is None or float(row.get("min_price") or 0) < rec["min_price"]:
            rec["min_price"] = float(row.get("min_price") or 0)
        if rec["max_price"] is None or float(row.get("max_price") or 0) > rec["max_price"]:
            rec["max_price"] = float(row.get("max_price") or 0)

    for rec in prod_map.values():
        prices = [float(item.get("avg_price") or 0) for item in rec["streamers"] if item.get("avg_price") is not None]
        rec["all_avg"] = round(sum(prices) / len(prices), 2) if prices else 0.0

    products = sorted(prod_map.values(), key=lambda item: (-item["total_sold"], item["product_name"].lower()))
    return {"products": products[: int(limit or 200)], "total": len(products)}


def get_competitor_price_products(limit=200, q="", db_path=None):
    if db_path:
        return _manual_events_compat_call(
            "get_competitor_price_products",
            limit=limit,
            q=q,
            db_path=db_path,
        )
    _require_postgres_runtime(db_path=db_path)
    return _build_competitor_price_products(
        _pg_fetch_cross_stream_winner_rows(),
        limit=limit,
        q=q,
    )


def _build_competitor_prices(rows, q="", limit=200):
    query = (q or "").strip().lower()
    prod_map = {}
    for row in rows:
        try:
            payload = json.loads(row.get("payload") or "{}")
        except Exception:
            payload = {}
        product_name = str(payload.get("footer_text") or "").strip()
        price = _parse_winner_price(payload)
        if not product_name or price <= 0:
            continue
        if query and query not in product_name.lower() and query not in str(row.get("streamer_name") or "").lower():
            continue
        product = prod_map.setdefault(product_name, {
            "product_name": product_name,
            "total_sold": 0,
            "streamers": {},
            "all_avg": 0.0,
            "min_price": None,
            "max_price": None,
        })
        product["total_sold"] += 1
        stream_key = (row.get("stream_id"), row.get("streamer_name"))
        stream_rec = product["streamers"].setdefault(stream_key, {
            "streamer": row.get("streamer_name"),
            "stream_id": row.get("stream_id"),
            "times_sold": 0,
            "prices": [],
            "avg_price": 0.0,
            "min_price": None,
            "max_price": None,
        })
        stream_rec["times_sold"] += 1
        stream_rec["prices"].append(price)
        stream_rec["min_price"] = price if stream_rec["min_price"] is None else min(stream_rec["min_price"], price)
        stream_rec["max_price"] = price if stream_rec["max_price"] is None else max(stream_rec["max_price"], price)
        product["min_price"] = price if product["min_price"] is None else min(product["min_price"], price)
        product["max_price"] = price if product["max_price"] is None else max(product["max_price"], price)

    products = []
    for product in prod_map.values():
        streamers = []
        for stream_rec in product["streamers"].values():
            prices = stream_rec.pop("prices", [])
            stream_rec["avg_price"] = round(sum(prices) / len(prices), 2) if prices else 0
            streamers.append(stream_rec)
        streamers.sort(key=lambda item: -int(item.get("times_sold") or 0))
        product["streamers"] = streamers
        avgs = [entry["avg_price"] for entry in streamers if entry.get("avg_price")]
        product["all_avg"] = round(sum(avgs) / len(avgs), 2) if avgs else 0
        products.append(product)
    products.sort(key=lambda item: -int(item.get("total_sold") or 0))
    return products[: int(limit or 200)]


def _pg_fetch_competitor_price_rows():
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT e.payload, s.streamer_name, s.id AS stream_id
                FROM {POSTGRES_SIDECAR_SCHEMA}.events e
                JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = e.stream_id
                WHERE e.event_type = 'auction_winner'
                ORDER BY e.id DESC
                """
            )
            return [
                {"payload": row[0], "streamer_name": row[1], "stream_id": row[2]}
                for row in cur.fetchall()
            ]


def get_competitor_prices(q="", limit=200, db_path=None):
    if db_path:
        sqlite_value = _manual_events_compat_call(
            "get_competitor_prices",
            q=q,
            limit=limit,
            db_path=db_path,
        )
        return {"products": sqlite_value, "total": len(sqlite_value)}
    _require_postgres_runtime(db_path=db_path)
    postgres_value = _build_competitor_prices(_pg_fetch_competitor_price_rows(), q=q, limit=limit)
    return {"products": postgres_value, "total": len(postgres_value)}


def _minutes_between(start_at, end_at):
    if not start_at or not end_at:
        return 0
    try:
        start_dt = datetime.fromisoformat(start_at)
        end_dt = datetime.fromisoformat(end_at)
    except Exception:
        return 0
    delta_seconds = max(0.0, (end_dt - start_dt).total_seconds())
    return round(delta_seconds / 60.0, 1)


def _stream_timeline_rows(rows):
    return [(row[1], row[2], row[3]) for row in rows]


def _compute_stream_event_summary(rows, stream_id):
    """Return recent collection heartbeat metrics for one stream."""

    counts = defaultdict(int)
    first_event_at = None
    last_event_at = None
    last_sale_at = None
    last_chat_at = None
    viewer_peak = 0
    viewer_latest = None

    for event_type, raw_payload, created_at in _stream_timeline_rows(rows):
        counts[event_type] += 1
        if not first_event_at or created_at < first_event_at:
            first_event_at = created_at
        if not last_event_at or created_at > last_event_at:
            last_event_at = created_at
        if event_type == "chat_message":
            last_chat_at = created_at
        elif event_type == "auction_winner":
            last_sale_at = created_at
        elif event_type == "live_viewers":
            try:
                payload = json.loads(raw_payload or "{}")
            except Exception:
                payload = {}
            count = payload.get("viewer_count", payload.get("count"))
            try:
                count = int(count)
            except Exception:
                count = None
            if count is not None:
                viewer_latest = count
                viewer_peak = max(viewer_peak, count)

    non_viewer_events = sum(v for k, v in counts.items() if k != "live_viewers")
    return {
        "stream_id": stream_id,
        "first_event_at": first_event_at,
        "last_event_at": last_event_at,
        "last_chat_at": last_chat_at,
        "last_sale_at": last_sale_at,
        "viewer_latest": viewer_latest,
        "viewer_peak": viewer_peak or None,
        "event_counts": dict(sorted(counts.items())),
        "non_viewer_event_count": non_viewer_events,
        "active_minutes": _minutes_between(first_event_at, last_event_at),
        "is_collecting": bool(last_event_at),
    }


def get_stream_event_summary(stream_id, db_path=None):
    """Return recent collection heartbeat metrics for one stream."""
    if db_path:
        sqlite_value = _manual_events_compat_call("get_stream_event_summary", stream_id, db_path=db_path)
        return sqlite_value
    _require_postgres_runtime(db_path=db_path)
    postgres_rows = _pg_get_stream_event_rows(stream_id)
    return _compute_stream_event_summary(postgres_rows, stream_id)


def _pg_get_competitor_businesses(our_stream_urls=None, our_streamer_names=None):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    our_urls = set(our_stream_urls or [])
    our_names = {n.lower() for n in (our_streamer_names or [])} | {"ynfdeals"}
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, stream_url, streamer_name, title, started_at, ended_at FROM {POSTGRES_SIDECAR_SCHEMA}.streams ORDER BY id DESC"
            )
            rows = cur.fetchall()
            cur.execute(
                f"SELECT stream_id, COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.events GROUP BY stream_id"
            )
            event_counts = {r[0]: r[1] for r in cur.fetchall()}

    businesses = {}
    for sid, url, name, title, started_at, ended_at in rows:
        if url in our_urls or (url and url.split("?")[0] in our_urls):
            continue
        if name and name.lower() in our_names:
            continue
        if event_counts.get(sid, 0) == 0:
            continue
        match = re.search(r'/live/([^/?#]+)', url or '')
        key = name or (match.group(1) if match else None) or url or str(sid)
        if key not in businesses:
            businesses[key] = {
                "streamer_name": key,
                "stream_url": url,
                "sessions": [],
            }
        businesses[key]["sessions"].append({
            "id": sid,
            "started_at": started_at,
            "ended_at": ended_at,
            "event_count": event_counts.get(sid, 0),
        })

    return list(businesses.values())


def get_competitor_businesses(our_stream_urls=None, our_streamer_names=None, db_path=None):
    """Return competitor streams grouped by streamer_name, excluding our own stream URLs.

    Returns list of:
      {
        streamer_name, stream_url,
        sessions: [{id, started_at, ended_at, event_count}]  -- newest first
      }
    Only includes streamers who have at least 1 event (no empty/failed runs).
    """
    if db_path:
        return _manual_events_compat_call(
            "get_competitor_businesses",
            our_stream_urls=our_stream_urls,
            our_streamer_names=our_streamer_names,
            db_path=db_path,
        )
    return _pg_get_competitor_businesses(our_stream_urls=our_stream_urls, our_streamer_names=our_streamer_names)


def _pg_get_competitor_listings(stream_id):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT MAX(scraped_at) FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings WHERE stream_id = %s",
                (stream_id,),
            )
            row = cur.fetchone()
            latest_ts = row[0] if row else None
            if not latest_ts:
                return {"scraped_at": None, "total": 0, "by_type": {}, "listings": []}
            cur.execute(
                f"SELECT product_name, qty, starting_price, bid_count, listing_type, image_url, button_label, badge_text, catalog_position "
                f"FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings WHERE stream_id = %s AND scraped_at = %s ORDER BY id ASC",
                (stream_id, latest_ts),
            )
            listings = [
                {
                    "product_name": r[0],
                    "qty": r[1],
                    "starting_price": r[2],
                    "bid_count": r[3],
                    "listing_type": r[4],
                    "image_url": r[5],
                    "button_label": r[6],
                    "badge_text": r[7],
                    "catalog_position": r[8],
                }
                for r in cur.fetchall()
            ]
    by_type = {}
    for item in listings:
        listing_type = item["listing_type"] or "unknown"
        by_type[listing_type] = by_type.get(listing_type, 0) + 1
    return {"scraped_at": latest_ts, "total": len(listings), "by_type": by_type, "listings": listings}


def get_competitor_listings(stream_id, db_path=None):
    """Return the latest snapshot of competitor shop listings for a stream.

    Selects only rows from the most recent scrape (MAX scraped_at) so the
    caller always gets a consistent point-in-time view of the shop panel.
    Returns a dict with:
      - scraped_at: ISO timestamp of the snapshot
      - total: total listing count
      - by_type: {listing_type: count}
      - listings: [{product_name, qty, starting_price, bid_count, listing_type, image_url, button_label, badge_text, catalog_position}]
    """
    if db_path:
        return _manual_events_compat_call("get_competitor_listings", stream_id, db_path=db_path)
    return _pg_get_competitor_listings(stream_id)


def _pg_get_stream_users_rows(stream_id):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT event_type, payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = %s ORDER BY id ASC",
                (stream_id,),
            )
            return cur.fetchall()


def get_stream_users(stream_id, db_path=None):
    """Return all users seen in a stream with combined chat + purchase stats.

    Each entry:
      username, messages, lots_won, total_spent, avg_price,
      first_seen, last_seen, tier (whale/heavy/regular/chatter)
    Sorted by total_spent desc, then message_count desc.
    """
    if db_path:
        rows = _manual_events_compat_call("get_stream_users", stream_id, db_path=db_path)
    else:
        rows = _pg_get_stream_users_rows(stream_id)

    import re
    users = {}

    def _get(u):
        if u not in users:
            users[u] = {
                "username": u,
                "messages": 0,
                "lots_won": 0,
                "total_spent": 0.0,
                "first_seen": None,
                "last_seen": None,
                "event_count": 0,
            }
        return users[u]

    for event_type, raw_payload, created_at in rows:
        try:
            p = json.loads(raw_payload or "{}")
        except Exception:
            p = {}

        if event_type == "chat_message":
            u = p.get("username") or p.get("user") or ""
            if not u:
                continue
            rec = _get(u)
            rec["messages"] += 1
            rec["event_count"] += 1
            if not rec["first_seen"] or created_at < rec["first_seen"]:
                rec["first_seen"] = created_at
            if not rec["last_seen"] or created_at > rec["last_seen"]:
                rec["last_seen"] = created_at

        elif event_type == "auction_winner":
            u = p.get("winner") or p.get("winner_username") or p.get("username") or ""
            if not u:
                continue
            price = 0.0
            pv = p.get("price_value") or p.get("winning_price") or p.get("sale_price")
            if pv is not None:
                try:
                    price = float(pv)
                except Exception:
                    pass
            if price == 0:
                raw = str(p.get("price") or p.get("footer_text") or "")
                m = re.findall(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)", raw)
                if m:
                    try:
                        price = float(m[-1].replace(",", ""))
                    except Exception:
                        pass
            rec = _get(u)
            rec["lots_won"] += 1
            rec["total_spent"] = round(rec["total_spent"] + price, 2)
            rec["event_count"] += 1
            if not rec["first_seen"] or created_at < rec["first_seen"]:
                rec["first_seen"] = created_at
            if not rec["last_seen"] or created_at > rec["last_seen"]:
                rec["last_seen"] = created_at

    result = []
    for rec in users.values():
        spent = rec["total_spent"]
        won = rec["lots_won"]
        if spent >= 500:
            tier = "whale"
        elif spent >= 100:
            tier = "heavy"
        elif won > 0:
            tier = "regular"
        else:
            tier = "chatter"
        result.append({
            **rec,
            "avg_price": round(spent / won, 2) if won else 0.0,
            "active_minutes": _minutes_between(rec["first_seen"], rec["last_seen"]),
            "tier": tier,
        })

    result.sort(key=lambda x: (-x["total_spent"], -x["messages"]))
    return result


def _pg_get_user_purchase_rows(stream_id):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = %s AND event_type = 'auction_winner' ORDER BY id ASC",
                (stream_id,),
            )
            return cur.fetchall()


def get_user_purchases(stream_id, username, db_path=None):
    """Return all purchases made by a username in a given stream.

    Each entry: product, lot_number, price, time
    """
    if db_path:
        rows = _manual_events_compat_call("get_user_purchases", stream_id, db_path=db_path)
    else:
        rows = _pg_get_user_purchase_rows(stream_id)

    import re
    purchases = []
    for raw_payload, created_at in rows:
        try:
            p = json.loads(raw_payload or "{}")
        except Exception:
            continue
        u = p.get("winner") or p.get("winner_username") or p.get("username") or ""
        if u.lower() != username.lower():
            continue
        price = 0.0
        pv = p.get("price_value") or p.get("winning_price") or p.get("sale_price")
        if pv is not None:
            try:
                price = float(pv)
            except Exception:
                pass
        if price == 0:
            raw = str(p.get("price") or p.get("footer_text") or "")
            m = re.findall(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)", raw)
            if m:
                try:
                    price = float(m[-1].replace(",", ""))
                except Exception:
                    pass
        purchases.append({
            "product": p.get("product_name") or p.get("title") or "",
            "lot_number": p.get("lot_number") or "",
            "price": price,
            "time": created_at,
        })
    return purchases


def _pg_get_audience_users_rows():
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT e.event_type, e.payload, e.created_at, s.id AS stream_id, s.streamer_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.events e
                JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = e.stream_id
                WHERE e.event_type IN ('chat_message', 'auction_winner', 'bid_update')
                ORDER BY e.id ASC
                """
            )
            return _pg_fetchall_dict(cur)


def get_audience_users(min_streams=1, limit=500, q="", db_path=None):
    """Return a broad audience list aggregated from chat, bids, and winners."""
    cache_key = (int(min_streams or 1), int(limit or 500), (q or "").strip().lower(), _events_cache_backend_key(db_path))
    cached = _AUDIENCE_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached["ts"] <= _AUDIENCE_CACHE_TTL:
        return list(cached["rows"])

    if db_path:
        rows = _manual_events_compat_call("get_audience_users", db_path=db_path)
    else:
        rows = _pg_get_audience_users_rows()

    query = (q or "").strip().lower()
    user_map = {}

    def _get_user(username):
        rec = user_map.get(username)
        if rec:
            return rec
        rec = {
            "username": username,
            "chat_messages": 0,
            "bids": 0,
            "wins": 0,
            "total_spent": 0.0,
            "first_seen": None,
            "last_seen": None,
            "streams": {},
            "roles": set(),
        }
        user_map[username] = rec
        return rec

    for row in rows:
        event_type = row["event_type"]
        created_at = row["created_at"]
        stream_id = row["stream_id"]
        streamer_name = row["streamer_name"] or ""
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        roles = _extract_event_user_roles(event_type, payload)
        if not roles:
            continue
        seen_in_event = set()
        for username, role in roles:
            if not username or username in seen_in_event:
                continue
            seen_in_event.add(username)
            rec = _get_user(username)
            stream_rec = rec["streams"].setdefault(stream_id, {
                "stream_id": stream_id,
                "streamer_name": streamer_name,
                "chat_messages": 0,
                "bids": 0,
                "wins": 0,
                "spent": 0.0,
                "first_seen": None,
                "last_seen": None,
            })
            rec["roles"].add(role)
            if role == "chat":
                rec["chat_messages"] += 1
                stream_rec["chat_messages"] += 1
            elif role == "bidder":
                rec["bids"] += 1
                stream_rec["bids"] += 1
            elif role == "winner":
                price = _parse_winner_price(payload)
                rec["wins"] += 1
                rec["total_spent"] = round(rec["total_spent"] + price, 2)
                stream_rec["wins"] += 1
                stream_rec["spent"] = round(stream_rec["spent"] + price, 2)
            else:
                rec["bids"] += 1
                stream_rec["bids"] += 1

            if not rec["first_seen"] or (created_at and created_at < rec["first_seen"]):
                rec["first_seen"] = created_at
            if not rec["last_seen"] or (created_at and created_at > rec["last_seen"]):
                rec["last_seen"] = created_at
            if not stream_rec["first_seen"] or (created_at and created_at < stream_rec["first_seen"]):
                stream_rec["first_seen"] = created_at
            if not stream_rec["last_seen"] or (created_at and created_at > stream_rec["last_seen"]):
                stream_rec["last_seen"] = created_at

    users = []
    for username, rec in user_map.items():
        stream_rows = sorted(
            rec["streams"].values(),
            key=lambda row: (-row["spent"], -row["wins"], -row["chat_messages"], row["streamer_name"]),
        )
        if len(stream_rows) < max(1, int(min_streams or 1)):
            continue
        if query and query not in username:
            continue
        spent = round(rec["total_spent"], 2)
        if spent >= 500:
            tier = "whale"
        elif spent >= 100:
            tier = "heavy"
        elif rec["wins"] > 0:
            tier = "buyer"
        elif rec["bids"] > 0:
            tier = "bidder"
        else:
            tier = "chatter"
        users.append({
            "username": username,
            "stream_count": len(stream_rows),
            "chat_messages": rec["chat_messages"],
            "bids": rec["bids"],
            "total_wins": rec["wins"],
            "total_spent": spent,
            "first_seen": rec["first_seen"],
            "last_seen": rec["last_seen"],
            "roles": sorted(rec["roles"]),
            "tier": tier,
            "streams": stream_rows,
        })

    users.sort(key=lambda row: (-row["stream_count"], -row["total_spent"], -row["total_wins"], -row["chat_messages"]))
    result = users[: max(1, int(limit or 500))]
    _AUDIENCE_CACHE[cache_key] = {"ts": now, "rows": list(result)}
    return result


def _pg_get_audience_user_profile_rows(uname):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT e.event_type, e.payload, e.created_at, s.id AS stream_id, s.streamer_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.events e
                JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = e.stream_id
                WHERE e.event_type IN ('chat_message', 'auction_winner', 'bid_update')
                  AND LOWER(e.payload) LIKE %s
                ORDER BY e.created_at DESC, e.id DESC
                """,
                (f'%"{uname}"%',),
            )
            return _pg_fetchall_dict(cur)


def get_audience_user_profile(username, db_path=None):
    """Return a broad per-user profile from chat, bids, and winner events."""
    uname = _normalize_username(username)
    if not uname:
        return None

    if db_path:
        event_rows = _manual_events_compat_call("get_audience_user_profile", uname, db_path=db_path)
    else:
        event_rows = _pg_get_audience_user_profile_rows(uname)

    if not event_rows:
        return None

    profile = {
        "username": uname,
        "tier": "chatter",
        "roles": set(),
        "stream_count": 0,
        "chat_messages": 0,
        "bids": 0,
        "total_wins": 0,
        "total_spent": 0.0,
        "first_seen": None,
        "last_seen": None,
        "streams": {},
    }
    timeline = []
    purchases = []
    for row in event_rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        roles = _extract_event_user_roles(row["event_type"], payload)
        match_role = next((role for candidate, role in roles if candidate == uname), None)
        if not match_role:
            continue
        profile["roles"].add(match_role)
        stream_rec = profile["streams"].setdefault(row["stream_id"], {
            "stream_id": row["stream_id"],
            "streamer_name": row["streamer_name"],
            "chat_messages": 0,
            "bids": 0,
            "wins": 0,
            "spent": 0.0,
            "first_seen": None,
            "last_seen": None,
        })
        if match_role == "chat":
            profile["chat_messages"] += 1
            stream_rec["chat_messages"] += 1
        elif match_role == "bidder":
            profile["bids"] += 1
            stream_rec["bids"] += 1
        elif match_role == "winner":
            price = round(_parse_winner_price(payload), 2)
            profile["total_wins"] += 1
            profile["total_spent"] = round(profile["total_spent"] + price, 2)
            stream_rec["wins"] += 1
            stream_rec["spent"] = round(stream_rec["spent"] + price, 2)
        if not profile["first_seen"] or (row["created_at"] and row["created_at"] < profile["first_seen"]):
            profile["first_seen"] = row["created_at"]
        if not profile["last_seen"] or (row["created_at"] and row["created_at"] > profile["last_seen"]):
            profile["last_seen"] = row["created_at"]
        if not stream_rec["first_seen"] or (row["created_at"] and row["created_at"] < stream_rec["first_seen"]):
            stream_rec["first_seen"] = row["created_at"]
        if not stream_rec["last_seen"] or (row["created_at"] and row["created_at"] > stream_rec["last_seen"]):
            stream_rec["last_seen"] = row["created_at"]
        item = {
            "time": row["created_at"],
            "streamer": row["streamer_name"],
            "stream_id": row["stream_id"],
            "role": match_role,
            "lot": payload.get("lot_number") or payload.get("lot") or "",
            "product": payload.get("product_name") or payload.get("title") or payload.get("item_name") or "",
            "price": 0.0,
        }
        if match_role == "winner":
            item["price"] = round(_parse_winner_price(payload), 2)
            purchases.append(dict(item))
        timeline.append(item)
        if len(timeline) >= 250:
            break

    streams = sorted(
        profile["streams"].values(),
        key=lambda row: (-row["spent"], -row["wins"], -row["chat_messages"], row["streamer_name"]),
    )
    spent = round(profile["total_spent"], 2)
    if spent >= 500:
        tier = "whale"
    elif spent >= 100:
        tier = "heavy"
    elif profile["total_wins"] > 0:
        tier = "buyer"
    elif profile["bids"] > 0:
        tier = "bidder"
    else:
        tier = "chatter"

    return {
        "username": profile["username"],
        "tier": tier,
        "roles": sorted(profile["roles"]),
        "stream_count": len(streams),
        "chat_messages": profile["chat_messages"],
        "bids": profile["bids"],
        "total_wins": profile["total_wins"],
        "total_spent": spent,
        "first_seen": profile["first_seen"],
        "last_seen": profile["last_seen"],
        "streams": streams,
        "purchases": purchases[:200],
        "timeline": timeline,
    }


def _pg_get_target_buyer_rows(normalized_streamers):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    LOWER(COALESCE(s.streamer_name, '')) AS streamer_name,
                    e.payload,
                    e.created_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.events e
                JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = e.stream_id
                WHERE e.event_type = 'auction_winner'
                  AND LOWER(COALESCE(s.streamer_name, '')) = ANY(%s)
                ORDER BY e.created_at DESC, e.id DESC
                """,
                (list(normalized_streamers),),
            )
            return _pg_fetchall_dict(cur)


def get_target_buyers(streamer_names=None, min_streamers=2, limit=100, q="", db_path=None):
    """Return cross-stream buyers worth targeting across selected competitor sellers."""
    normalized_streamers = tuple(sorted({
        _normalize_username(name)
        for name in (streamer_names or [])
        if _normalize_username(name)
    }))
    cache_key = (
        normalized_streamers,
        int(min_streamers or 2),
        int(limit or 100),
        (q or "").strip().lower(),
        _events_cache_backend_key(db_path),
    )
    cached = _TARGET_BUYER_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached["ts"] <= _TARGET_BUYER_CACHE_TTL:
        return cached["rows"]

    if not normalized_streamers:
        return {
            "watchlist": [],
            "buyers": [],
            "totals": {
                "watchlist_count": 0,
                "buyer_count": 0,
                "cross_stream_buyers": 0,
                "whales": 0,
                "total_spend": 0.0,
                "total_wins": 0,
            },
        }

    if db_path:
        rows = _manual_events_compat_call("get_target_buyers", normalized_streamers, db_path=db_path)
    else:
        rows = _pg_get_target_buyer_rows(normalized_streamers)

    query = (q or "").strip().lower()
    buyer_map = {}

    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        username = _normalize_username(
            payload.get("winner") or payload.get("winner_username") or payload.get("username")
        )
        if not username:
            continue
        if query and query not in username:
            continue
        price = round(_parse_winner_price(payload), 2)
        streamer_name = row["streamer_name"] or ""
        rec = buyer_map.setdefault(username, {
            "username": username,
            "total_spent": 0.0,
            "total_wins": 0,
            "first_seen": None,
            "last_seen": None,
            "streamers": {},
        })
        streamer_rec = rec["streamers"].setdefault(streamer_name, {
            "streamer_name": streamer_name,
            "wins": 0,
            "spent": 0.0,
            "first_seen": None,
            "last_seen": None,
        })
        rec["total_spent"] = round(rec["total_spent"] + price, 2)
        rec["total_wins"] += 1
        streamer_rec["spent"] = round(streamer_rec["spent"] + price, 2)
        streamer_rec["wins"] += 1
        created_at = row["created_at"]
        if not rec["first_seen"] or (created_at and created_at < rec["first_seen"]):
            rec["first_seen"] = created_at
        if not rec["last_seen"] or (created_at and created_at > rec["last_seen"]):
            rec["last_seen"] = created_at
        if not streamer_rec["first_seen"] or (created_at and created_at < streamer_rec["first_seen"]):
            streamer_rec["first_seen"] = created_at
        if not streamer_rec["last_seen"] or (created_at and created_at > streamer_rec["last_seen"]):
            streamer_rec["last_seen"] = created_at

    buyers = []
    for username, rec in buyer_map.items():
        streamer_rows = sorted(
            rec["streamers"].values(),
            key=lambda item: (-item["spent"], -item["wins"], item["streamer_name"]),
        )
        streamer_count = len(streamer_rows)
        if streamer_count < max(1, int(min_streamers or 2)):
            continue
        total_spent = round(rec["total_spent"], 2)
        if total_spent >= 2500:
            target_tier = "priority whale"
        elif total_spent >= 750:
            target_tier = "high value"
        elif total_spent >= 250:
            target_tier = "repeat buyer"
        else:
            target_tier = "emerging"
        buyers.append({
            "username": username,
            "streamer_count": streamer_count,
            "total_wins": rec["total_wins"],
            "total_spent": total_spent,
            "avg_spend_per_win": round(total_spent / max(1, rec["total_wins"]), 2),
            "first_seen": rec["first_seen"],
            "last_seen": rec["last_seen"],
            "target_tier": target_tier,
            "streamers": streamer_rows,
            "target_reason": (
                f"Buying across {streamer_count} target sellers with "
                f"{rec['total_wins']} wins and {total_spent:.2f} observed spend."
            ),
        })

    buyers.sort(key=lambda item: (-item["streamer_count"], -item["total_spent"], -item["total_wins"], item["username"]))
    buyers = buyers[: max(1, int(limit or 100))]
    result = {
        "watchlist": list(normalized_streamers),
        "buyers": buyers,
        "totals": {
            "watchlist_count": len(normalized_streamers),
            "buyer_count": len(buyers),
            "cross_stream_buyers": sum(1 for item in buyers if item["streamer_count"] >= 2),
            "whales": sum(1 for item in buyers if item["total_spent"] >= 750),
            "total_spend": round(sum(item["total_spent"] for item in buyers), 2),
            "total_wins": sum(item["total_wins"] for item in buyers),
        },
    }
    _TARGET_BUYER_CACHE[cache_key] = {"ts": now, "rows": result}
    return result


def _pg_get_stream_title_quality_rows(stream_id):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT event_type, payload, created_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE stream_id = %s
                  AND event_type IN ('lot_update', 'auction_winner')
                ORDER BY id DESC
                LIMIT 250
                """,
                (stream_id,),
            )
            return _pg_fetchall_dict(cur)


def get_stream_title_quality(stream_id, db_path=None):
    """Score how usable a stream's lot titles are for product identification."""
    cache_key = (int(stream_id or 0), _events_cache_backend_key(db_path))
    cached = _TITLE_QUALITY_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached["ts"] <= _TITLE_QUALITY_CACHE_TTL:
        return cached["rows"]

    if db_path:
        rows = _manual_events_compat_call("get_stream_title_quality", stream_id, db_path=db_path)
    else:
        rows = _pg_get_stream_title_quality_rows(stream_id)

    def _extract_title(payload):
        return (
            str(payload.get("product_name") or payload.get("title") or payload.get("item_name") or "")
            .strip()
        )

    def _classify_title(title):
        raw = str(title or "").strip()
        normalized = re.sub(r"\s+", " ", raw).strip().lower()
        if not normalized:
            return "blank", "No product name available."
        for pattern in _GENERIC_TITLE_PATTERNS:
            if re.search(pattern, normalized):
                return "generic", "Title looks like a placeholder or vague lot label."
        brand_hit = any(hint in normalized for hint in _PERFUME_BRAND_HINTS)
        long_enough = len(normalized) >= 18 and len(normalized.split()) >= 3
        has_size = bool(re.search(r"\b\d+(?:\.\d+)?\s?(?:ml|oz)\b", normalized))
        if brand_hit or has_size or long_enough:
            return "structured", "Title contains enough product detail to trust directly."
        return "semi_structured", "Title has some signal, but product matching may still need help."

    titles = []
    seen = set()
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        title = _extract_title(payload)
        if not title:
            continue
        lowered = title.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        kind, reason = _classify_title(title)
        titles.append({
            "title": title,
            "type": kind,
            "reason": reason,
            "seen_at": row["created_at"],
        })

    structured = sum(1 for item in titles if item["type"] == "structured")
    semi = sum(1 for item in titles if item["type"] == "semi_structured")
    generic = sum(1 for item in titles if item["type"] == "generic")
    blank = sum(1 for item in titles if item["type"] == "blank")
    total = len(titles)
    quality_score = round(((structured * 1.0) + (semi * 0.5)) / max(total, 1) * 100, 1)
    generic_ratio = round((generic + blank) / max(total, 1) * 100, 1)

    if total < 5:
        mode = "insufficient_data"
        recommendation = "Collect more lots before deciding whether OCR/captions are needed."
    elif generic_ratio >= 55:
        mode = "ocr_captions_recommended"
        recommendation = "This seller uses too many generic lot names. Turn on OCR + caption fallback."
    elif generic_ratio >= 25 or semi >= structured:
        mode = "hybrid"
        recommendation = "Use lot titles first, but enable OCR/captions when the title looks weak."
    else:
        mode = "titles_good"
        recommendation = "Lot titles are good enough most of the time. OCR/captions can stay low-frequency."

    result = {
        "stream_id": int(stream_id),
        "sample_size": total,
        "quality_score": quality_score,
        "generic_ratio": generic_ratio,
        "counts": {
            "structured": structured,
            "semi_structured": semi,
            "generic": generic,
            "blank": blank,
        },
        "mode": mode,
        "recommendation": recommendation,
        "sample_titles": titles[:12],
    }
    _TITLE_QUALITY_CACHE[cache_key] = {"ts": now, "rows": result}
    return result


def _pg_get_stream_detection_feed_rows(stream_id):
    _require_postgres_runtime()
    _ensure_detection_tables_pg()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT captured_at, image_path, ocr_text_raw, ocr_confidence, source
                FROM {POSTGRES_SIDECAR_SCHEMA}.stream_ocr_frames
                WHERE stream_id = %s
                ORDER BY captured_at DESC, id DESC
                LIMIT 10
                """,
                (int(stream_id),),
            )
            ocr_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT captured_at, caption_text, confidence, source
                FROM {POSTGRES_SIDECAR_SCHEMA}.stream_caption_windows
                WHERE stream_id = %s
                ORDER BY captured_at DESC, id DESC
                LIMIT 12
                """,
                (int(stream_id),),
            )
            caption_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT lot_number, resolved_product_name, resolved_brand, confidence, evidence_summary, resolution_status, resolved_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.resolved_lot_products
                WHERE stream_id = %s
                ORDER BY resolved_at DESC, id DESC
                LIMIT 20
                """,
                (int(stream_id),),
            )
            resolved_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT id, created_at, payload
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE stream_id = %s AND event_type = 'auction_winner'
                ORDER BY created_at DESC, id DESC
                LIMIT 120
                """,
                (int(stream_id),),
            )
            winner_rows = _pg_fetchall_dict(cur)
    return ocr_rows, caption_rows, resolved_rows, winner_rows


def get_stream_detection_feed(stream_id, db_path=None):
    """Return OCR/caption evidence and lot-resolution state for a stream."""
    if db_path:
        ocr_rows, caption_rows, resolved_rows, winner_rows = _manual_events_compat_call(
            "get_stream_detection_feed",
            stream_id,
            db_path=db_path,
        )
    else:
        ocr_rows, caption_rows, resolved_rows, winner_rows = _pg_get_stream_detection_feed_rows(stream_id)

    resolved_lots = {str(row["lot_number"] or "").strip() for row in resolved_rows if str(row["lot_number"] or "").strip()}
    unresolved = []
    seen_lots = set()
    for row in winner_rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        lot_number = str(payload.get("lot_number") or payload.get("lot") or "").strip()
        if not lot_number or lot_number in seen_lots:
            continue
        seen_lots.add(lot_number)
        if lot_number in resolved_lots:
            continue
        unresolved.append({
            "lot_number": lot_number,
            "winner_username": _normalize_username(payload.get("winner") or payload.get("winner_username") or payload.get("username")),
            "product_hint": str(payload.get("product_name") or payload.get("title") or payload.get("item_name") or "").strip(),
            "sale_price": round(_parse_winner_price(payload), 2),
            "sold_at": row["created_at"],
        })
        if len(unresolved) >= 12:
            break

    return {
        "stream_id": int(stream_id),
        "ocr_frames": [
            {
                "captured_at": row["captured_at"],
                "image_path": row["image_path"],
                "ocr_text_raw": row["ocr_text_raw"],
                "ocr_confidence": float(row["ocr_confidence"] or 0),
                "source": row["source"] or "manual",
            }
            for row in ocr_rows
        ],
        "captions": [
            {
                "captured_at": row["captured_at"],
                "caption_text": row["caption_text"],
                "confidence": float(row["confidence"] or 0),
                "source": row["source"] or "manual",
            }
            for row in caption_rows
        ],
        "resolved_lots": [
            {
                "lot_number": row["lot_number"],
                "resolved_product_name": row["resolved_product_name"],
                "resolved_brand": row["resolved_brand"],
                "confidence": float(row["confidence"] or 0),
                "evidence_summary": row["evidence_summary"],
                "resolution_status": row["resolution_status"] or "resolved",
                "resolved_at": row["resolved_at"],
            }
            for row in resolved_rows
        ],
        "unresolved_lots": unresolved,
        "totals": {
            "ocr_frames": len(ocr_rows),
            "captions": len(caption_rows),
            "resolved_lots": len(resolved_rows),
            "unresolved_lots": len(unresolved),
        },
    }


def _pg_get_stream_evidence_timeline_rows(stream_id, limit=120):
    _require_postgres_runtime()
    _ensure_detection_tables_pg()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, created_at, event_type, payload
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE stream_id = %s
                  AND event_type IN ('chat_message', 'auction_winner', 'lot_update')
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (int(stream_id), max(40, int(limit or 120))),
            )
            event_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT id, captured_at, caption_text, confidence, source
                FROM {POSTGRES_SIDECAR_SCHEMA}.stream_caption_windows
                WHERE stream_id = %s
                ORDER BY captured_at DESC, id DESC
                LIMIT %s
                """,
                (int(stream_id), max(20, int(limit or 120) // 2)),
            )
            caption_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT id, captured_at, ocr_text_raw, ocr_confidence, source
                FROM {POSTGRES_SIDECAR_SCHEMA}.stream_ocr_frames
                WHERE stream_id = %s
                ORDER BY captured_at DESC, id DESC
                LIMIT %s
                """,
                (int(stream_id), max(20, int(limit or 120) // 2)),
            )
            ocr_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT id, lot_number, resolved_product_name, resolved_brand, confidence, evidence_summary, resolution_status, resolved_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.resolved_lot_products
                WHERE stream_id = %s
                ORDER BY resolved_at DESC, id DESC
                LIMIT %s
                """,
                (int(stream_id), max(20, int(limit or 120) // 3)),
            )
            resolved_rows = _pg_fetchall_dict(cur)
    return event_rows, caption_rows, ocr_rows, resolved_rows


def get_stream_evidence_timeline(stream_id, db_path=None, limit=120):
    """Return a merged chronological evidence stream for one competitor stream."""
    if db_path:
        event_rows, caption_rows, ocr_rows, resolved_rows = _manual_events_compat_call(
            "get_stream_evidence_timeline",
            stream_id,
            limit=limit,
            db_path=db_path,
        )
    else:
        event_rows, caption_rows, ocr_rows, resolved_rows = _pg_get_stream_evidence_timeline_rows(stream_id, limit=limit)

    rows = []
    for row in event_rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        event_type = row["event_type"]
        if event_type == "chat_message":
            rows.append({
                "kind": "chat",
                "ts": row["created_at"],
                "sort_key": f"{row['created_at']}-{row['id']}",
                "username": _normalize_username(payload.get("username") or payload.get("user")),
                "message": str(payload.get("message") or payload.get("text") or "").strip(),
            })
        elif event_type == "auction_winner":
            rows.append({
                "kind": "winner",
                "ts": row["created_at"],
                "sort_key": f"{row['created_at']}-{row['id']}",
                "lot_number": str(payload.get("lot_number") or payload.get("lot") or "").strip(),
                "winner_username": _normalize_username(payload.get("winner") or payload.get("winner_username") or payload.get("username")),
                "product_name": str(payload.get("product_name") or payload.get("title") or payload.get("item_name") or "").strip(),
                "sale_price": round(_parse_winner_price(payload), 2),
            })
        elif event_type == "lot_update":
            rows.append({
                "kind": "lot",
                "ts": row["created_at"],
                "sort_key": f"{row['created_at']}-{row['id']}",
                "product_name": str(payload.get("product_name") or payload.get("title") or "").strip(),
            })

    for row in caption_rows:
        rows.append({
            "kind": "caption",
            "ts": row["captured_at"],
            "sort_key": f"{row['captured_at']}-cap-{row['id']}",
            "text": str(row["caption_text"] or "").strip(),
            "confidence": float(row["confidence"] or 0),
            "source": row["source"] or "manual",
        })

    for row in ocr_rows:
        rows.append({
            "kind": "ocr",
            "ts": row["captured_at"],
            "sort_key": f"{row['captured_at']}-ocr-{row['id']}",
            "text": str(row["ocr_text_raw"] or "").strip(),
            "confidence": float(row["ocr_confidence"] or 0),
            "source": row["source"] or "manual",
        })

    for row in resolved_rows:
        rows.append({
            "kind": "resolved",
            "ts": row["resolved_at"],
            "sort_key": f"{row['resolved_at']}-res-{row['id']}",
            "lot_number": str(row["lot_number"] or "").strip(),
            "resolved_product_name": str(row["resolved_product_name"] or "").strip(),
            "resolved_brand": str(row["resolved_brand"] or "").strip(),
            "confidence": float(row["confidence"] or 0),
            "resolution_status": row["resolution_status"] or "resolved",
            "evidence_summary": row["evidence_summary"] or "",
        })

    rows = [row for row in rows if row.get("ts")]
    rows.sort(key=lambda row: row["sort_key"], reverse=True)
    return {
        "stream_id": int(stream_id),
        "items": rows[:max(40, int(limit or 120))],
        "totals": {
            "chat": sum(1 for row in rows if row["kind"] == "chat"),
            "winner": sum(1 for row in rows if row["kind"] == "winner"),
            "caption": sum(1 for row in rows if row["kind"] == "caption"),
            "ocr": sum(1 for row in rows if row["kind"] == "ocr"),
            "resolved": sum(1 for row in rows if row["kind"] == "resolved"),
        },
    }


def _clean_match_text(value):
    return re.sub(r"[^a-z0-9\s]+", " ", str(value or "").lower()).strip()


def _product_tokens(value):
    tokens = [tok for tok in re.findall(r"[a-z0-9]{3,}", _clean_match_text(value))]
    return [tok for tok in tokens if tok not in _PRODUCT_TOKEN_STOP_WORDS]


def _looks_generic_product_name(value):
    normalized = _clean_match_text(value)
    if not normalized:
        return True
    for pattern in _GENERIC_TITLE_PATTERNS:
        if re.search(pattern, normalized):
            return True
    return len(normalized) < 12 or len(normalized.split()) < 2


def _infer_lot_number(payload):
    direct = str(
        payload.get("lot_number")
        or payload.get("lot")
        or payload.get("lotNo")
        or ""
    ).strip()
    if direct:
        return direct
    for field in (
        payload.get("product_name"),
        payload.get("title"),
        payload.get("item_name"),
        payload.get("name"),
    ):
        text = str(field or "").strip()
        if not text:
            continue
        match = re.search(r"(?:^|[^\d])#\s*(\d{1,5})(?:\D|$)", text)
        if match:
            return match.group(1)
        match = re.search(r"\blot\s*#?\s*(\d{1,5})\b", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _pg_resolve_stream_sold_products_inputs(stream_id, limit=24):
    _require_postgres_runtime()
    _ensure_detection_tables_pg()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT product_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings
                WHERE stream_id = %s
                  AND scraped_at = (
                    SELECT MAX(scraped_at) FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings WHERE stream_id = %s
                  )
                ORDER BY id ASC
                """,
                (int(stream_id), int(stream_id)),
            )
            listing_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT id, created_at, payload
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE stream_id = %s AND event_type = 'auction_winner'
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (int(stream_id), max(1, int(limit or 24))),
            )
            winner_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT created_at, payload
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE stream_id = %s AND event_type = 'chat_message'
                ORDER BY created_at DESC, id DESC
                LIMIT 4000
                """,
                (int(stream_id),),
            )
            chat_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT captured_at, caption_text, confidence, source
                FROM {POSTGRES_SIDECAR_SCHEMA}.stream_caption_windows
                WHERE stream_id = %s
                ORDER BY captured_at DESC, id DESC
                LIMIT 1500
                """,
                (int(stream_id),),
            )
            caption_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT captured_at, ocr_text_raw, ocr_confidence, source
                FROM {POSTGRES_SIDECAR_SCHEMA}.stream_ocr_frames
                WHERE stream_id = %s
                ORDER BY captured_at DESC, id DESC
                LIMIT 1200
                """,
                (int(stream_id),),
            )
            ocr_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT created_at, payload
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE stream_id = %s AND event_type = 'lot_update'
                ORDER BY created_at DESC, id DESC
                LIMIT 1200
                """,
                (int(stream_id),),
            )
            lot_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"SELECT lot_number FROM {POSTGRES_SIDECAR_SCHEMA}.resolved_lot_products WHERE stream_id = %s",
                (int(stream_id),),
            )
            existing_resolved = {str(row["lot_number"] or "").strip() for row in _pg_fetchall_dict(cur)}
    return listing_rows, winner_rows, chat_rows, caption_rows, ocr_rows, lot_rows, existing_resolved


def resolve_stream_sold_products(stream_id, db_path=None, limit=24, persist=False):
    """Resolve sold competitor lots using a time-window evidence model.

    Sold truth always comes from winner events. Product identification is
    inferred from nearby:
    - lot titles / product hints
    - chat mentions
    - captions / transcript snippets
    - OCR text
    - current competitor catalog snapshot
    """
    if db_path:
        listing_rows, winner_rows, chat_rows, caption_rows, ocr_rows, lot_rows, existing_resolved = _manual_events_compat_call(
            "resolve_stream_sold_products",
            stream_id,
            limit=limit,
            db_path=db_path,
        )
    else:
        listing_rows, winner_rows, chat_rows, caption_rows, ocr_rows, lot_rows, existing_resolved = _pg_resolve_stream_sold_products_inputs(
            stream_id,
            limit=limit,
        )

    candidates = []
    for row in listing_rows:
        name = str(row["product_name"] or "").strip()
        if not name:
            continue
        if _looks_generic_product_name(name):
            continue
        candidates.append({
            "product_name": name,
            "normalized": _clean_match_text(name),
            "tokens": set(_product_tokens(name)),
        })

    parsed_chats = []
    for row in chat_rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        message = str(payload.get("message") or "").strip()
        username = _normalize_username(payload.get("username") or payload.get("user"))
        if not message:
            continue
        parsed_chats.append({
            "created_at": row["created_at"],
            "username": username,
            "message": message,
            "normalized": _clean_match_text(message),
            "tokens": set(_product_tokens(message)),
        })

    parsed_captions = []
    for row in caption_rows:
        text = str(row["caption_text"] or "").strip()
        if not text:
            continue
        parsed_captions.append({
            "captured_at": row["captured_at"],
            "text": text,
            "normalized": _clean_match_text(text),
            "tokens": set(_product_tokens(text)),
            "confidence": float(row["confidence"] or 0),
            "source": row["source"] or "dom_probe",
        })

    parsed_ocr = []
    for row in ocr_rows:
        text = str(row["ocr_text_raw"] or "").strip()
        if not text:
            continue
        parsed_ocr.append({
            "captured_at": row["captured_at"],
            "text": text,
            "normalized": _clean_match_text(text),
            "tokens": set(_product_tokens(text)),
            "confidence": float(row["ocr_confidence"] or 0),
            "source": row["source"] or "rapidocr",
        })

    parsed_lot_updates = []
    for row in lot_rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        title = str(payload.get("product_name") or payload.get("title") or payload.get("item_name") or "").strip()
        if not title:
            continue
        parsed_lot_updates.append({
            "created_at": row["created_at"],
            "title": title,
            "normalized": _clean_match_text(title),
            "tokens": set(_product_tokens(title)),
        })

    def _parse_dt(value):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    suggestions = []
    inserts = []
    for row in winner_rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        lot_number = _infer_lot_number(payload)
        if not lot_number or lot_number in existing_resolved:
            continue
        sold_at = row["created_at"]
        sold_dt = _parse_dt(sold_at)
        product_hint = str(payload.get("product_name") or payload.get("title") or payload.get("item_name") or "").strip()
        winner_username = _normalize_username(payload.get("winner") or payload.get("winner_username") or payload.get("username"))
        sale_price = round(_parse_winner_price(payload), 2)

        nearby_chat = []
        nearby_captions = []
        nearby_ocr = []
        nearby_lot_updates = []
        if sold_dt:
            for chat in parsed_chats:
                chat_dt = _parse_dt(chat["created_at"])
                if not chat_dt:
                    continue
                delta = (sold_dt - chat_dt).total_seconds()
                if -10 <= delta <= 45:
                    nearby_chat.append(chat)
            for caption in parsed_captions:
                caption_dt = _parse_dt(caption["captured_at"])
                if not caption_dt:
                    continue
                delta = (sold_dt - caption_dt).total_seconds()
                if -10 <= delta <= 55:
                    nearby_captions.append(caption)
            for ocr in parsed_ocr:
                ocr_dt = _parse_dt(ocr["captured_at"])
                if not ocr_dt:
                    continue
                delta = (sold_dt - ocr_dt).total_seconds()
                if -10 <= delta <= 55:
                    nearby_ocr.append(ocr)
            for lot in parsed_lot_updates:
                lot_dt = _parse_dt(lot["created_at"])
                if not lot_dt:
                    continue
                delta = (sold_dt - lot_dt).total_seconds()
                if -15 <= delta <= 60:
                    nearby_lot_updates.append(lot)
        else:
            nearby_chat = parsed_chats[:80]
            nearby_captions = parsed_captions[:40]
            nearby_ocr = parsed_ocr[:30]
            nearby_lot_updates = parsed_lot_updates[:20]

        hint_tokens = set(_product_tokens(product_hint))
        hint_normalized = _clean_match_text(product_hint)
        scored = []
        for cand in candidates:
            score = 0.0
            evidence = []
            evidence_payload = {
                "title_examples": [],
                "chat_examples": [],
                "caption_examples": [],
                "ocr_examples": [],
            }
            token_overlap = len(hint_tokens & cand["tokens"]) if hint_tokens else 0
            if token_overlap:
                score += token_overlap * 3.5
                evidence.append(f"hint token overlap {token_overlap}")
            if hint_normalized and not _looks_generic_product_name(product_hint):
                ratio = SequenceMatcher(None, hint_normalized, cand["normalized"]).ratio()
                score += ratio * 8.0
                if ratio >= 0.55:
                    evidence.append(f"title similarity {ratio:.2f}")
                    evidence_payload["title_examples"].append(product_hint)
            title_hits = 0
            for lot in nearby_lot_updates:
                overlap = cand["tokens"] & lot["tokens"]
                if overlap:
                    title_hits += len(overlap)
                    if len(evidence_payload["title_examples"]) < 3:
                        evidence_payload["title_examples"].append(lot["title"])
                elif lot["normalized"] and not _looks_generic_product_name(lot["title"]):
                    ratio = SequenceMatcher(None, lot["normalized"], cand["normalized"]).ratio()
                    if ratio >= 0.68:
                        title_hits += max(1, int(round(ratio * 2)))
                        if len(evidence_payload["title_examples"]) < 3:
                            evidence_payload["title_examples"].append(lot["title"])
            if title_hits:
                score += min(title_hits, 8) * 2.2
                evidence.append(f"lot title hits {title_hits}")
            chat_hits = 0
            chat_unique = set()
            for chat in nearby_chat:
                overlap = cand["tokens"] & chat["tokens"]
                if overlap:
                    chat_dt = _parse_dt(chat["created_at"])
                    delta = abs((sold_dt - chat_dt).total_seconds()) if sold_dt and chat_dt else 15
                    weight = max(0.4, 1.0 - min(delta, 45) / 60.0)
                    chat_hits += len(overlap) * weight
                    chat_unique.add(chat["normalized"])
                    if len(evidence_payload["chat_examples"]) < 3:
                        evidence_payload["chat_examples"].append(chat["message"])
            if chat_hits:
                score += min(chat_hits, 6) * 2.1
                evidence.append(f"chat token hits {chat_hits:.1f}")
            caption_hits = 0
            caption_unique = set()
            for caption in nearby_captions:
                overlap = cand["tokens"] & caption["tokens"]
                if overlap:
                    caption_dt = _parse_dt(caption["captured_at"])
                    delta = abs((sold_dt - caption_dt).total_seconds()) if sold_dt and caption_dt else 15
                    proximity = max(0.5, 1.0 - min(delta, 55) / 70.0)
                    weight = max(1.0, float(caption["confidence"] or 0.6) * 2.0) * proximity
                    caption_hits += len(overlap) * weight
                    caption_unique.add(caption["normalized"])
                    if len(evidence_payload["caption_examples"]) < 3:
                        evidence_payload["caption_examples"].append(caption["text"])
            if caption_hits:
                score += min(caption_hits, 10) * 3.0
                evidence.append(f"caption token hits {caption_hits:.1f}")
            ocr_hits = 0
            ocr_unique = set()
            for ocr in nearby_ocr:
                overlap = cand["tokens"] & ocr["tokens"]
                if overlap:
                    ocr_dt = _parse_dt(ocr["captured_at"])
                    delta = abs((sold_dt - ocr_dt).total_seconds()) if sold_dt and ocr_dt else 15
                    proximity = max(0.5, 1.0 - min(delta, 55) / 70.0)
                    weight = max(1.0, float(ocr["confidence"] or 0.55) * 2.2) * proximity
                    ocr_hits += len(overlap) * weight
                    ocr_unique.add(ocr["normalized"])
                    if len(evidence_payload["ocr_examples"]) < 3:
                        evidence_payload["ocr_examples"].append(ocr["text"])
                elif ocr["normalized"]:
                    ratio = SequenceMatcher(None, ocr["normalized"], cand["normalized"]).ratio()
                    if ratio >= 0.72:
                        ocr_dt = _parse_dt(ocr["captured_at"])
                        delta = abs((sold_dt - ocr_dt).total_seconds()) if sold_dt and ocr_dt else 15
                        proximity = max(0.5, 1.0 - min(delta, 55) / 70.0)
                        ocr_hits += ratio * max(1.0, float(ocr["confidence"] or 0.55) * 2.0) * proximity
                        ocr_unique.add(ocr["normalized"])
                        if len(evidence_payload["ocr_examples"]) < 3:
                            evidence_payload["ocr_examples"].append(ocr["text"])
            if ocr_hits:
                score += min(ocr_hits, 12) * 3.2
                evidence.append(f"ocr hits {ocr_hits:.1f}")
            if score <= 0:
                continue
            evidence_strength = {
                "title": title_hits,
                "chat": chat_hits,
                "caption": caption_hits,
                "ocr": ocr_hits,
                "chat_unique": len(chat_unique),
                "caption_unique": len(caption_unique),
                "ocr_unique": len(ocr_unique),
            }
            scored.append({
                "candidate": cand["product_name"],
                "score": round(score, 2),
                "evidence": evidence,
                "evidence_payload": evidence_payload,
                "evidence_strength": evidence_strength,
            })

        scored.sort(key=lambda item: (-item["score"], item["candidate"]))
        best = scored[0] if scored else None
        confidence = 0.0
        if best:
            second_score = float(scored[1]["score"]) if len(scored) > 1 else 0.0
            margin = float(best["score"]) - second_score
            strength = best.get("evidence_strength") or {}
            evidence_types = sum(1 for key in ("title", "chat", "caption", "ocr") if float(strength.get(key) or 0) > 0)
            confidence = min(0.97, round(best["score"] / 24.0, 2))
            if evidence_types == 1 and float(strength.get("chat") or 0) > 0:
                confidence = max(0.0, confidence - 0.22)
            if float(strength.get("chat_unique") or 0) <= 1 and evidence_types == 1:
                confidence = max(0.0, confidence - 0.12)
            if margin < 2.5:
                confidence = max(0.0, confidence - 0.12)
            if not any(float(strength.get(key) or 0) > 0 for key in ("title", "caption", "ocr")) and float(strength.get("chat") or 0) < 4.5:
                confidence = max(0.0, confidence - 0.18)
        suggestion = {
            "lot_number": lot_number,
            "winner_username": winner_username,
            "sale_price": sale_price,
            "sold_at": sold_at,
            "product_hint": product_hint,
            "suggested_product_name": best["candidate"] if best else "",
            "confidence": confidence,
            "evidence_summary": "; ".join(best["evidence"]) if best else "No strong catalog/chat match yet.",
            "title_examples": best["evidence_payload"]["title_examples"] if best else [],
            "chat_examples": best["evidence_payload"]["chat_examples"] if best else [],
            "caption_examples": best["evidence_payload"]["caption_examples"] if best else [],
            "ocr_examples": best["evidence_payload"]["ocr_examples"] if best else [],
            "status": "suggested" if best and confidence >= 0.58 else "unresolved",
        }
        suggestions.append(suggestion)
        if persist and best and confidence >= 0.6:
            inserts.append((
                int(stream_id),
                lot_number,
                int(row["id"]),
                best["candidate"],
                "",
                float(confidence),
                suggestion["evidence_summary"],
                "resolved",
                datetime.now(timezone.utc).isoformat(),
            ))

    if persist and inserts and not db_path:
        _require_postgres_runtime(db_path=db_path)
        _ensure_detection_tables_pg()
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.resolved_lot_products
                        (stream_id, lot_number, winner_event_id, resolved_product_name, resolved_brand, confidence, evidence_summary, resolution_status, resolved_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (stream_id, lot_number) DO UPDATE SET
                        winner_event_id = EXCLUDED.winner_event_id,
                        resolved_product_name = EXCLUDED.resolved_product_name,
                        resolved_brand = EXCLUDED.resolved_brand,
                        confidence = EXCLUDED.confidence,
                        evidence_summary = EXCLUDED.evidence_summary,
                        resolution_status = EXCLUDED.resolution_status,
                        resolved_at = EXCLUDED.resolved_at
                    """,
                    inserts,
                )
            conn.commit()

    return {
        "stream_id": int(stream_id),
        "suggestions": suggestions,
        "candidate_count": len(candidates),
        "resolved_candidate_count": sum(1 for item in suggestions if item["status"] == "suggested"),
    }


def backfill_users_and_lots(stream_id=None, db_path=None):
    """Backfill users and lots tables from existing events.

    Runs on all streams unless stream_id is given.
    Safe to run multiple times — uses INSERT OR IGNORE and UPDATE only if winner not set.
    """
    if db_path:
        raise RuntimeError("events_db_sqlite_runtime_retired")

    use_cutover_users = True
    use_cutover_lots = True
    _require_postgres_runtime(db_path=db_path)
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if stream_id:
                cur.execute(
                    f"SELECT stream_id, event_type, payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = %s ORDER BY id ASC",
                    (stream_id,),
                )
            else:
                cur.execute(
                    f"SELECT stream_id, event_type, payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events ORDER BY id ASC"
                )
            rows = cur.fetchall()
    conn = None
    current_lot_id_by_stream = {}

    for sid, event_type, raw_payload, created_at in rows:
        try:
            p = json.loads(raw_payload or "{}")
        except Exception:
            continue

        if event_type == "chat_message":
            u = p.get("username") or p.get("user") or ""
            if u:
                if use_cutover_users:
                    from .ingest_cutover import upsert_ingest_user
                    upsert_ingest_user(u)

        elif event_type == "lot_update":
            lot_number = p.get("lot_number") or ""
            product_name = p.get("product_name") or ""
            if use_cutover_lots:
                from .ingest_cutover import upsert_ingest_lot_open
                lot_id = upsert_ingest_lot_open(sid, lot_number, product_name, created_at)
                if lot_id:
                    current_lot_id_by_stream[sid] = int(lot_id)

        elif event_type == "auction_winner":
            u = p.get("winner") or p.get("winner_username") or p.get("username") or ""
            if u:
                if use_cutover_users:
                    from .ingest_cutover import upsert_ingest_user
                    upsert_ingest_user(u)
            price = _parse_winner_price(p)
            lot_db_id = current_lot_id_by_stream.get(sid)
            if lot_db_id and u and use_cutover_lots:
                from .ingest_cutover import close_ingest_lot
                close_ingest_lot(lot_db_id, u, price, created_at)
                current_lot_id_by_stream.pop(sid, None)

    by_stream = defaultdict(list)
    for sid, event_type, raw_payload, created_at in rows:
        by_stream[sid].append((event_type, raw_payload, created_at))

    for sid, event_rows in by_stream.items():
        for sold in _reconstruct_sold_lots(event_rows):
            from .ingest_cutover import upsert_reconstructed_ingest_lot
            upsert_reconstructed_ingest_lot(
                sid,
                str(sold.get("lot") or "").strip() or None,
                (sold.get("product") or "").strip() or None,
                sold.get("opened_at") or sold.get("time"),
                sold.get("time"),
                (sold.get("username") or "").strip() or None,
                float(sold.get("price") or 0) or None,
            )


def save_failed_ingest(event_id, winner_username, sale_price, lot_number, sold_at, error_message, db_path=None):
    """Record a winner event that failed to ingest into company records."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    if db_path:
        _manual_events_compat_call(
            "save_failed_ingest",
            event_id,
            winner_username,
            sale_price,
            lot_number,
            sold_at,
            error_message,
            created_at=now,
            db_path=db_path,
        )
        return
    _require_postgres_runtime(db_path=db_path)
    from .ingest_cutover import create_failed_ingest
    create_failed_ingest(
        event_id,
        winner_username,
        sale_price,
        lot_number,
        sold_at,
        error_message,
        created_at=now,
    )


def get_failed_ingests(include_resolved=False, db_path=None):
    """Return all failed ingest records, newest first."""
    if db_path:
        rows = _manual_events_compat_call(
            "get_failed_ingests",
            include_resolved=include_resolved,
            db_path=db_path,
        )
    else:
        _require_postgres_runtime(db_path=db_path)
        ensure_wave1_postgres_schema()
        clause = "" if include_resolved else "WHERE COALESCE(resolved, 0) = 0"
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, event_id, source_event_id, winner_username, sale_price, lot_number,
                           sold_at, error_message, retry_count, created_at, last_retry_at, resolved
                    FROM {POSTGRES_SIDECAR_SCHEMA}.failed_ingests {clause}
                    ORDER BY id DESC
                    """
                )
                rows = cur.fetchall()
    MAX_RETRIES = 5
    return [
        {
            "id": r[0], "event_id": r[1], "source_event_id": r[2],
            "winner_username": r[3], "sale_price": r[4], "lot_number": r[5],
            "sold_at": r[6], "error_message": r[7], "retry_count": r[8],
            "created_at": r[9], "last_retry_at": r[10], "resolved": bool(r[11]),
            "needs_review": r[8] >= MAX_RETRIES,
        }
        for r in rows
    ]


def mark_failed_ingest_resolved(failed_id, db_path=None):
    """Mark a failed ingest as resolved (manually or after successful retry)."""
    if db_path:
        _manual_events_compat_call("mark_failed_ingest_resolved", failed_id, db_path=db_path)
        return
    _require_postgres_runtime(db_path=db_path)
    from .ingest_cutover import resolve_failed_ingest
    resolve_failed_ingest(failed_id)


def increment_retry_count(failed_id, error_message=None, db_path=None):
    """Increment retry count and update last_retry_at timestamp."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    if db_path:
        _manual_events_compat_call(
            "increment_retry_count",
            failed_id,
            error_message=error_message,
            last_retry_at=now,
            db_path=db_path,
        )
        return
    _require_postgres_runtime(db_path=db_path)
    from .ingest_cutover import increment_failed_ingest_retry
    increment_failed_ingest_retry(failed_id, error_message=error_message, last_retry_at=now)


def get_collector_health(stream_id=None, db_path=None):
    """Return health metrics for the collector: last event timestamps by type."""
    if db_path:
        return _manual_events_compat_call("get_collector_health", stream_id=stream_id, db_path=db_path)
    _require_postgres_runtime(db_path=db_path)
    return _pg_get_collector_health(stream_id=stream_id)


def _parse_iso_utc(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_generic_product_name(name):
    text = str(name or "").strip().lower()
    if not text:
        return True
    for pattern in _GENERIC_TITLE_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def _stream_health_snapshot(stream_id, db_path=None, raw=None):
    raw = raw if raw is not None else get_collector_health(stream_id=stream_id, db_path=db_path)
    now = datetime.now(timezone.utc)
    freshness = {}
    for key, value in raw.items():
        if key not in {"chat_message", "lot_update", "bid_update", "auction_winner", "live_viewers", "last_event_at"}:
            continue
        dt = _parse_iso_utc(value)
        freshness[key] = None if not dt else max(0, round((now - dt).total_seconds(), 1))

    last_event_age = freshness.get("last_event_at")
    if last_event_age is None:
        status = "offline"
    elif last_event_age <= 75:
        status = "healthy"
    elif last_event_age <= 240:
        status = "degraded"
    else:
        status = "stalled"

    return {
        "status": status,
        "last_event_age_sec": last_event_age,
        "last_chat_age_sec": freshness.get("chat_message"),
        "last_winner_age_sec": freshness.get("auction_winner"),
        "last_bid_age_sec": freshness.get("bid_update"),
        "last_lot_age_sec": freshness.get("lot_update"),
        "last_viewer_age_sec": freshness.get("live_viewers"),
        "raw": raw,
    }


def _lot_confidence(row):
    score = 0.1
    reasons = []
    source_text = str(row.get("source") or "")
    if "auction_winner" in source_text:
        score += 0.42
        reasons.append("winner signal")
    if "lot_update" in source_text:
        score += 0.16
        reasons.append("lot signal")
    if "bid_update" in source_text:
        score += 0.12
        reasons.append("bid signal")
    if row.get("username"):
        score += 0.10
        reasons.append("winner username")
    if float(row.get("price") or 0) > 0:
        score += 0.10
        reasons.append("sale price")
    if row.get("product") and not _is_generic_product_name(row.get("product")):
        score += 0.12
        reasons.append("specific product")
    elif row.get("product"):
        score -= 0.06
        reasons.append("generic product title")
    else:
        score -= 0.10
        reasons.append("missing product")
    if row.get("lot"):
        score += 0.06
        reasons.append("lot number")
    else:
        score -= 0.14
        reasons.append("missing lot number")
    score = max(0.0, min(0.99, round(score, 2)))
    label = "high" if score >= 0.8 else "medium" if score >= 0.55 else "low"
    return score, label, reasons


def _compute_stream_reconciled_state(rows, stream_id, db_path=None, limit=50, health_raw=None):
    sold_lots = _reconstruct_sold_lots(_stream_timeline_rows(rows))
    health = _stream_health_snapshot(stream_id, db_path=db_path, raw=health_raw)

    canonical_lots = []
    duplicate_winner_keys = defaultdict(int)
    generic_titles = 0
    winner_without_price = 0
    missing_product = 0

    for idx, lot in enumerate(sold_lots):
        score, label, reasons = _lot_confidence(lot)
        lot_number = str(lot.get("lot") or "").strip()
        username = str(lot.get("username") or "").strip()
        price = round(float(lot.get("price") or 0), 2)
        product = str(lot.get("product") or "").strip()

        if _is_generic_product_name(product):
            generic_titles += 1
        if username and price <= 0:
            winner_without_price += 1
        if not product:
            missing_product += 1

        if username or price or lot_number:
            duplicate_winner_keys[(lot_number, username.lower(), price)] += 1

        canonical_lots.append({
            "index": idx + 1,
            "lot_number": lot_number,
            "product_name": product,
            "winner_username": username,
            "sale_price": price,
            "sold_at": lot.get("time"),
            "source": lot.get("source") or "",
            "reason": lot.get("reason") or "",
            "confidence_score": score,
            "confidence": label,
            "confidence_reasons": reasons,
            "generic_title": _is_generic_product_name(product),
        })

    active_lot = None
    for row in rows:
        event_type = row[1]
        try:
            payload = json.loads(row[2] or "{}")
        except Exception:
            payload = {}
        if event_type == "lot_update":
            active_lot = {
                "lot_number": str(payload.get("lot_number") or "").strip(),
                "product_name": (payload.get("product_name") or payload.get("title") or payload.get("item_name") or "").strip(),
                "updated_at": row[3],
            }
        elif event_type == "auction_winner" and active_lot:
            winner_lot = str(payload.get("lot_number") or payload.get("lot") or "").strip()
            if not winner_lot or winner_lot == active_lot.get("lot_number"):
                active_lot = None
        elif event_type == "auction_state" and active_lot:
            state = str(payload.get("state") or "").strip().lower()
            if state in {"awaiting_next_item", "shipping_shown"}:
                active_lot = None

    duplicate_winner_signals = sum(max(0, count - 1) for count in duplicate_winner_keys.values())
    anomaly_counts = {
        "duplicate_winner_signals": duplicate_winner_signals,
        "winner_without_price": winner_without_price,
        "generic_product_titles": generic_titles,
        "missing_product_name": missing_product,
        "low_confidence_lots": sum(1 for row in canonical_lots if row["confidence"] == "low"),
    }
    anomaly_counts["needs_review"] = (
        anomaly_counts["duplicate_winner_signals"] > 0
        or anomaly_counts["winner_without_price"] > 0
        or anomaly_counts["low_confidence_lots"] >= 3
        or health["status"] in {"degraded", "stalled"}
    )

    return {
        "stream_id": int(stream_id),
        "health": health,
        "active_lot": active_lot,
        "summary": {
            "canonical_lots": len(canonical_lots),
            "revenue": round(sum(row["sale_price"] for row in canonical_lots), 2),
            "avg_confidence": round(sum(row["confidence_score"] for row in canonical_lots) / len(canonical_lots), 2) if canonical_lots else 0.0,
            "high_confidence_lots": sum(1 for row in canonical_lots if row["confidence"] == "high"),
            "medium_confidence_lots": sum(1 for row in canonical_lots if row["confidence"] == "medium"),
            "low_confidence_lots": sum(1 for row in canonical_lots if row["confidence"] == "low"),
        },
        "anomalies": anomaly_counts,
        "lots": canonical_lots[-max(1, int(limit)):],
    }


def _pg_get_stream_reconciled_state(stream_id, limit=50):
    postgres_rows = _pg_get_stream_event_rows(stream_id)
    postgres_health = _pg_get_collector_health(stream_id=stream_id)
    return _compute_stream_reconciled_state(
        postgres_rows,
        stream_id,
        limit=limit,
        health_raw=postgres_health,
    )


def get_stream_reconciled_state(stream_id, db_path=None, limit=50):
    """Return canonical lot records plus health/anomaly scoring for a stream."""
    _require_postgres_runtime(db_path=db_path)
    backfill_users_and_lots(stream_id=stream_id, db_path=db_path)
    if db_path:
        return _manual_events_compat_call(
            "get_stream_reconciled_state",
            stream_id,
            limit=limit,
            db_path=db_path,
        )

    return _pg_get_stream_reconciled_state(stream_id, limit=limit)


def _compute_spectator_insights(rows, stream_id, db_path=None):
    """
    Aggregate insights for a given stream_id from the events table:
      - total_revenue, lots_sold
      - top_buyers: [{username, lots_won, total_spent}]
      - products_sold: [{product, lot, price, buyer, time}]
      - top_chatters: [{username, message_count}]
      - chat_sample: last 50 messages
    """
    chatter_counts = {}
    chat_sample = []
    timeline_rows = _stream_timeline_rows(rows)
    winners = _reconstruct_sold_lots(timeline_rows)
    raw_winner_events = 0
    raw_winner_keys = []

    for event_type, raw_payload, created_at in timeline_rows:
        try:
            p = json.loads(raw_payload or "{}")
        except Exception:
            p = {}

        if event_type == "chat_message":
            username = p.get("username") or p.get("user") or "anon"
            message = p.get("message") or p.get("text") or ""
            chatter_counts[username] = chatter_counts.get(username, 0) + 1
            chat_sample.append({"username": username, "message": message, "time": created_at})
        elif event_type == "auction_winner":
            raw_winner_events += 1
            raw_winner_keys.append((
                str(p.get("lot_number") or "").strip(),
                str(p.get("winner") or p.get("winner_username") or p.get("username") or "").strip().lower(),
                round(float(_parse_winner_price(p) or 0), 2),
            ))

    duplicate_winner_signals = 0
    winner_key_counts = defaultdict(int)
    for key in raw_winner_keys:
        if not any(key):
            continue
        winner_key_counts[key] += 1
    for count in winner_key_counts.values():
        if count > 1:
            duplicate_winner_signals += count - 1

    # Aggregate top buyers
    buyer_map = {}
    for w in winners:
        u = w["username"]
        if u not in buyer_map:
            buyer_map[u] = {"username": u, "lots_won": 0, "total_spent": 0.0}
        buyer_map[u]["lots_won"] += 1
        buyer_map[u]["total_spent"] = round(buyer_map[u]["total_spent"] + w["price"], 2)
    top_buyers = sorted(buyer_map.values(), key=lambda x: x["total_spent"], reverse=True)[:20]

    top_chatters = sorted(
        [{"username": u, "message_count": c} for u, c in chatter_counts.items()],
        key=lambda x: x["message_count"],
        reverse=True,
    )[:20]

    summary = _compute_stream_event_summary(rows, stream_id)
    unique_buyers = len(buyer_map)

    return {
        "stream_id": stream_id,
        "total_revenue": round(sum(w["price"] for w in winners), 2),
        "lots_sold": len(winners),
        "unique_buyers": unique_buyers,
        "avg_sale_price": round(sum(w["price"] for w in winners) / len(winners), 2) if winners else 0.0,
        "top_buyers": top_buyers,
        "products_sold": winners[-500:],  # last 500 items sold
        "top_chatters": top_chatters,
        "chat_sample": chat_sample[-250:],
        "total_chatters": len(chatter_counts),
        "total_messages": sum(chatter_counts.values()),
        "collection_summary": summary,
        "integrity": {
            "raw_winner_events": raw_winner_events,
            "reconstructed_lots": len(winners),
            "duplicate_winner_signals": duplicate_winner_signals,
            "winner_gap": max(0, len(winners) - raw_winner_events),
            "needs_review": abs(len(winners) - raw_winner_events) >= 3 or duplicate_winner_signals >= 2,
        },
    }


def _pg_get_spectator_insights(stream_id):
    postgres_rows = _pg_get_stream_event_rows(stream_id)
    return _compute_spectator_insights(postgres_rows, stream_id)


def get_spectator_insights(stream_id, db_path=None):
    """
    Aggregate insights for a given stream_id from the events table.
    """
    _require_postgres_runtime(db_path=db_path)
    backfill_users_and_lots(stream_id=stream_id, db_path=db_path)
    if db_path:
        return _manual_events_compat_call("get_spectator_insights", stream_id, db_path=db_path)

    return _pg_get_spectator_insights(stream_id)


def _pg_get_company_stream_history(account_name="ynfdeals", limit=15):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT cs.id, cs.stream_id, cs.name, cs.status, cs.started_at, cs.ended_at,
                       cs.total_revenue, cs.total_cost, cs.total_fees, cs.total_profit,
                       cs.total_products_sold, cs.total_lots_sold,
                       s.title, s.streamer_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = cs.stream_id
                WHERE LOWER(cs.whatnot_account) = %s
                ORDER BY cs.started_at DESC, cs.id DESC
                LIMIT %s
                """,
                (account_name.lower(), int(limit)),
            )
            rows = cur.fetchall()
    sessions = []
    for row in rows:
        display_name = row[12] or row[2] or f"{account_name} stream"
        sessions.append({
            "id": row[0],
            "stream_id": row[1],
            "name": display_name,
            "status": row[3] or "ended",
            "start_time": row[4],
            "end_time": row[5],
            "total_revenue": row[6] or 0,
            "total_cost": row[7] or 0,
            "total_fees": row[8] or 0,
            "total_profit": row[9] or 0,
            "total_products_sold": row[10] or 0,
            "total_lots_sold": row[11] or 0,
            "streamer_name": row[13] or account_name,
        })
    return sessions


def get_company_stream_history(account_name="ynfdeals", limit=15, db_path=None):
    """Return history from company_sessions (source of truth for our streams).

    Falls back to stream title from the streams table for display names.
    """
    if db_path:
        return _manual_events_compat_call(
            "get_company_stream_history",
            account_name=account_name,
            limit=limit,
            db_path=db_path,
        )

    return _pg_get_company_stream_history(account_name=account_name, limit=limit)


def _pg_get_company_stream_detail(stream_id):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions WHERE id = %s",
                (int(stream_id),),
            )
            session_row = cur.fetchone()
            if not session_row:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions WHERE stream_id = %s ORDER BY id DESC LIMIT 1",
                    (int(stream_id),),
                )
                session_row = cur.fetchone()
            if not session_row:
                return None
            session_columns = [desc[0] for desc in cur.description]
            session = dict(zip(session_columns, session_row))
            sid = session["id"]
            cur.execute(
                f"""SELECT sold_at, winner_username, product_name, lot_number,
                           sale_price, fees, cost_price, profit, margin_pct
                    FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results
                    WHERE session_id = %s
                    ORDER BY sold_at ASC""",
                (sid,),
            )
            ar_rows = cur.fetchall()
    winners = []
    product_map = defaultdict(lambda: {"product_name": "", "times_sold": 0, "total_revenue": 0.0})
    buyer_map = defaultdict(lambda: {"buyer_username": "", "total_lots": 0, "total_revenue": 0.0})
    for ar in ar_rows:
        pname = ar[2] or "(no scan)"
        uname = ar[1] or ""
        price = float(ar[4] or 0)
        winners.append({
            "sold_at": ar[0],
            "winner_username": uname,
            "product_name": pname,
            "lot_number": ar[3] or "",
            "sale_price": round(price, 2),
            "fees": round(float(ar[5] or 0), 2),
            "profit": round(float(ar[7] or 0), 2),
        })
        rec = product_map[pname]
        rec["product_name"] = pname
        rec["times_sold"] += 1
        rec["total_revenue"] = round(rec["total_revenue"] + price, 2)
        buyer = buyer_map[uname]
        buyer["buyer_username"] = uname
        buyer["total_lots"] += 1
        buyer["total_revenue"] = round(buyer["total_revenue"] + price, 2)
    return {
        "winners": winners,
        "products": sorted(product_map.values(), key=lambda r: r["total_revenue"], reverse=True),
        "buyers": sorted(buyer_map.values(), key=lambda r: r["total_revenue"], reverse=True),
        "total_revenue": session.get("total_revenue") or 0,
        "total_cost": session.get("total_cost") or 0,
        "total_fees": session.get("total_fees") or 0,
        "total_profit": session.get("total_profit") or 0,
        "lots_sold": session.get("total_lots_sold") or 0,
        "total_messages": 0,
    }


def get_company_stream_detail(stream_id, db_path=None):
    """Return winner/product/buyer breakdown for a company stream.

    stream_id here is actually the company_session.id passed from the history view.
    We try company_session first; if not found, fall back to spectator insights.
    """
    if db_path:
        sqlite_value = _manual_events_compat_call("get_company_stream_detail", stream_id, db_path=db_path)
        if sqlite_value is not None:
            return sqlite_value
    else:
        postgres_value = _pg_get_company_stream_detail(stream_id)
        if postgres_value is not None:
            return postgres_value

    insights = get_spectator_insights(stream_id, db_path=db_path)
    winners = []
    product_map = defaultdict(lambda: {"product_name": "", "times_sold": 0, "total_revenue": 0.0})
    buyer_map = defaultdict(lambda: {"buyer_username": "", "total_lots": 0, "total_revenue": 0.0})
    for item in insights.get("products_sold", []):
        product_name = item.get("product") or "(no scan)"
        buyer_username = item.get("username") or ""
        price = float(item.get("price") or 0)
        lot_number = item.get("lot") or ""
        sold_at = item.get("time")
        winners.append({
            "sold_at": sold_at, "winner_username": buyer_username,
            "product_name": product_name, "lot_number": lot_number,
            "sale_price": round(price, 2), "fees": None, "profit": None,
        })
        rec = product_map[product_name]
        rec["product_name"] = product_name
        rec["times_sold"] += 1
        rec["total_revenue"] = round(rec["total_revenue"] + price, 2)
        buyer = buyer_map[buyer_username]
        buyer["buyer_username"] = buyer_username
        buyer["total_lots"] += 1
        buyer["total_revenue"] = round(buyer["total_revenue"] + price, 2)
    products = sorted(product_map.values(), key=lambda row: row["total_revenue"], reverse=True)
    buyers = sorted(buyer_map.values(), key=lambda row: row["total_revenue"], reverse=True)
    return {
        "winners": winners, "products": products, "buyers": buyers,
        "total_revenue": insights.get("total_revenue") or 0,
        "lots_sold": insights.get("lots_sold") or 0,
        "total_messages": insights.get("total_messages") or 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Competitor multi-session analytics
# ─────────────────────────────────────────────────────────────────────────────

def _pg_get_analytics_trends(streamer_name, our_stream_urls=None, our_streamer_names=None):
    _require_postgres_runtime()
    excluded = _our_stream_ids_pg(our_stream_urls, our_streamer_names)
    if streamer_name.lower() in _OUR_STREAMER_NAMES:
        return {"sessions": [], "schedule": {"by_day": [], "by_hour": [], "avg_duration_minutes": None, "avg_revenue_per_hour": None, "total_sessions": 0}}
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, started_at, ended_at FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE LOWER(streamer_name)=%s ORDER BY started_at ASC",
                (streamer_name.lower(),),
            )
            stream_rows = cur.fetchall()

    sessions = []
    for stream_id, started_at, ended_at in stream_rows:
        if stream_id in excluded:
            continue
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT payload FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id=%s AND event_type='auction_winner'",
                    (stream_id,),
                )
                winner_rows = cur.fetchall()
                cur.execute(
                    f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id=%s AND event_type='chat_message'",
                    (stream_id,),
                )
                chat_count = cur.fetchone()[0]

        revenue = 0.0
        buyers = set()
        prices = []
        for row in winner_rows:
            try:
                p = json.loads(row[0] or "{}")
                price = _parse_winner_price(p)
                username = (p.get("winner") or p.get("winner_username") or "").strip().lower()
                if price > 0:
                    revenue += price
                    prices.append(price)
                if username:
                    buyers.add(username)
            except Exception:
                pass

        duration_min = None
        if started_at and ended_at:
            try:
                s = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                e = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                duration_min = max(1, round((e - s).total_seconds() / 60))
            except Exception:
                pass

        rev_per_hour = round(revenue / (duration_min / 60), 2) if duration_min else None
        avg_price = round(revenue / len(prices), 2) if prices else 0.0
        sessions.append({
            "stream_id": stream_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "revenue": round(revenue, 2),
            "lots_sold": len(prices),
            "unique_buyers": len(buyers),
            "avg_price": avg_price,
            "chat_messages": chat_count,
            "duration_minutes": duration_min,
            "revenue_per_hour": rev_per_hour,
        })

    DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_rev = defaultdict(list)
    hour_rev = defaultdict(list)
    durations = []
    rph_list = []
    for s in sessions:
        if s["started_at"]:
            try:
                dt = datetime.fromisoformat(s["started_at"].replace("Z", "+00:00"))
                day_rev[dt.weekday()].append(s["revenue"])
                hour_rev[dt.hour].append(s["revenue"])
            except Exception:
                pass
        if s["duration_minutes"]:
            durations.append(s["duration_minutes"])
        if s["revenue_per_hour"]:
            rph_list.append(s["revenue_per_hour"])
    by_day = [
        {"day": DAYS[i], "count": len(day_rev[i]), "avg_revenue": round(sum(day_rev[i]) / len(day_rev[i]), 2) if day_rev[i] else 0, "total_revenue": round(sum(day_rev[i]), 2)}
        for i in range(7)
    ]
    by_hour = [
        {"hour": i, "count": len(hour_rev[i]), "avg_revenue": round(sum(hour_rev[i]) / len(hour_rev[i]), 2) if hour_rev[i] else 0}
        for i in range(24)
    ]
    return {
        "sessions": sessions,
        "schedule": {
            "by_day": by_day,
            "by_hour": by_hour,
            "avg_duration_minutes": round(sum(durations) / len(durations)) if durations else None,
            "avg_revenue_per_hour": round(sum(rph_list) / len(rph_list), 2) if rph_list else None,
            "total_sessions": len(sessions),
        },
    }


def get_analytics_trends(streamer_name, our_stream_urls=None, our_streamer_names=None, db_path=None):
    """
    Per-session performance timeline for a competitor.

    Returns list of sessions (oldest first) each with:
      revenue, lots_sold, unique_buyers, avg_price, duration_minutes,
      revenue_per_hour, chat_messages, started_at, ended_at
    Also returns schedule breakdown:
      by_day  — [{day, count, avg_revenue}] for Mon-Sun
      by_hour — [{hour, count, avg_revenue}] for 0-23 (UTC)
      avg_duration_minutes, avg_revenue_per_hour, total_sessions
    """
    if db_path:
        return _manual_events_compat_call(
            "get_analytics_trends",
            streamer_name,
            our_stream_urls=our_stream_urls,
            our_streamer_names=our_streamer_names,
            db_path=db_path,
        )

    return _pg_get_analytics_trends(
        streamer_name,
        our_stream_urls=our_stream_urls,
        our_streamer_names=our_streamer_names,
    )


def _pg_get_analytics_buyer_overlap(streamer_name, our_stream_urls=None, our_streamer_names=None):
    _require_postgres_runtime()
    excluded = _our_stream_ids_pg(our_stream_urls, our_streamer_names)
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE LOWER(streamer_name)=%s",
                (streamer_name.lower(),),
            )
            comp_ids = [row[0] for row in cur.fetchall() if row[0] not in excluded]
            if not comp_ids:
                return []
            comp_spend = defaultdict(float)
            comp_lots = defaultdict(int)
            cur.execute(
                f"SELECT payload FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = ANY(%s) AND event_type='auction_winner'",
                (comp_ids,),
            )
            for row in cur.fetchall():
                try:
                    p = json.loads(row[0] or "{}")
                    username = (p.get("winner") or p.get("winner_username") or "").strip().lower()
                    price = _parse_winner_price(p)
                    if username:
                        comp_spend[username] += price
                        comp_lots[username] += 1
                except Exception:
                    pass
            if not comp_spend:
                return []
            our_ids = list(excluded)
            if not our_ids:
                return []
            our_chat = defaultdict(int)
            cur.execute(
                f"SELECT payload FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = ANY(%s) AND event_type='chat_message'",
                (our_ids,),
            )
            for row in cur.fetchall():
                try:
                    p = json.loads(row[0] or "{}")
                    username = (p.get("username") or p.get("user") or "").strip().lower()
                    if username:
                        our_chat[username] += 1
                except Exception:
                    pass
    overlap = []
    for username, spent in comp_spend.items():
        if username in our_chat:
            overlap.append({
                "username": username,
                "comp_spent": round(spent, 2),
                "comp_lots": comp_lots[username],
                "our_chat_count": our_chat[username],
                "tier": "whale" if spent >= 500 else "heavy" if spent >= 100 else "regular",
            })
    return sorted(overlap, key=lambda x: x["comp_spent"], reverse=True)


def get_analytics_buyer_overlap(streamer_name, our_stream_urls=None, our_streamer_names=None, db_path=None):
    """
    Find buyers who spent money on a competitor AND appeared in our own chat.

    Returns list of overlapping users sorted by competitor spend:
      username, comp_spent, comp_lots, our_chat_count, tier
    """
    if db_path:
        return _manual_events_compat_call(
            "get_analytics_buyer_overlap",
            streamer_name,
            our_stream_urls=our_stream_urls,
            our_streamer_names=our_streamer_names,
            db_path=db_path,
        )

    return _pg_get_analytics_buyer_overlap(
        streamer_name,
        our_stream_urls=our_stream_urls,
        our_streamer_names=our_streamer_names,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Analytics: Chat Signals
# ─────────────────────────────────────────────────────────────────────────────

_CHAT_STOP_WORDS = {
    "the", "and", "for", "lot", "item", "with", "new", "you", "your",
    "are", "was", "have", "this", "that", "they", "from", "what", "when",
    "just", "like", "dont", "does", "will", "would", "yall", "guys", "pls",
    "please", "thanks", "thank", "hello", "hey", "yeah", "okay", "not",
    "lol", "omg", "its", "get", "got", "can", "cant", "ima", "its",
    "let", "too", "now", "wow", "yes", "nah", "ugh", "tbh", "idk",
}

_PRODUCT_TOKEN_STOP_WORDS = _CHAT_STOP_WORDS | {
    "ml", "oz", "spray", "perfume", "parfum", "eau", "de", "for", "men", "women",
    "woman", "man", "unisex", "edition", "gift", "set", "tester", "brand", "new",
}

def _pg_get_analytics_chat_signal_rows(stream_id=None):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if stream_id:
                cur.execute(
                    f"SELECT stream_id, payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = %s AND event_type = 'chat_message' ORDER BY id DESC LIMIT 5000",
                    (stream_id,),
                )
            else:
                cur.execute(
                    f"SELECT stream_id, payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE event_type = 'chat_message' ORDER BY id DESC LIMIT 10000"
                )
            return cur.fetchall()


def get_analytics_chat_signals(db_path=None, stream_id=None, limit=200):
    """
    Aggregate chat keywords, top chatters, and recent messages.
    If stream_id given: scoped to that stream.
    Otherwise: across all streams (last 10k messages for performance).
    Returns:
      - top_keywords: [{keyword, mentions, unique_users, streams_count}]
      - top_chatters: [{username, message_count, streams_count}]
      - recent_messages: [{stream_id, username, message, created_at}]
      - total_messages: int
    """
    import re
    if db_path:
        rows = _manual_events_compat_call(
            "get_analytics_chat_signals",
            stream_id=stream_id,
            db_path=db_path,
        )
    else:
        rows = _pg_get_analytics_chat_signal_rows(stream_id=stream_id)

    keyword_mentions = defaultdict(int)
    keyword_users = defaultdict(set)
    keyword_streams = defaultdict(set)
    chatter_msgs = defaultdict(int)
    chatter_streams = defaultdict(set)
    recent = []

    for sid, raw, ts in rows:
        try:
            p = json.loads(raw or "{}")
        except Exception:
            continue
        username = (p.get("username") or p.get("user") or "").strip().lower()
        message = (p.get("message") or "").strip()
        if not username or not message:
            continue

        chatter_msgs[username] += 1
        chatter_streams[username].add(sid)

        if len(recent) < 50:
            recent.append({
                "stream_id": sid,
                "username": username,
                "message": message,
                "created_at": ts,
            })

        tokens = re.findall(r"[a-z]{3,}", message.lower())
        for tok in tokens:
            if tok in _CHAT_STOP_WORDS or len(tok) > 30:
                continue
            keyword_mentions[tok] += 1
            keyword_users[tok].add(username)
            keyword_streams[tok].add(sid)

    top_keywords = sorted(
        [
            {
                "keyword": k,
                "mentions": keyword_mentions[k],
                "unique_users": len(keyword_users[k]),
                "streams_count": len(keyword_streams[k]),
                "score": keyword_mentions[k] + len(keyword_users[k]) * 2,
            }
            for k in keyword_mentions
            if keyword_mentions[k] >= 2
        ],
        key=lambda x: x["score"],
        reverse=True,
    )[:limit]

    top_chatters = sorted(
        [
            {
                "username": u,
                "message_count": chatter_msgs[u],
                "streams_count": len(chatter_streams[u]),
            }
            for u in chatter_msgs
        ],
        key=lambda x: x["message_count"],
        reverse=True,
    )[:50]

    return {
        "top_keywords": top_keywords,
        "top_chatters": top_chatters,
        "recent_messages": recent,
        "total_messages": len(rows),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Analytics: Timing Heatmap
# ─────────────────────────────────────────────────────────────────────────────

def _pg_get_analytics_timing_rows(streamer_name=None):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if streamer_name:
                cur.execute(
                    f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE LOWER(streamer_name) = LOWER(%s)",
                    (streamer_name,),
                )
                stream_ids = [r[0] for r in cur.fetchall()]
            else:
                stream_ids = None
            if stream_ids is not None and not stream_ids:
                return None, None
            if stream_ids:
                cur.execute(
                    f"SELECT event_type, payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = ANY(%s) AND event_type IN ('bid_update','auction_winner','chat_message','live_viewers') ORDER BY id ASC",
                    (stream_ids,),
                )
                rows = cur.fetchall()
                cur.execute(
                    f"SELECT payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = ANY(%s) AND event_type='auction_winner'",
                    (stream_ids,),
                )
                winner_rows = cur.fetchall()
            else:
                cur.execute(
                    f"SELECT event_type, payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE event_type IN ('bid_update','auction_winner','chat_message','live_viewers') ORDER BY id DESC LIMIT 200000"
                )
                rows = cur.fetchall()
                cur.execute(
                    f"SELECT payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE event_type='auction_winner' ORDER BY id DESC LIMIT 50000"
                )
                winner_rows = cur.fetchall()
    return rows, winner_rows


def get_analytics_timing(db_path=None, streamer_name=None):
    """
    Aggregate bids, winners, chat, and viewer counts by hour-of-day and day-of-week.
    Returns:
      - by_hour: [{hour, bids, winners, chat, viewers, engagement_score}] (0-23)
      - by_day:  [{day, day_num, bids, winners, chat, streams, revenue}]
      - best_hour: int
      - best_day: str
    """
    if db_path:
        sqlite_payload = _manual_events_compat_call(
            "get_analytics_timing",
            streamer_name=streamer_name,
            db_path=db_path,
        )
        if sqlite_payload == (None, None):
            return {"by_hour": [], "by_day": [], "best_hour": None, "best_day": None}
        rows, winner_rows = sqlite_payload
    else:
        rows, winner_rows = _pg_get_analytics_timing_rows(streamer_name=streamer_name)
        if rows is None and winner_rows is None:
            return {"by_hour": [], "by_day": [], "best_hour": None, "best_day": None}

    _DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    hour_bids = defaultdict(int)
    hour_winners = defaultdict(int)
    hour_chat = defaultdict(int)
    hour_viewers = defaultdict(list)
    day_bids = defaultdict(int)
    day_winners = defaultdict(int)
    day_chat = defaultdict(int)
    day_streams = defaultdict(set)
    day_revenue = defaultdict(float)

    for event_type, raw, ts in rows:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            h = dt.hour
            d = dt.weekday()  # 0=Mon
        except Exception:
            continue

        try:
            p = json.loads(raw or "{}")
        except Exception:
            p = {}

        if event_type == "bid_update":
            hour_bids[h] += 1
            day_bids[d] += 1
        elif event_type == "auction_winner":
            hour_winners[h] += 1
            day_winners[d] += 1
        elif event_type == "chat_message":
            hour_chat[h] += 1
            day_chat[d] += 1
        elif event_type == "live_viewers":
            cnt = p.get("count") or p.get("viewer_count")
            if cnt is not None:
                try:
                    hour_viewers[h].append(int(cnt))
                except Exception:
                    pass

    for raw, ts in winner_rows:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            d = dt.weekday()
            p = json.loads(raw or "{}")
            price = _parse_winner_price(p)
            day_revenue[d] += price
        except Exception:
            pass

    by_hour = []
    for h in range(24):
        avg_v = round(sum(hour_viewers[h]) / len(hour_viewers[h]), 1) if hour_viewers[h] else 0
        score = hour_bids[h] * 2 + hour_winners[h] * 3 + hour_chat[h] + avg_v * 0.2
        by_hour.append({
            "hour": h,
            "bids": hour_bids[h],
            "winners": hour_winners[h],
            "chat": hour_chat[h],
            "avg_viewers": avg_v,
            "engagement_score": round(score, 1),
        })

    by_day = []
    for d, name in enumerate(_DAY_NAMES):
        by_day.append({
            "day": name,
            "day_num": d,
            "bids": day_bids[d],
            "winners": day_winners[d],
            "chat": day_chat[d],
            "revenue": round(day_revenue[d], 2),
            "engagement_score": round(day_bids[d] * 2 + day_winners[d] * 3 + day_chat[d], 1),
        })

    best_hour_row = max(by_hour, key=lambda x: x["engagement_score"], default=None)
    best_day_row = max(by_day, key=lambda x: x["engagement_score"], default=None)

    return {
        "by_hour": by_hour,
        "by_day": by_day,
        "best_hour": best_hour_row["hour"] if best_hour_row else None,
        "best_day": best_day_row["day"] if best_day_row else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Analytics: Products Intelligence
# ─────────────────────────────────────────────────────────────────────────────

def _pg_get_analytics_products_intel_rows(streamer_name=None):
    _require_postgres_runtime()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if streamer_name:
                cur.execute(
                    f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE LOWER(streamer_name) = LOWER(%s)",
                    (streamer_name,),
                )
                stream_ids = [r[0] for r in cur.fetchall()]
            else:
                stream_ids = None
            if stream_ids is not None and not stream_ids:
                return None, None, None
            if stream_ids:
                cur.execute(
                    f"SELECT product_name, stream_id FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings WHERE stream_id = ANY(%s)",
                    (stream_ids,),
                )
                listing_rows = cur.fetchall()
                cur.execute(
                    f"SELECT payload FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = ANY(%s) AND event_type='auction_winner'",
                    (stream_ids,),
                )
                winner_rows = cur.fetchall()
                cur.execute(
                    f"SELECT payload FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = ANY(%s) AND event_type='bid_update'",
                    (stream_ids,),
                )
                bid_rows = cur.fetchall()
            else:
                cur.execute(f"SELECT product_name, stream_id FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings")
                listing_rows = cur.fetchall()
                cur.execute(f"SELECT payload FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE event_type='auction_winner' ORDER BY id DESC LIMIT 50000")
                winner_rows = cur.fetchall()
                cur.execute(f"SELECT payload FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE event_type='bid_update' ORDER BY id DESC LIMIT 100000")
                bid_rows = cur.fetchall()
    return listing_rows, winner_rows, bid_rows


def get_analytics_products_intel(db_path=None, streamer_name=None, limit=60):
    """
    Aggregate product intelligence across all competitor streams (or one seller).
    Returns:
      - products: [{name, appearances, total_bids, wins, avg_win_price, max_win_price,
                    streams_count, demand_score}]
      - total_products: int
    """
    import re
    if db_path:
        sqlite_payload = _manual_events_compat_call(
            "get_analytics_products_intel",
            streamer_name=streamer_name,
            db_path=db_path,
        )
        if sqlite_payload == (None, None, None):
            return {"products": [], "total_products": 0}
        listing_rows, winner_rows, bid_rows = sqlite_payload
    else:
        listing_rows, winner_rows, bid_rows = _pg_get_analytics_products_intel_rows(streamer_name=streamer_name)
        if listing_rows is None and winner_rows is None and bid_rows is None:
            return {"products": [], "total_products": 0}

    def _normalize(name):
        if not name:
            return ""
        return re.sub(r"\s+", " ", str(name).strip().lower())

    # Catalog appearances
    product_appearances = defaultdict(int)
    product_streams = defaultdict(set)
    for name, sid in listing_rows:
        key = _normalize(name)
        if not key or len(key) < 3:
            continue
        product_appearances[key] += 1
        product_streams[key].add(sid)

    # Wins + prices from auction winners
    product_wins = defaultdict(int)
    product_prices = defaultdict(list)
    for (raw,) in winner_rows:
        try:
            p = json.loads(raw or "{}")
        except Exception:
            continue
        name = _normalize(p.get("product_name") or p.get("title") or p.get("item_name") or "")
        price = _parse_winner_price(p)
        if name and len(name) >= 3:
            product_wins[name] += 1
            if price > 0:
                product_prices[name].append(price)

    # Bids by product
    product_bids = defaultdict(int)
    for (raw,) in bid_rows:
        try:
            p = json.loads(raw or "{}")
        except Exception:
            continue
        name = _normalize(p.get("product_name") or "")
        if name and len(name) >= 3:
            product_bids[name] += 1

    # Union of all known products
    all_keys = set(product_appearances) | set(product_wins) | set(product_bids)
    products = []
    for key in all_keys:
        appearances = product_appearances.get(key, 0)
        wins = product_wins.get(key, 0)
        bids = product_bids.get(key, 0)
        prices = product_prices.get(key, [])
        avg_price = round(sum(prices) / len(prices), 2) if prices else 0.0
        max_price = round(max(prices), 2) if prices else 0.0
        streams = len(product_streams.get(key, set()))
        demand = appearances * 1 + bids * 2 + wins * 3 + avg_price * 0.1
        products.append({
            "name": key,
            "appearances": appearances,
            "total_bids": bids,
            "wins": wins,
            "avg_win_price": avg_price,
            "max_win_price": max_price,
            "streams_count": streams,
            "demand_score": round(demand, 1),
        })

    products.sort(key=lambda x: x["demand_score"], reverse=True)
    return {
        "products": products[:limit],
        "total_products": len(products),
    }
