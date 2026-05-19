from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from .config import POSTGRES_SIDECAR_SCHEMA
from .postgres_cutover import (
    _fetchone_dict_pg,
    _normalize_value,
    _pg_connect,
    domain_primary_backend,
    domain_validate_enabled,
    ensure_wave1_postgres_schema,
    log_cutover_event,
    pg_domain_tx,
    postgres_available,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_OUR_STREAMER_NAMES = {"ynfdeals"}


def _pg_rows_to_dicts(cur) -> list[dict]:
    return [
        {desc[0]: _normalize_value(value) for desc, value in zip(cur.description, row)}
        for row in cur.fetchall()
    ]


def _require_postgres_primary(domain: str) -> None:
    if domain_primary_backend(domain) != "postgres":
        raise RuntimeError(f"postgres_runtime_required:{domain}")


def _reject_sqlite_runtime(value=None) -> None:
    if value:
        raise RuntimeError("ingest_cutover_sqlite_runtime_retired")


def _reject_sqlite_validation(*, db_path: str | None = None, sqlite_compare: bool = False) -> None:
    if db_path or sqlite_compare:
        raise RuntimeError("ingest_cutover_sqlite_validation_retired")


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


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _local_day_key(value: str | None) -> str | None:
    dt = _parse_iso(value)
    if not dt:
        return None
    try:
        return dt.astimezone().date().isoformat()
    except Exception:
        return None


def _extract_stream_slug(stream_url: str | None) -> str | None:
    if not stream_url:
        return None
    match = re.search(r"/live/([^/?#]+)", str(stream_url), flags=re.IGNORECASE)
    if not match:
        return None
    slug = match.group(1).strip().lower()
    return slug or None


def _normalize_stream_identity(stream_url: str | None = None, streamer_name: str | None = None) -> str | None:
    name = (streamer_name or "").strip().lower()
    if name:
        return name
    return _extract_stream_slug(stream_url)


def _pg_latest_stream(stream_url: str) -> dict | None:
    if not postgres_available():
        return None
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, stream_url, streamer_name, title, started_at, ended_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.streams
                WHERE stream_url = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (stream_url,),
            )
            return _fetchone_dict_pg(cur)


def _pg_insert_stream_txn(cur, stream_url: str, streamer_name: str | None, title: str | None, started_at: str | None):
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.streams (stream_url, streamer_name, title, started_at)
        VALUES (%s, %s, %s, %s)
        RETURNING id, stream_url, streamer_name, title, started_at, ended_at
        """,
        (stream_url, (streamer_name or "").strip() or None, (title or "").strip() or None, started_at or _utc_now_iso()),
    )
    return _fetchone_dict_pg(cur)


def _payload_text(payload, *, ensure_ascii: bool = False) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload or {}, ensure_ascii=ensure_ascii)


def _pg_insert_event_txn(cur, stream_id: int, event_type: str, payload_text: str, created_at: str):
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.events (stream_id, event_type, payload, created_at)
        VALUES (%s, %s, %s, %s)
        RETURNING id, stream_id, event_type, payload, created_at
        """,
        (int(stream_id), str(event_type or "").strip(), payload_text, created_at),
    )
    return _fetchone_dict_pg(cur)


def upsert_ingest_user(username: str) -> int | None:
    username = str(username or "").strip()
    if not username:
        return None

    domain = "ingest_users"

    _require_postgres_primary(domain)
    with pg_domain_tx(domain, "users") as (_conn, cur):
        cur.execute(
            f"""
            INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.users (username)
            VALUES (%s)
            ON CONFLICT (username) DO NOTHING
            RETURNING id
            """,
            (username,),
        )
        row = cur.fetchone()
        if row:
            user_id = int(row[0])
        else:
            cur.execute(
                f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.users WHERE username = %s LIMIT 1",
                (username,),
            )
            existing = cur.fetchone()
            user_id = int(existing[0]) if existing else None
    return user_id


def upsert_ingest_lot_open(stream_id, lot_number, product_name, started_at) -> int | None:
    stream_id = int(stream_id or 0)
    if not stream_id:
        return None
    lot_number = str(lot_number or "")
    product_name = str(product_name or "")
    started_at = str(started_at or _utc_now_iso())
    domain = "ingest_lots"

    _require_postgres_primary(domain)
    with pg_domain_tx(domain, "lots") as (_conn, cur):
        cur.execute(
            f"""
            SELECT id
            FROM {POSTGRES_SIDECAR_SCHEMA}.lots
            WHERE stream_id = %s AND COALESCE(lot_number, '') = %s AND COALESCE(product_name, '') = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (stream_id, lot_number, product_name),
        )
        existing = cur.fetchone()
        if existing:
            lot_id = int(existing[0])
        else:
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.lots
                    (stream_id, lot_number, product_name, started_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (stream_id, lot_number or None, product_name or None, started_at),
            )
            row = cur.fetchone()
            lot_id = int(row[0]) if row else None
    return lot_id


def close_ingest_lot(lot_id, winner_username, final_price, ended_at) -> bool:
    lot_id = int(lot_id or 0)
    if not lot_id:
        return False
    winner_username = str(winner_username or "")
    ended_at = str(ended_at or _utc_now_iso())
    domain = "ingest_lots"

    _require_postgres_primary(domain)
    with pg_domain_tx(domain, "lots") as (_conn, cur):
        cur.execute(
            f"""
            UPDATE {POSTGRES_SIDECAR_SCHEMA}.lots
            SET winner_username = %s,
                final_price = %s,
                ended_at = %s
            WHERE id = %s AND winner_username IS NULL
            """,
            (winner_username, final_price, ended_at, lot_id),
        )
    return True


def replace_competitor_listings_snapshot(stream_id, listings, scraped_at=None) -> int:
    stream_id = int(stream_id or 0)
    if not stream_id:
        return 0
    listings = list(listings or [])
    scraped_at = str(scraped_at or _utc_now_iso())
    domain = "ingest_events"

    _require_postgres_primary(domain)
    ensure_wave1_postgres_schema()
    with pg_domain_tx(domain, "competitor_listings") as (_conn, cur):
        cur.execute(
            f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings WHERE stream_id = %s",
            (stream_id,),
        )
        if listings:
            cur.executemany(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.competitor_listings (
                    stream_id, scraped_at, product_name, qty, starting_price, bid_count,
                    listing_type, image_url, button_label, badge_text, catalog_position
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        stream_id,
                        scraped_at,
                        row.get("product_name"),
                        row.get("qty"),
                        row.get("starting_price"),
                        row.get("bid_count"),
                        row.get("listing_type"),
                        row.get("image_url"),
                        row.get("button_label"),
                        row.get("badge_text"),
                        row.get("catalog_position"),
                    )
                    for row in listings
                ],
            )
    return len(listings)


def insert_stream_ocr_frame(stream_id, image_path, ocr_text_raw, confidence=0, source="rapidocr", captured_at=None) -> bool:
    stream_id = int(stream_id or 0)
    if not stream_id:
        return False
    captured_at = str(captured_at or _utc_now_iso())
    domain = "ingest_events"
    values = (
        stream_id,
        captured_at,
        image_path,
        str(ocr_text_raw or ""),
        float(confidence or 0),
        source or "rapidocr",
    )

    _require_postgres_primary(domain)
    ensure_wave1_postgres_schema()
    with pg_domain_tx(domain, "stream_ocr_frames") as (_conn, cur):
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
            f"""
            INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.stream_ocr_frames
            (stream_id, captured_at, image_path, ocr_text_raw, ocr_confidence, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            values,
        )
    return True


def insert_stream_caption_window(stream_id, caption_text, confidence=0, source="dom_probe", captured_at=None) -> bool:
    stream_id = int(stream_id or 0)
    if not stream_id:
        return False
    captured_at = str(captured_at or _utc_now_iso())
    domain = "ingest_events"
    values = (
        stream_id,
        captured_at,
        str(caption_text or "").strip(),
        float(confidence or 0),
        source or "dom_probe",
    )

    _require_postgres_primary(domain)
    ensure_wave1_postgres_schema()
    with pg_domain_tx(domain, "stream_caption_windows") as (_conn, cur):
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
            f"""
            INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.stream_caption_windows
            (stream_id, captured_at, caption_text, confidence, source)
            VALUES (%s, %s, %s, %s, %s)
            """,
            values,
        )
    return True


def upsert_reconstructed_ingest_lot(
    stream_id,
    lot_number,
    product_name,
    started_at,
    ended_at,
    winner_username,
    final_price,
):
    stream_id = int(stream_id or 0)
    if not stream_id:
        return None
    lot_number = str(lot_number or "").strip()
    product_name = str(product_name or "").strip()
    started_at = str(started_at or ended_at or _utc_now_iso())
    ended_at = str(ended_at or _utc_now_iso())
    winner_username = (str(winner_username or "").strip() or None)
    final_price = float(final_price or 0) if final_price not in (None, "") else None
    domain = "ingest_lots"
    _require_postgres_primary(domain)

    def _apply_existing(cur, lot_id, existing_winner, existing_price, existing_ended):
        updates = []
        params = []
        if winner_username and not existing_winner:
            updates.append("winner_username=%s")
            params.append(winner_username)
        if final_price and not existing_price:
            updates.append("final_price=%s")
            params.append(final_price)
        if ended_at and not existing_ended:
            updates.append("ended_at=%s")
            params.append(ended_at)
        if product_name:
            updates.append("product_name=COALESCE(NULLIF(product_name,''), %s)")
            params.append(product_name)
        if updates:
            params.append(lot_id)
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.lots SET {', '.join(updates)} WHERE id=%s",
                params,
            )
        return lot_id

    try:
        with pg_domain_tx(domain, "lots") as (_conn, cur):
            existing = None
            if lot_number:
                cur.execute(
                    f"""
                    SELECT id, winner_username, final_price, ended_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.lots
                    WHERE stream_id=%s AND lot_number=%s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (stream_id, lot_number),
                )
                existing = cur.fetchone()
            if not existing and product_name and ended_at:
                cur.execute(
                    f"""
                    SELECT id, winner_username, final_price, ended_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.lots
                    WHERE stream_id=%s AND product_name=%s AND ended_at=%s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (stream_id, product_name, ended_at),
                )
                existing = cur.fetchone()
            if existing:
                lot_id = _apply_existing(cur, int(existing[0]), existing[1], existing[2], existing[3])
            else:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.lots
                        (stream_id, lot_number, product_name, started_at, ended_at, winner_username, final_price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (stream_id, lot_number or None, product_name or None, started_at, ended_at, winner_username, final_price),
                )
                row = cur.fetchone()
                lot_id = int(row[0]) if row else None
        return lot_id
    except Exception as exc:
        log_cutover_event(domain, "postgres_primary_failed_closed", "lots", f"{stream_id}:{lot_number}:{product_name}:{ended_at}", {"error": str(exc)})
        raise


def insert_event(
    stream_id: int,
    event_type: str,
    payload,
    *,
    created_at: str | None = None,
    ensure_ascii: bool = False,
) -> int | None:
    if not stream_id:
        return None
    event_type = str(event_type or "").strip()
    if not event_type:
        return None
    payload_text = _payload_text(payload, ensure_ascii=ensure_ascii)
    created_at = str(created_at or _utc_now_iso())
    domain = "ingest_events"
    _require_postgres_primary(domain)
    try:
        with pg_domain_tx(domain, "events") as (_conn, cur):
            row = _pg_insert_event_txn(cur, int(stream_id), event_type, payload_text, created_at)
        if row and row.get("id"):
            return int(row["id"])
        return None
    except Exception as exc:
        log_cutover_event(
            domain,
            "postgres_primary_failed_closed",
            "events",
            f"{stream_id}:{event_type}",
            {"error": str(exc)},
        )
        raise


def create_failed_ingest(event_id, winner_username, sale_price, lot_number, sold_at, error_message, *, created_at: str | None = None) -> int | None:
    domain = "ingest_failed"
    source_event_id = f"collector_event_{event_id}"
    created_at = str(created_at or _utc_now_iso())
    _require_postgres_primary(domain)
    try:
        with pg_domain_tx(domain, "failed_ingests") as (_conn, cur):
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.failed_ingests
                    (event_id, source_event_id, winner_username, sale_price, lot_number, sold_at, error_message, retry_count, created_at, resolved)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, 0)
                ON CONFLICT (source_event_id) DO NOTHING
                RETURNING id
                """,
                (event_id, source_event_id, winner_username, sale_price, lot_number, sold_at, error_message, created_at),
            )
            row = cur.fetchone()
            if row:
                failed_id = int(row[0])
            else:
                cur.execute(
                    f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.failed_ingests WHERE source_event_id = %s LIMIT 1",
                    (source_event_id,),
                )
                existing = cur.fetchone()
                failed_id = int(existing[0]) if existing else None
        return failed_id
    except Exception as exc:
        log_cutover_event(domain, "postgres_primary_failed_closed", "failed_ingests", source_event_id, {"error": str(exc)})
        raise


def resolve_failed_ingest(failed_id) -> bool:
    domain = "ingest_failed"
    failed_id = int(failed_id or 0)
    if not failed_id:
        return False

    _require_postgres_primary(domain)
    try:
        with pg_domain_tx(domain, "failed_ingests") as (_conn, cur):
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.failed_ingests SET resolved = 1 WHERE id = %s",
                (failed_id,),
            )
        return True
    except Exception as exc:
        log_cutover_event(domain, "postgres_primary_failed_closed", "failed_ingests", failed_id, {"error": str(exc)})
        raise


def increment_failed_ingest_retry(failed_id, error_message=None, *, last_retry_at: str | None = None) -> bool:
    domain = "ingest_failed"
    failed_id = int(failed_id or 0)
    if not failed_id:
        return False
    last_retry_at = str(last_retry_at or _utc_now_iso())

    _require_postgres_primary(domain)
    try:
        with pg_domain_tx(domain, "failed_ingests") as (_conn, cur):
            if error_message is not None:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.failed_ingests
                       SET retry_count = retry_count + 1,
                           last_retry_at = %s,
                           error_message = %s
                     WHERE id = %s
                    """,
                    (last_retry_at, error_message, failed_id),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.failed_ingests
                       SET retry_count = retry_count + 1,
                           last_retry_at = %s
                     WHERE id = %s
                    """,
                    (last_retry_at, failed_id),
                )
        return True
    except Exception as exc:
        log_cutover_event(domain, "postgres_primary_failed_closed", "failed_ingests", failed_id, {"error": str(exc)})
        raise


def ensure_ingest_stream(stream_url: str, streamer_name: str | None = None, title: str | None = None, started_at: str | None = None) -> int | None:
    stream_url = (stream_url or "").strip()
    if not stream_url:
        return None

    domain = "ingest_streams"
    _require_postgres_primary(domain)
    existing = _pg_latest_stream(stream_url)
    if existing:
        return int(existing["id"])
    try:
        with pg_domain_tx(domain, "streams") as (_conn, cur):
            row = _pg_insert_stream_txn(cur, stream_url, streamer_name, title, started_at)
        if row and row.get("id"):
            return int(row["id"])
        return None
    except Exception as exc:
        log_cutover_event(domain, "postgres_primary_failed_closed", "streams", stream_url, {"error": str(exc)})
        raise


def update_ingest_stream_metadata(
    stream_id,
    *,
    stream_url: str | None = None,
    streamer_name: str | None = None,
    title: str | None = None,
    ended_at: str | None = None,
    clear_ended_at: bool = False,
) -> bool:
    domain = "ingest_streams"
    stream_id = int(stream_id or 0)
    if not stream_id:
        return False

    set_parts = []
    params = []

    if stream_url is not None:
        set_parts.append("stream_url = %s")
        params.append((stream_url or "").strip() or None)
    if streamer_name is not None:
        set_parts.append("streamer_name = COALESCE(%s, streamer_name)")
        params.append((streamer_name or "").strip() or None)
    if title is not None:
        set_parts.append("title = COALESCE(%s, title)")
        params.append((title or "").strip() or None)
    if clear_ended_at:
        set_parts.append("ended_at = NULL")
    elif ended_at is not None:
        set_parts.append("ended_at = %s")
        params.append(str(ended_at or "").strip() or None)

    if not set_parts:
        return True
    _require_postgres_primary(domain)
    try:
        with pg_domain_tx(domain, "streams") as (_conn, cur):
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.streams
                SET {', '.join(set_parts)}
                WHERE id = %s
                RETURNING id
                """,
                (*params, stream_id),
            )
            row = cur.fetchone()
            updated = bool(row)
        return updated
    except Exception as exc:
        log_cutover_event(domain, "postgres_primary_failed_closed", "streams", stream_id, {"error": str(exc)})
        raise


def _pg_fetch_stream_row(cur, stream_id: int) -> dict | None:
    cur.execute(
        f"""
        SELECT id, stream_url, streamer_name, title, started_at, ended_at
        FROM {POSTGRES_SIDECAR_SCHEMA}.streams
        WHERE id = %s
        """,
        (int(stream_id),),
    )
    return _fetchone_dict_pg(cur)


def _merge_stream_fields(src: dict, dst: dict) -> dict:
    src_started = _parse_iso(src.get("started_at"))
    dst_started = _parse_iso(dst.get("started_at"))
    src_ended = _parse_iso(src.get("ended_at"))
    dst_ended = _parse_iso(dst.get("ended_at"))

    if dst_started and src_started:
        merged_started = dst.get("started_at") if dst_started <= src_started else src.get("started_at")
    else:
        merged_started = dst.get("started_at") or src.get("started_at")

    if dst_ended and src_ended:
        merged_ended = dst.get("ended_at") if dst_ended >= src_ended else src.get("ended_at")
    else:
        merged_ended = dst.get("ended_at") or src.get("ended_at")

    return {
        "stream_url": dst.get("stream_url") or src.get("stream_url"),
        "streamer_name": dst.get("streamer_name") or src.get("streamer_name"),
        "title": dst.get("title") or src.get("title"),
        "started_at": merged_started,
        "ended_at": merged_ended,
    }


def _pg_merge_stream_rows_txn(cur, source_id: int, target_id: int) -> int:
    if int(source_id) == int(target_id):
        return int(target_id)
    src = _pg_fetch_stream_row(cur, int(source_id))
    dst = _pg_fetch_stream_row(cur, int(target_id))
    if not src or not dst:
        return int(target_id)

    merged = _merge_stream_fields(src, dst)
    for table in ("events", "lots", "chat_messages", "competitor_listings", "company_sessions"):
        cur.execute(
            f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.{table} SET stream_id = %s WHERE stream_id = %s",
            (int(target_id), int(source_id)),
        )

    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.streams
           SET stream_url = %s,
               streamer_name = %s,
               title = %s,
               started_at = %s,
               ended_at = %s
         WHERE id = %s
        """,
        (
            merged["stream_url"],
            merged["streamer_name"],
            merged["title"],
            merged["started_at"],
            merged["ended_at"],
            int(target_id),
        ),
    )
    cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE id = %s", (int(source_id),))
    return int(target_id)


def merge_ingest_stream_rows(sqlite_conn=None, source_id: int = 0, target_id: int = 0) -> int:
    domain = "ingest_stream_merge"
    _reject_sqlite_runtime(sqlite_conn)
    source_id = int(source_id or 0)
    target_id = int(target_id or 0)
    if not source_id or not target_id:
        return int(target_id or source_id or 0)
    _require_postgres_primary(domain)
    try:
        with pg_domain_tx(domain, "stream_merge") as (_conn, cur):
            canonical_id = _pg_merge_stream_rows_txn(cur, source_id, target_id)
        return int(canonical_id)
    except Exception as exc:
        log_cutover_event(domain, "postgres_primary_failed_closed", "streams", source_id, {"target_id": target_id, "error": str(exc)})
        raise


def _pg_finalize_stream_identity_txn(
    cur,
    stream_id: int,
    stream_url: str,
    streamer_name: str | None = None,
    title: str | None = None,
) -> int:
    row = _pg_fetch_stream_row(cur, int(stream_id))
    if not row:
        return int(stream_id)

    identity = _normalize_stream_identity(stream_url=stream_url, streamer_name=streamer_name or row.get("streamer_name"))
    if not identity or identity in _OUR_STREAMER_NAMES:
        cur.execute(
            f"""
            UPDATE {POSTGRES_SIDECAR_SCHEMA}.streams
               SET stream_url = %s,
                   streamer_name = COALESCE(%s, streamer_name),
                   title = COALESCE(%s, title)
             WHERE id = %s
            """,
            (stream_url, streamer_name, title, int(stream_id)),
        )
        return int(stream_id)

    day_key = _local_day_key(row.get("started_at"))
    canonical_id = int(stream_id)
    cur.execute(
        f"""
        SELECT id, stream_url, streamer_name, started_at
        FROM {POSTGRES_SIDECAR_SCHEMA}.streams
        ORDER BY started_at ASC, id ASC
        """
    )
    for candidate in [
        {desc[0]: value for desc, value in zip(cur.description, row_values)}
        for row_values in cur.fetchall()
    ]:
        candidate_identity = _normalize_stream_identity(
            stream_url=candidate.get("stream_url"),
            streamer_name=candidate.get("streamer_name"),
        )
        if candidate_identity != identity or _local_day_key(candidate.get("started_at")) != day_key:
            continue
        canonical_id = int(candidate["id"])
        break

    if canonical_id != int(stream_id):
        canonical_id = _pg_merge_stream_rows_txn(cur, int(stream_id), canonical_id)

    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.streams
           SET stream_url = %s,
               streamer_name = COALESCE(%s, streamer_name),
               title = COALESCE(%s, title),
               ended_at = NULL
         WHERE id = %s
        """,
        (stream_url, streamer_name, title, canonical_id),
    )
    return int(canonical_id)


def finalize_ingest_stream_identity(
    sqlite_conn=None,
    stream_id: int = 0,
    stream_url: str = "",
    streamer_name: str | None = None,
    title: str | None = None,
) -> int:
    domain = "ingest_stream_merge"
    _reject_sqlite_runtime(sqlite_conn)
    stream_id = int(stream_id or 0)
    if not stream_id:
        return 0
    _require_postgres_primary(domain)
    try:
        with pg_domain_tx(domain, "stream_finalize") as (_conn, cur):
            canonical_id = _pg_finalize_stream_identity_txn(cur, stream_id, stream_url, streamer_name, title)
        return int(canonical_id)
    except Exception as exc:
        log_cutover_event(domain, "postgres_primary_failed_closed", "streams", stream_id, {"stream_url": stream_url, "error": str(exc)})
        raise


def _pg_only_streams_validation_report(recent_limit: int = 100) -> dict:
    ensure_wave1_postgres_schema()
    with _pg_connect() as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.streams")
            pg_count = int((cur.fetchone() or [0])[0] or 0)
            cur.execute(
                f"""
                SELECT id, stream_url, streamer_name, title, started_at, ended_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.streams
                ORDER BY id DESC
                LIMIT %s
                """,
                (int(recent_limit),),
            )
            pg_recent = _pg_rows_to_dicts(cur)
            cur.execute(
                f"""
                SELECT stream_url, COUNT(*) AS row_count, MAX(id) AS latest_id
                FROM {POSTGRES_SIDECAR_SCHEMA}.streams
                GROUP BY stream_url
                """
            )
            pg_url_groups = {
                _normalize_value(row[0]): {
                    "row_count": int(row[1] or 0),
                    "latest_id": int(row[2] or 0),
                }
                for row in cur.fetchall()
            }
            cur.execute(
                f"""
                SELECT s1.id, s1.stream_url, s1.streamer_name, s1.title, s1.started_at, s1.ended_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.streams s1
                JOIN (
                    SELECT stream_url, MAX(id) AS latest_id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.streams
                    GROUP BY stream_url
                ) latest
                  ON latest.stream_url = s1.stream_url
                 AND latest.latest_id = s1.id
                """
            )
            pg_latest = {
                _normalize_value(row[1]): {
                    "id": int(row[0]),
                    "streamer_name": _normalize_value(row[2]),
                    "title": _normalize_value(row[3]),
                    "started_at": _normalize_value(row[4]),
                    "ended_at": _normalize_value(row[5]),
                }
                for row in cur.fetchall()
            }
    return {
        "ok": True,
        "mode": "postgres_only",
        "row_count": pg_count,
        "recent_rows": {"recent_limit": int(recent_limit), "sample": pg_recent[:10]},
        "stream_url_grouping": {"group_count": len(pg_url_groups), "sample": dict(list(sorted(pg_url_groups.items()))[:20])},
        "latest_stream_lookup": {"sample": dict(list(pg_latest.items())[:20])},
    }


def _pg_only_stream_merge_validation_report(source_id: int | None = None, target_id: int | None = None, recent_limit: int = 100) -> dict:
    ensure_wave1_postgres_schema()
    source_id = int(source_id or 0) or None
    target_id = int(target_id or 0) or None
    dep_tables = ("events", "lots", "chat_messages", "competitor_listings", "company_sessions")
    with _pg_connect() as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(
                f"SELECT id, stream_url, streamer_name, title, started_at, ended_at FROM {POSTGRES_SIDECAR_SCHEMA}.streams"
            )
            pg_streams = _pg_rows_to_dicts(cur)
            pg_target = next((row for row in pg_streams if int(row["id"]) == int(target_id or -1)), None)
            pg_source = next((row for row in pg_streams if int(row["id"]) == int(source_id or -1)), None)
            pg_identity_map = _canonical_stream_lookup_map(pg_streams)
            pg_orphans = {}
            pg_source_refs = {}
            fk_counts = {}
            for table in dep_tables:
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.{table} t
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = t.stream_id
                    WHERE s.id IS NULL
                    """
                )
                pg_orphans[table] = int((cur.fetchone() or [0])[0] or 0)
                pg_source_count = None
                pg_target_count = None
                if source_id:
                    cur.execute(
                        f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.{table} WHERE stream_id = %s",
                        (int(source_id),),
                    )
                    pg_source_count = int((cur.fetchone() or [0])[0] or 0)
                    pg_source_refs[table] = pg_source_count
                if target_id:
                    cur.execute(
                        f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.{table} WHERE stream_id = %s",
                        (int(target_id),),
                    )
                    pg_target_count = int((cur.fetchone() or [0])[0] or 0)
                fk_counts[table] = {
                    "postgres_source_count": pg_source_count,
                    "postgres_target_count": pg_target_count,
                }
            pg_recent = sorted(pg_streams, key=lambda row: int(row.get("id") or 0), reverse=True)[: int(recent_limit)]
    return {
        "ok": True,
        "mode": "postgres_only",
        "canonical_target_row": {"target_id": target_id, "postgres_target": pg_target},
        "source_stream_presence": {"source_id": source_id, "postgres_source_exists": pg_source is not None},
        "target_stream_presence": {"target_id": target_id, "postgres_target_exists": pg_target is not None},
        "foreign_key_counts": {"tables": fk_counts},
        "orphaned_references": {"postgres_orphans": pg_orphans, "postgres_source_residuals": pg_source_refs},
        "latest_stream_identity_lookup": {"sample": dict(list(pg_identity_map.items())[:20])},
        "recent_stream_behavior": {"recent_limit": int(recent_limit), "postgres_sample": pg_recent[-10:]},
    }


def _pg_only_events_validation_report(recent_limit: int = 500, duplicate_limit: int = 2000) -> dict:
    ensure_wave1_postgres_schema()
    with _pg_connect() as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.events")
            pg_count = int((cur.fetchone() or [0])[0] or 0)
            cur.execute(
                f"SELECT event_type, COUNT(*) AS row_count FROM {POSTGRES_SIDECAR_SCHEMA}.events GROUP BY event_type"
            )
            pg_type_counts = {_normalize_value(row[0]): int(row[1] or 0) for row in cur.fetchall()}
            cur.execute(
                f"""
                SELECT id, stream_id, event_type, payload, created_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                ORDER BY id DESC
                LIMIT %s
                """,
                (int(recent_limit),),
            )
            pg_recent = _pg_rows_to_dicts(cur)
            pg_recent_hashes = [
                {"id": int(row["id"] or 0), "stream_id": int(row["stream_id"] or 0), "event_type": row["event_type"], "payload_hash": _payload_hash(row["payload"])}
                for row in pg_recent
            ]
            cur.execute(
                f"""
                SELECT id, stream_id, event_type, payload, created_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                ORDER BY id DESC
                LIMIT 1
                """
            )
            newest_rows = _pg_rows_to_dicts(cur)
            pg_newest = newest_rows[0] if newest_rows else None
            pg_max_id = int(pg_newest["id"] or 0) if pg_newest else 0
            cur.execute(
                f"SELECT stream_id, COUNT(*) AS row_count FROM {POSTGRES_SIDECAR_SCHEMA}.events GROUP BY stream_id"
            )
            pg_stream_counts = {int(row[0]): int(row[1] or 0) for row in cur.fetchall()}
            cur.execute(
                f"""
                SELECT stream_id, event_type, payload, COUNT(*) AS dup_count
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                GROUP BY stream_id, event_type, payload
                HAVING COUNT(*) > 1
                ORDER BY dup_count DESC, stream_id ASC
                LIMIT %s
                """,
                (int(duplicate_limit),),
            )
            pg_dupes = {
                f"{int(row[0])}|{_normalize_value(row[1])}|{_payload_hash(row[2])}": int(row[3] or 0)
                for row in cur.fetchall()
            }
    return {
        "ok": True,
        "mode": "postgres_only",
        "row_count": pg_count,
        "event_type_counts": pg_type_counts,
        "recent_rows": {"recent_limit": int(recent_limit), "sample": pg_recent[:20]},
        "payload_hashes": {"recent_limit": int(recent_limit), "sample": pg_recent_hashes[:20]},
        "newest_event": {"max_id": pg_max_id, "row": pg_newest},
        "stream_linkage": {"stream_count": len(pg_stream_counts), "sample": dict(list(sorted(pg_stream_counts.items()))[:20])},
        "duplicate_detection": {"duplicate_count": len(pg_dupes), "sample": dict(list(pg_dupes.items())[:20])},
    }


def _pg_only_failed_ingest_validation_report(recent_limit: int = 100) -> dict:
    ensure_wave1_postgres_schema()
    with _pg_connect() as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.failed_ingests")
            pg_count = int((cur.fetchone() or [0])[0] or 0)
            cur.execute(f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.failed_ingests WHERE resolved = 0")
            pg_unresolved = int((cur.fetchone() or [0])[0] or 0)
            cur.execute(
                f"SELECT COALESCE(retry_count, 0) AS retry_count, COUNT(*) AS row_count FROM {POSTGRES_SIDECAR_SCHEMA}.failed_ingests GROUP BY COALESCE(retry_count, 0)"
            )
            pg_retry_counts = {int(row[0] or 0): int(row[1] or 0) for row in cur.fetchall()}
            cur.execute(
                f"SELECT COALESCE(resolved, 0) AS resolved, COUNT(*) AS row_count FROM {POSTGRES_SIDECAR_SCHEMA}.failed_ingests GROUP BY COALESCE(resolved, 0)"
            )
            pg_resolved_counts = {int(row[0] or 0): int(row[1] or 0) for row in cur.fetchall()}
            cur.execute(
                f"""
                SELECT id, event_id, source_event_id, winner_username, sale_price, lot_number,
                       sold_at, error_message, retry_count, created_at, last_retry_at, resolved
                FROM {POSTGRES_SIDECAR_SCHEMA}.failed_ingests
                ORDER BY id DESC
                LIMIT %s
                """,
                (int(recent_limit),),
            )
            pg_recent = _pg_rows_to_dicts(cur)
            cur.execute(
                f"""
                SELECT source_event_id, COUNT(*) AS dup_count
                FROM {POSTGRES_SIDECAR_SCHEMA}.failed_ingests
                GROUP BY source_event_id
                HAVING COUNT(*) > 1
                ORDER BY dup_count DESC, source_event_id ASC
                """
            )
            pg_dupes = {_normalize_value(row[0]): int(row[1] or 0) for row in cur.fetchall()}
    return {
        "ok": True,
        "mode": "postgres_only",
        "row_count": pg_count,
        "unresolved_count": pg_unresolved,
        "retry_counts": pg_retry_counts,
        "resolved_counts": pg_resolved_counts,
        "recent_rows": {"recent_limit": int(recent_limit), "sample": pg_recent[:20]},
        "source_event_duplicates": {"duplicate_count": len(pg_dupes), "sample": dict(list(pg_dupes.items())[:20])},
    }


def _pg_only_users_validation_report(recent_limit: int = 200, event_limit: int = 5000) -> dict:
    ensure_wave1_postgres_schema()
    with _pg_connect() as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.users")
            pg_count = int((cur.fetchone() or [0])[0] or 0)
            cur.execute(f"SELECT COUNT(DISTINCT username) FROM {POSTGRES_SIDECAR_SCHEMA}.users")
            pg_distinct = int((cur.fetchone() or [0])[0] or 0)
            cur.execute(
                f"SELECT id, username FROM {POSTGRES_SIDECAR_SCHEMA}.users ORDER BY id DESC LIMIT %s",
                (int(recent_limit),),
            )
            pg_recent = _pg_rows_to_dicts(cur)
            cur.execute(
                f"""
                SELECT username, COUNT(*) AS dup_count
                FROM {POSTGRES_SIDECAR_SCHEMA}.users
                GROUP BY username
                HAVING COUNT(*) > 1
                ORDER BY dup_count DESC, username ASC
                """
            )
            pg_dupes = {_normalize_value(row[0]): int(row[1] or 0) for row in cur.fetchall()}
            cur.execute(f"SELECT username FROM {POSTGRES_SIDECAR_SCHEMA}.users")
            pg_usernames = {_normalize_value(row[0]) for row in cur.fetchall() if _normalize_value(row[0])}
            cur.execute(
                f"""
                SELECT event_type, payload
                FROM {POSTGRES_SIDECAR_SCHEMA}.events
                WHERE event_type IN ('chat_message', 'auction_winner')
                ORDER BY id DESC
                LIMIT %s
                """,
                (int(event_limit),),
            )
            event_rows = cur.fetchall()
    recent_event_usernames = set()
    for row in event_rows:
        event_type = _normalize_value(row[0])
        try:
            payload = json.loads(row[1] or "{}")
        except Exception:
            continue
        if event_type == "chat_message":
            username = str(payload.get("username") or payload.get("user") or "").strip()
        else:
            username = str(payload.get("winner") or payload.get("winner_username") or payload.get("username") or "").strip()
        if username:
            recent_event_usernames.add(username)
    pg_missing_from_events = sorted(username for username in recent_event_usernames if username not in pg_usernames)
    return {
        "ok": True,
        "mode": "postgres_only",
        "row_count": pg_count,
        "distinct_usernames": pg_distinct,
        "recent_rows": {"recent_limit": int(recent_limit), "sample": pg_recent[:20]},
        "event_linkage_consistency": {"event_limit": int(event_limit), "missing_count": len(pg_missing_from_events), "missing_sample": pg_missing_from_events[:20]},
        "duplicate_detection": {"duplicate_count": len(pg_dupes), "sample": dict(list(pg_dupes.items())[:20])},
    }


def _pg_only_lots_validation_report(recent_limit: int = 200, duplicate_limit: int = 2000) -> dict:
    ensure_wave1_postgres_schema()
    with _pg_connect() as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.lots")
            pg_count = int((cur.fetchone() or [0])[0] or 0)
            cur.execute(f"SELECT stream_id, COUNT(*) AS row_count FROM {POSTGRES_SIDECAR_SCHEMA}.lots GROUP BY stream_id")
            pg_stream_counts = {int(row[0]): int(row[1] or 0) for row in cur.fetchall()}
            cur.execute(
                f"""
                SELECT id, stream_id, lot_number, product_name, started_at, ended_at, winner_username, final_price
                FROM {POSTGRES_SIDECAR_SCHEMA}.lots ORDER BY id DESC LIMIT %s
                """,
                (int(recent_limit),),
            )
            pg_recent = _pg_rows_to_dicts(cur)
            cur.execute(
                f"""
                SELECT stream_id, COALESCE(lot_number, '') AS lot_number, COUNT(*) AS row_count
                FROM {POSTGRES_SIDECAR_SCHEMA}.lots
                GROUP BY stream_id, COALESCE(lot_number, '')
                """
            )
            pg_stream_lot_groups = {
                f"{int(row[0])}|{_normalize_value(row[1])}": int(row[2] or 0)
                for row in cur.fetchall()
            }
            cur.execute(
                f"""
                SELECT id, stream_id, lot_number, winner_username, final_price, ended_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.lots
                WHERE winner_username IS NOT NULL AND TRIM(COALESCE(winner_username,'')) != ''
                ORDER BY id DESC
                LIMIT %s
                """,
                (int(recent_limit),),
            )
            pg_winner_rows = _pg_rows_to_dicts(cur)
            cur.execute(
                f"""
                SELECT stream_id, COALESCE(lot_number, '') AS lot_number, COALESCE(product_name, '') AS product_name,
                       COUNT(*) AS dup_count
                FROM {POSTGRES_SIDECAR_SCHEMA}.lots
                GROUP BY stream_id, COALESCE(lot_number, ''), COALESCE(product_name, '')
                HAVING COUNT(*) > 1
                ORDER BY dup_count DESC, stream_id ASC
                LIMIT %s
                """,
                (int(duplicate_limit),),
            )
            pg_dupes = {
                f"{int(row[0])}|{_normalize_value(row[1])}|{_normalize_value(row[2])}": int(row[3] or 0)
                for row in cur.fetchall()
            }
    return {
        "ok": True,
        "mode": "postgres_only",
        "row_count": pg_count,
        "stream_row_counts": pg_stream_counts,
        "recent_rows": {"recent_limit": int(recent_limit), "sample": pg_recent[:20]},
        "stream_lot_grouping": {"group_count": len(pg_stream_lot_groups), "sample": dict(list(sorted(pg_stream_lot_groups.items()))[:20])},
        "winner_rows": {"recent_limit": int(recent_limit), "sample": pg_winner_rows[:20]},
        "duplicate_detection": {"duplicate_count": len(pg_dupes), "sample": dict(list(pg_dupes.items())[:20])},
    }


def streams_validation_report(recent_limit: int = 100, *, db_path: str | None = None, sqlite_compare: bool = False) -> dict:
    if not postgres_available():
        return {"ok": False, "error": "postgres_unavailable"}
    _reject_sqlite_validation(db_path=db_path, sqlite_compare=sqlite_compare)
    return _pg_only_streams_validation_report(recent_limit=recent_limit)


def _canonical_stream_lookup_map(rows: list[dict]) -> dict:
    mapping = {}
    ordered = sorted(
        rows,
        key=lambda row: ((row.get("started_at") or ""), int(row.get("id") or 0)),
    )
    for row in ordered:
        identity = _normalize_stream_identity(row.get("stream_url"), row.get("streamer_name"))
        day_key = _local_day_key(row.get("started_at"))
        if not identity or not day_key or identity in _OUR_STREAMER_NAMES:
            continue
        key = f"{identity}|{day_key}"
        mapping.setdefault(
            key,
            {
                "id": int(row.get("id") or 0),
                "stream_url": _normalize_value(row.get("stream_url")),
                "streamer_name": _normalize_value(row.get("streamer_name")),
                "title": _normalize_value(row.get("title")),
                "started_at": _normalize_value(row.get("started_at")),
                "ended_at": _normalize_value(row.get("ended_at")),
            },
        )
    return mapping


def stream_merge_validation_report(
    source_id: int | None = None,
    target_id: int | None = None,
    recent_limit: int = 100,
    *,
    db_path: str | None = None,
    sqlite_compare: bool = False,
) -> dict:
    if not postgres_available():
        return {"ok": False, "error": "postgres_unavailable"}
    _reject_sqlite_validation(db_path=db_path, sqlite_compare=sqlite_compare)
    return _pg_only_stream_merge_validation_report(source_id=source_id, target_id=target_id, recent_limit=recent_limit)


def _payload_hash(value) -> str:
    text = "" if value is None else str(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def events_validation_report(
    recent_limit: int = 500,
    duplicate_limit: int = 2000,
    *,
    db_path: str | None = None,
    sqlite_compare: bool = False,
) -> dict:
    if not postgres_available():
        return {"ok": False, "error": "postgres_unavailable"}
    _reject_sqlite_validation(db_path=db_path, sqlite_compare=sqlite_compare)
    return _pg_only_events_validation_report(recent_limit=recent_limit, duplicate_limit=duplicate_limit)


def failed_ingest_validation_report(
    recent_limit: int = 100,
    *,
    db_path: str | None = None,
    sqlite_compare: bool = False,
) -> dict:
    if not postgres_available():
        return {"ok": False, "error": "postgres_unavailable"}
    _reject_sqlite_validation(db_path=db_path, sqlite_compare=sqlite_compare)
    return _pg_only_failed_ingest_validation_report(recent_limit=recent_limit)


def users_validation_report(
    recent_limit: int = 200,
    event_limit: int = 5000,
    *,
    db_path: str | None = None,
    sqlite_compare: bool = False,
) -> dict:
    if not postgres_available():
        return {"ok": False, "error": "postgres_unavailable"}
    _reject_sqlite_validation(db_path=db_path, sqlite_compare=sqlite_compare)
    return _pg_only_users_validation_report(recent_limit=recent_limit, event_limit=event_limit)


def lots_validation_report(
    recent_limit: int = 200,
    duplicate_limit: int = 2000,
    *,
    db_path: str | None = None,
    sqlite_compare: bool = False,
) -> dict:
    if not postgres_available():
        return {"ok": False, "error": "postgres_unavailable"}
    _reject_sqlite_validation(db_path=db_path, sqlite_compare=sqlite_compare)
    return _pg_only_lots_validation_report(recent_limit=recent_limit, duplicate_limit=duplicate_limit)
