"""
Materialized spectator fact tables built from reconciled stream state.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone

from .config import POSTGRES_SIDECAR_SCHEMA
from .events_db import (
    get_all_streams,
    get_competitor_listings,
    get_stream_event_summary,
    get_stream_reconciled_state,
)
from .postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, postgres_available


RECONCILER_SQLITE_RUNTIME_RETIRED = "reconciler_sqlite_runtime_retired"


def _use_postgres_backend(db_path=None):
    if db_path:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)
    return True


def _require_postgres_backend(db_path=None):
    if db_path:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)
    if not postgres_available():
        raise RuntimeError("reconciler_postgres_unavailable")


def _fetchall_dict_pg(cur):
    cols = [desc[0] for desc in (cur.description or [])]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetchone_dict_pg(cur):
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip((desc[0] for desc in cur.description or []), row))


def ensure_reconciler_postgres_schema() -> bool:
    if not _use_postgres_backend():
        return False
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.fact_lots (
                    id BIGSERIAL PRIMARY KEY,
                    stream_id BIGINT NOT NULL,
                    stream_url TEXT,
                    streamer_name TEXT,
                    lot_key TEXT NOT NULL,
                    lot_number TEXT,
                    opened_at TEXT,
                    closed_at TEXT,
                    resolved_product_name TEXT,
                    resolved_brand TEXT,
                    winner_username TEXT,
                    sale_price DOUBLE PRECISION DEFAULT 0,
                    last_bid DOUBLE PRECISION,
                    confidence_score DOUBLE PRECISION DEFAULT 0,
                    confidence_label TEXT,
                    source_flags_json TEXT,
                    anomaly_flags_json TEXT,
                    raw_lot_title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(stream_id, lot_key)
                )
                """
            )
            cur.execute(
                f"""
                DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.fact_lots fl
                USING {POSTGRES_SIDECAR_SCHEMA}.fact_lots newer
                WHERE fl.stream_id = newer.stream_id
                  AND fl.lot_key = newer.lot_key
                  AND fl.id < newer.id
                """
            )
            cur.execute(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_lots_stream_lot_key
                ON {POSTGRES_SIDECAR_SCHEMA}.fact_lots(stream_id, lot_key)
                """
            )
            cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.fact_lots_id_seq")
            cur.execute(
                f"""
                ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.fact_lots
                ALTER COLUMN id SET DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.fact_lots_id_seq'::regclass)
                """
            )
            cur.execute(
                f"""
                SELECT setval(
                    '{POSTGRES_SIDECAR_SCHEMA}.fact_lots_id_seq'::regclass,
                    GREATEST(COALESCE((SELECT MAX(id) FROM {POSTGRES_SIDECAR_SCHEMA}.fact_lots), 0), 1),
                    true
                )
                """
            )
            cur.execute(
                f"""
                ALTER SEQUENCE {POSTGRES_SIDECAR_SCHEMA}.fact_lots_id_seq
                OWNED BY {POSTGRES_SIDECAR_SCHEMA}.fact_lots.id
                """
            )
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_lots_stream_id ON {POSTGRES_SIDECAR_SCHEMA}.fact_lots(stream_id)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_lots_streamer_name ON {POSTGRES_SIDECAR_SCHEMA}.fact_lots(streamer_name)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_lots_closed_at ON {POSTGRES_SIDECAR_SCHEMA}.fact_lots(closed_at DESC)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_lots_confidence ON {POSTGRES_SIDECAR_SCHEMA}.fact_lots(confidence_label)")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.stream_health (
                    stream_id BIGINT PRIMARY KEY,
                    stream_url TEXT,
                    streamer_name TEXT,
                    status TEXT,
                    last_event_at TEXT,
                    last_chat_at TEXT,
                    last_winner_at TEXT,
                    last_bid_at TEXT,
                    last_lot_at TEXT,
                    last_viewer_at TEXT,
                    stale_seconds DOUBLE PRECISION,
                    restart_count BIGINT DEFAULT 0,
                    total_events BIGINT DEFAULT 0,
                    non_viewer_events BIGINT DEFAULT 0,
                    active_lot_json TEXT,
                    anomalies_json TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams (
                    stream_id BIGINT NOT NULL,
                    stream_url TEXT,
                    streamer_name TEXT,
                    username TEXT NOT NULL,
                    chat_messages BIGINT DEFAULT 0,
                    bids BIGINT DEFAULT 0,
                    lots_won BIGINT DEFAULT 0,
                    total_spend DOUBLE PRECISION DEFAULT 0,
                    avg_sale_price DOUBLE PRECISION DEFAULT 0,
                    first_seen TEXT,
                    last_seen TEXT,
                    buyer_tier TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (stream_id, username)
                )
                """
            )
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_buyer_streams_stream_id ON {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams(stream_id)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_buyer_streams_streamer_name ON {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams(streamer_name)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_buyer_streams_username ON {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams(username)")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.fact_buyers (
                    username TEXT PRIMARY KEY,
                    streams_seen BIGINT DEFAULT 0,
                    lots_won BIGINT DEFAULT 0,
                    total_spend DOUBLE PRECISION DEFAULT 0,
                    avg_sale_price DOUBLE PRECISION DEFAULT 0,
                    chat_messages BIGINT DEFAULT 0,
                    bids BIGINT DEFAULT 0,
                    first_seen TEXT,
                    last_seen TEXT,
                    buyer_tier TEXT,
                    cross_stream_score DOUBLE PRECISION DEFAULT 0,
                    streamers_json TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_buyers_tier ON {POSTGRES_SIDECAR_SCHEMA}.fact_buyers(buyer_tier)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_buyers_spend ON {POSTGRES_SIDECAR_SCHEMA}.fact_buyers(total_spend DESC)")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.fact_products (
                    stream_id BIGINT NOT NULL,
                    stream_url TEXT,
                    streamer_name TEXT,
                    product_key TEXT NOT NULL,
                    product_name TEXT,
                    brand TEXT,
                    times_sold BIGINT DEFAULT 0,
                    total_revenue DOUBLE PRECISION DEFAULT 0,
                    avg_sale_price DOUBLE PRECISION DEFAULT 0,
                    median_sale_price DOUBLE PRECISION DEFAULT 0,
                    demand_score DOUBLE PRECISION DEFAULT 0,
                    resolver_confidence_avg DOUBLE PRECISION DEFAULT 0,
                    first_seen TEXT,
                    last_seen TEXT,
                    last_buyer TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (stream_id, product_key)
                )
                """
            )
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_products_stream_id ON {POSTGRES_SIDECAR_SCHEMA}.fact_products(stream_id)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_products_streamer_name ON {POSTGRES_SIDECAR_SCHEMA}.fact_products(streamer_name)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_fact_products_sold ON {POSTGRES_SIDECAR_SCHEMA}.fact_products(times_sold DESC)")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals (
                    id BIGSERIAL PRIMARY KEY,
                    stream_id BIGINT NOT NULL,
                    streamer_name TEXT,
                    signal_type TEXT NOT NULL,
                    signal_key TEXT NOT NULL,
                    signal_score DOUBLE PRECISION DEFAULT 0,
                    signal_label TEXT,
                    reason TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(stream_id, signal_type, signal_key)
                )
                """
            )
            cur.execute(
                f"""
                DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals old
                USING {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals newer
                WHERE old.stream_id = newer.stream_id
                  AND old.signal_type = newer.signal_type
                  AND old.signal_key = newer.signal_key
                  AND old.id < newer.id
                """
            )
            cur.execute(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_intelligence_signals_stream_type_key
                ON {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals(stream_id, signal_type, signal_key)
                """
            )
            cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals_id_seq")
            cur.execute(
                f"""
                ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals
                ALTER COLUMN id SET DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.intelligence_signals_id_seq'::regclass)
                """
            )
            cur.execute(
                f"""
                SELECT setval(
                    '{POSTGRES_SIDECAR_SCHEMA}.intelligence_signals_id_seq'::regclass,
                    GREATEST(COALESCE((SELECT MAX(id) FROM {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals), 0), 1),
                    true
                )
                """
            )
            cur.execute(
                f"""
                ALTER SEQUENCE {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals_id_seq
                OWNED BY {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals.id
                """
            )
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_intelligence_signals_stream_id ON {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals(stream_id)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_intelligence_signals_type ON {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals(signal_type)")
        conn.commit()
    return True


def ensure_fact_tables(db_path=None):
    if _use_postgres_backend(db_path=db_path):
        _require_postgres_backend(db_path=db_path)
        return ensure_reconciler_postgres_schema()
    raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _lot_key(row):
    lot_number = str(row.get("lot_number") or "").strip()
    if lot_number:
        return f"lot:{lot_number}"
    sold_at = str(row.get("sold_at") or "").strip()
    winner = str(row.get("winner_username") or "").strip().lower()
    price = f"{float(row.get('sale_price') or 0):.2f}"
    product = str(row.get("product_name") or "").strip().lower()
    return f"fallback:{sold_at}|{winner}|{price}|{product}"


def _buyer_tier(total_spend, lots_won, bids=0, chat_messages=0):
    spent = float(total_spend or 0)
    wins = int(lots_won or 0)
    if spent >= 750:
        return "whale"
    if spent >= 200:
        return "heavy"
    if wins > 0:
        return "buyer"
    if int(bids or 0) > 0:
        return "bidder"
    if int(chat_messages or 0) > 0:
        return "chatter"
    return "unknown"


def _buyer_cross_stream_score(streams_seen, lots_won, total_spend, chat_messages=0):
    return round(
        min(100.0, (float(streams_seen or 0) * 18.0) + (float(lots_won or 0) * 2.5) + (float(total_spend or 0) / 20.0) + (float(chat_messages or 0) * 0.2)),
        1,
    )


def _aggregate_stream_buyers(stream_id, db_path=None):
    if _use_postgres_backend(db_path=db_path):
        ensure_wave1_postgres_schema()
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, stream_url, streamer_name
                    FROM {POSTGRES_SIDECAR_SCHEMA}.streams
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (int(stream_id),),
                )
                stream_meta = _fetchone_dict_pg(cur)
                cur.execute(
                    f"""
                    SELECT event_type, payload, created_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE stream_id = %s
                      AND event_type IN ('chat_message', 'auction_winner', 'bid_update')
                    ORDER BY id ASC
                    """,
                    (int(stream_id),),
                )
                rows = _fetchall_dict_pg(cur)
    else:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

    stream_data = dict(stream_meta or {})
    buyer_map = {}
    for row in rows:
        event_type = row["event_type"]
        created_at = row["created_at"]
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        roles = []
        if event_type == "chat_message":
            username = (
                payload.get("username")
                or payload.get("user")
                or payload.get("sender")
                or payload.get("display_username")
            )
            if username:
                roles.append((str(username).strip().lower(), "chat"))
        elif event_type == "bid_update":
            username = (
                payload.get("bidder")
                or payload.get("username")
                or payload.get("user")
                or payload.get("display_username")
            )
            if username:
                roles.append((str(username).strip().lower(), "bidder"))
        elif event_type == "auction_winner":
            username = (
                payload.get("winner")
                or payload.get("username")
                or payload.get("user")
                or payload.get("display_username")
            )
            if username:
                roles.append((str(username).strip().lower(), "winner"))
        for username, role in roles:
            if not username:
                continue
            rec = buyer_map.setdefault(username, {
                "username": username,
                "chat_messages": 0,
                "bids": 0,
                "lots_won": 0,
                "total_spend": 0.0,
                "first_seen": None,
                "last_seen": None,
            })
            if role == "chat":
                rec["chat_messages"] += 1
            elif role == "bidder":
                rec["bids"] += 1
            elif role == "winner":
                price = 0.0
                try:
                    price = float(payload.get("price_value") or payload.get("price") or 0)
                except Exception:
                    price = 0.0
                rec["lots_won"] += 1
                rec["total_spend"] = round(rec["total_spend"] + price, 2)
            if not rec["first_seen"] or (created_at and created_at < rec["first_seen"]):
                rec["first_seen"] = created_at
            if not rec["last_seen"] or (created_at and created_at > rec["last_seen"]):
                rec["last_seen"] = created_at
    return stream_data, list(buyer_map.values())


def _rebuild_fact_buyers(conn, usernames=None, use_postgres=False):
    if use_postgres:
        with conn.cursor() as cur:
            if usernames:
                normalized = sorted({str(u or "").strip().lower() for u in usernames if str(u or "").strip()})
                if not normalized:
                    return
                cur.execute(
                    f"""
                    SELECT username, streamer_name, stream_id, chat_messages, bids, lots_won, total_spend, first_seen, last_seen
                    FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams
                    WHERE username = ANY(%s)
                    ORDER BY username, streamer_name
                    """,
                    (normalized,),
                )
                rows = _fetchall_dict_pg(cur)
            else:
                cur.execute(
                    f"""
                    SELECT username, streamer_name, stream_id, chat_messages, bids, lots_won, total_spend, first_seen, last_seen
                    FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams
                    ORDER BY username, streamer_name
                    """
                )
                rows = _fetchall_dict_pg(cur)
    else:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

    buyer_map = defaultdict(lambda: {
        "username": "",
        "streams_seen": 0,
        "lots_won": 0,
        "total_spend": 0.0,
        "chat_messages": 0,
        "bids": 0,
        "first_seen": None,
        "last_seen": None,
        "streamers": [],
    })
    for row in rows:
        username = str(row["username"] or "").strip().lower()
        if not username:
            continue
        rec = buyer_map[username]
        rec["username"] = username
        rec["streams_seen"] += 1
        rec["lots_won"] += int(row["lots_won"] or 0)
        rec["total_spend"] = round(rec["total_spend"] + float(row["total_spend"] or 0), 2)
        rec["chat_messages"] += int(row["chat_messages"] or 0)
        rec["bids"] += int(row["bids"] or 0)
        rec["streamers"].append({
            "stream_id": row["stream_id"],
            "streamer_name": row["streamer_name"] or "",
            "spent": round(float(row["total_spend"] or 0), 2),
            "wins": int(row["lots_won"] or 0),
        })
        first_seen = row["first_seen"]
        last_seen = row["last_seen"]
        if not rec["first_seen"] or (first_seen and first_seen < rec["first_seen"]):
            rec["first_seen"] = first_seen
        if not rec["last_seen"] or (last_seen and last_seen > rec["last_seen"]):
            rec["last_seen"] = last_seen

    now = _utc_now_iso()
    if use_postgres:
        with conn.cursor() as cur:
            if usernames:
                normalized = sorted({str(u or "").strip().lower() for u in usernames if str(u or "").strip()})
                if normalized:
                    cur.execute(
                        f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyers WHERE username = ANY(%s)",
                        (normalized,),
                    )
            else:
                cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyers")

            for username, rec in buyer_map.items():
                avg_sale = round((rec["total_spend"] / rec["lots_won"]), 2) if rec["lots_won"] else 0.0
                tier = _buyer_tier(rec["total_spend"], rec["lots_won"], bids=rec["bids"], chat_messages=rec["chat_messages"])
                cross_stream_score = _buyer_cross_stream_score(rec["streams_seen"], rec["lots_won"], rec["total_spend"], chat_messages=rec["chat_messages"])
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.fact_buyers (
                        username, streams_seen, lots_won, total_spend, avg_sale_price,
                        chat_messages, bids, first_seen, last_seen, buyer_tier,
                        cross_stream_score, streamers_json, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        username,
                        rec["streams_seen"],
                        rec["lots_won"],
                        rec["total_spend"],
                        avg_sale,
                        rec["chat_messages"],
                        rec["bids"],
                        rec["first_seen"],
                        rec["last_seen"],
                        tier,
                        cross_stream_score,
                        json.dumps(sorted(rec["streamers"], key=lambda item: (-item["spent"], -item["wins"], item["streamer_name"]))),
                        now,
                    ),
                )
        return


def materialize_stream_facts(stream_id, db_path=None):
    ensure_fact_tables(db_path=db_path)
    reconciled = get_stream_reconciled_state(stream_id, db_path=db_path, limit=500)
    event_summary = get_stream_event_summary(stream_id, db_path=db_path)
    streams = {int(row["id"]): row for row in get_all_streams(db_path=db_path)}
    stream_meta = streams.get(int(stream_id), {})
    now = _utc_now_iso()

    if _use_postgres_backend(db_path=db_path):
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                for row in reconciled.get("lots") or []:
                    anomaly_flags = {
                        "generic_title": bool(row.get("generic_title")),
                        "low_confidence": row.get("confidence") == "low",
                        "missing_product_name": not bool(row.get("product_name")),
                        "missing_winner": not bool(row.get("winner_username")),
                        "missing_price": float(row.get("sale_price") or 0) <= 0,
                    }
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.fact_lots (
                            stream_id, stream_url, streamer_name, lot_key, lot_number,
                            opened_at, closed_at, resolved_product_name, resolved_brand,
                            winner_username, sale_price, last_bid, confidence_score, confidence_label,
                            source_flags_json, anomaly_flags_json, raw_lot_title, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(stream_id, lot_key) DO UPDATE SET
                            stream_url=excluded.stream_url,
                            streamer_name=excluded.streamer_name,
                            lot_number=excluded.lot_number,
                            opened_at=excluded.opened_at,
                            closed_at=excluded.closed_at,
                            resolved_product_name=excluded.resolved_product_name,
                            resolved_brand=excluded.resolved_brand,
                            winner_username=excluded.winner_username,
                            sale_price=excluded.sale_price,
                            last_bid=excluded.last_bid,
                            confidence_score=excluded.confidence_score,
                            confidence_label=excluded.confidence_label,
                            source_flags_json=excluded.source_flags_json,
                            anomaly_flags_json=excluded.anomaly_flags_json,
                            raw_lot_title=excluded.raw_lot_title,
                            updated_at=excluded.updated_at
                        """,
                        (
                            int(stream_id),
                            stream_meta.get("stream_url"),
                            stream_meta.get("streamer_name"),
                            _lot_key(row),
                            row.get("lot_number"),
                            None,
                            row.get("sold_at"),
                            row.get("product_name"),
                            None,
                            row.get("winner_username"),
                            float(row.get("sale_price") or 0),
                            None,
                            float(row.get("confidence_score") or 0),
                            row.get("confidence"),
                            json.dumps(row.get("confidence_reasons") or []),
                            json.dumps(anomaly_flags),
                            row.get("product_name"),
                            now,
                            now,
                        ),
                    )

                health = reconciled.get("health") or {}
                raw = health.get("raw") or {}
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.stream_health (
                        stream_id, stream_url, streamer_name, status, last_event_at, last_chat_at,
                        last_winner_at, last_bid_at, last_lot_at, last_viewer_at, stale_seconds,
                        restart_count, total_events, non_viewer_events, active_lot_json, anomalies_json, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(stream_id) DO UPDATE SET
                        stream_url=excluded.stream_url,
                        streamer_name=excluded.streamer_name,
                        status=excluded.status,
                        last_event_at=excluded.last_event_at,
                        last_chat_at=excluded.last_chat_at,
                        last_winner_at=excluded.last_winner_at,
                        last_bid_at=excluded.last_bid_at,
                        last_lot_at=excluded.last_lot_at,
                        last_viewer_at=excluded.last_viewer_at,
                        stale_seconds=excluded.stale_seconds,
                        total_events=excluded.total_events,
                        non_viewer_events=excluded.non_viewer_events,
                        active_lot_json=excluded.active_lot_json,
                        anomalies_json=excluded.anomalies_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        int(stream_id),
                        stream_meta.get("stream_url"),
                        stream_meta.get("streamer_name"),
                        health.get("status"),
                        raw.get("last_event_at"),
                        raw.get("chat_message"),
                        raw.get("auction_winner"),
                        raw.get("bid_update"),
                        raw.get("lot_update"),
                        raw.get("live_viewers"),
                        float(health.get("last_event_age_sec") or 0),
                        0,
                        int(raw.get("total_events") or 0),
                        int(event_summary.get("non_viewer_event_count") or 0),
                        json.dumps(reconciled.get("active_lot") or {}),
                        json.dumps(reconciled.get("anomalies") or {}),
                        now,
                    ),
                )
            conn.commit()
        return reconciled

    raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

def materialize_stream_buyer_facts(stream_id, db_path=None):
    ensure_fact_tables(db_path=db_path)
    stream_meta, buyers = _aggregate_stream_buyers(stream_id, db_path=db_path)
    now = _utc_now_iso()

    if _use_postgres_backend(db_path=db_path):
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT username FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams WHERE stream_id = %s",
                    (int(stream_id),),
                )
                previous_rows = _fetchall_dict_pg(cur)
                previous_usernames = {
                    str(row.get("username") or "").strip().lower()
                    for row in previous_rows
                    if str(row.get("username") or "").strip()
                }
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams WHERE stream_id = %s",
                    (int(stream_id),),
                )
                touched_usernames = []
                for row in buyers:
                    username = str(row.get("username") or "").strip().lower()
                    if not username:
                        continue
                    touched_usernames.append(username)
                    lots_won = int(row.get("lots_won") or 0)
                    total_spend = round(float(row.get("total_spend") or 0), 2)
                    avg_sale = round((total_spend / lots_won), 2) if lots_won else 0.0
                    buyer_tier = _buyer_tier(total_spend, lots_won, bids=row.get("bids"), chat_messages=row.get("chat_messages"))
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams (
                            stream_id, stream_url, streamer_name, username, chat_messages, bids,
                            lots_won, total_spend, avg_sale_price, first_seen, last_seen, buyer_tier, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(stream_id),
                            stream_meta.get("stream_url"),
                            stream_meta.get("streamer_name"),
                            username,
                            int(row.get("chat_messages") or 0),
                            int(row.get("bids") or 0),
                            lots_won,
                            total_spend,
                            avg_sale,
                            row.get("first_seen"),
                            row.get("last_seen"),
                            buyer_tier,
                            now,
                        ),
                    )
            _rebuild_fact_buyers(conn, usernames=(previous_usernames | set(touched_usernames)), use_postgres=True)
            conn.commit()
        return buyers

    raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

def materialize_stream_product_facts(stream_id, db_path=None):
    ensure_fact_tables(db_path=db_path)
    reconciled = get_stream_reconciled_state(stream_id, db_path=db_path, limit=500)
    streams = {int(row["id"]): row for row in get_all_streams(db_path=db_path)}
    stream_meta = streams.get(int(stream_id), {})
    now = _utc_now_iso()

    product_map = {}
    for row in reconciled.get("lots") or []:
        product_name = str(row.get("product_name") or row.get("raw_lot_title") or "").strip() or "Unknown product"
        product_key = product_name.strip().lower()
        if not product_key:
            continue
        rec = product_map.setdefault(product_key, {
            "product_key": product_key,
            "product_name": product_name,
            "brand": None,
            "times_sold": 0,
            "total_revenue": 0.0,
            "prices": [],
            "confidence_scores": [],
            "first_seen": None,
            "last_seen": None,
            "last_buyer": "",
        })
        price = float(row.get("sale_price") or 0)
        sold_at = row.get("sold_at")
        rec["times_sold"] += 1
        rec["total_revenue"] = round(rec["total_revenue"] + price, 2)
        rec["prices"].append(price)
        rec["confidence_scores"].append(float(row.get("confidence_score") or 0))
        if not rec["first_seen"] or (sold_at and sold_at < rec["first_seen"]):
            rec["first_seen"] = sold_at
        if not rec["last_seen"] or (sold_at and sold_at > rec["last_seen"]):
            rec["last_seen"] = sold_at
            rec["last_buyer"] = row.get("winner_username") or rec["last_buyer"]

    if _use_postgres_backend(db_path=db_path):
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.fact_products WHERE stream_id = %s",
                    (int(stream_id),),
                )
                for rec in product_map.values():
                    prices = sorted(rec["prices"])
                    if prices:
                        mid = len(prices) // 2
                        if len(prices) % 2:
                            median_price = prices[mid]
                        else:
                            median_price = round((prices[mid - 1] + prices[mid]) / 2, 2)
                    else:
                        median_price = 0.0
                    avg_sale_price = round((rec["total_revenue"] / rec["times_sold"]), 2) if rec["times_sold"] else 0.0
                    confidence_avg = round(
                        sum(rec["confidence_scores"]) / len(rec["confidence_scores"]),
                        3,
                    ) if rec["confidence_scores"] else 0.0
                    demand_score = round((rec["times_sold"] * 12.0) + (rec["total_revenue"] / 10.0) + (confidence_avg * 25.0), 1)
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.fact_products (
                            stream_id, stream_url, streamer_name, product_key, product_name, brand,
                            times_sold, total_revenue, avg_sale_price, median_sale_price,
                            demand_score, resolver_confidence_avg, first_seen, last_seen, last_buyer, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(stream_id),
                            stream_meta.get("stream_url"),
                            stream_meta.get("streamer_name"),
                            rec["product_key"],
                            rec["product_name"],
                            rec["brand"],
                            rec["times_sold"],
                            rec["total_revenue"],
                            avg_sale_price,
                            median_price,
                            demand_score,
                            confidence_avg,
                            rec["first_seen"],
                            rec["last_seen"],
                            rec["last_buyer"],
                            now,
                        ),
                    )
            conn.commit()
        return list(product_map.values())

    raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

def materialize_recent_stream_facts(limit=25, db_path=None):
    streams = get_all_streams(db_path=db_path)
    updated = []
    for stream in streams[: max(1, int(limit))]:
        try:
            materialize_stream_facts(int(stream["id"]), db_path=db_path)
            updated.append(int(stream["id"]))
        except Exception:
            continue
    return updated


def materialize_streamer_facts(streamer_name, limit=5, db_path=None):
    target = str(streamer_name or "").strip().lower()
    if not target:
        return []
    streams = [
        row for row in get_all_streams(db_path=db_path)
        if str(row.get("streamer_name") or "").strip().lower() == target
    ]
    updated = []
    for stream in streams[: max(1, int(limit))]:
        try:
            materialize_stream_facts(int(stream["id"]), db_path=db_path)
            updated.append(int(stream["id"]))
        except Exception:
            continue
    return updated


def materialize_recent_stream_buyer_facts(limit=25, db_path=None):
    streams = get_all_streams(db_path=db_path)
    updated = []
    for stream in streams[: max(1, int(limit))]:
        try:
            materialize_stream_buyer_facts(int(stream["id"]), db_path=db_path)
            updated.append(int(stream["id"]))
        except Exception:
            continue
    return updated


def materialize_streamer_buyer_facts(streamer_name, limit=5, db_path=None):
    target = str(streamer_name or "").strip().lower()
    if not target:
        return []
    streams = [
        row for row in get_all_streams(db_path=db_path)
        if str(row.get("streamer_name") or "").strip().lower() == target
    ]
    updated = []
    for stream in streams[: max(1, int(limit))]:
        try:
            materialize_stream_buyer_facts(int(stream["id"]), db_path=db_path)
            updated.append(int(stream["id"]))
        except Exception:
            continue
    return updated


def materialize_recent_stream_product_facts(limit=25, db_path=None):
    streams = get_all_streams(db_path=db_path)
    updated = []
    for stream in streams[: max(1, int(limit))]:
        try:
            materialize_stream_product_facts(int(stream["id"]), db_path=db_path)
            updated.append(int(stream["id"]))
        except Exception:
            continue
    return updated


def materialize_streamer_product_facts(streamer_name, limit=5, db_path=None):
    target = str(streamer_name or "").strip().lower()
    if not target:
        return []
    streams = [
        row for row in get_all_streams(db_path=db_path)
        if str(row.get("streamer_name") or "").strip().lower() == target
    ]
    updated = []
    for stream in streams[: max(1, int(limit))]:
        try:
            materialize_stream_product_facts(int(stream["id"]), db_path=db_path)
            updated.append(int(stream["id"]))
        except Exception:
            continue
    return updated


def materialize_stream_intelligence(stream_id, db_path=None):
    ensure_fact_tables(db_path=db_path)
    # Refresh supporting fact layers first so signals stay aligned with stable facts.
    materialize_stream_facts(stream_id, db_path=db_path)
    materialize_stream_buyer_facts(stream_id, db_path=db_path)
    materialize_stream_product_facts(stream_id, db_path=db_path)

    now = _utc_now_iso()
    if _use_postgres_backend(db_path=db_path):
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT streamer_name, status, stale_seconds, total_events, non_viewer_events, anomalies_json
                    FROM {POSTGRES_SIDECAR_SCHEMA}.stream_health
                    WHERE stream_id = %s
                    LIMIT 1
                    """,
                    (int(stream_id),),
                )
                health = _fetchone_dict_pg(cur)
                cur.execute(
                    f"""
                    SELECT product_name, times_sold, total_revenue, avg_sale_price, median_sale_price,
                           demand_score, resolver_confidence_avg, last_buyer
                    FROM {POSTGRES_SIDECAR_SCHEMA}.fact_products
                    WHERE stream_id = %s
                    ORDER BY times_sold DESC, total_revenue DESC, demand_score DESC
                    LIMIT 12
                    """,
                    (int(stream_id),),
                )
                products = _fetchall_dict_pg(cur)
                cur.execute(
                    f"""
                    SELECT username, chat_messages, bids, lots_won, total_spend, avg_sale_price, buyer_tier
                    FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams
                    WHERE stream_id = %s
                    ORDER BY total_spend DESC, lots_won DESC, chat_messages DESC
                    LIMIT 20
                    """,
                    (int(stream_id),),
                )
                buyers = _fetchall_dict_pg(cur)
        listings_payload = get_competitor_listings(int(stream_id), db_path=db_path) or {}
    else:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

    health_row = dict(health) if health else {}
    streamer_name = str(health_row.get("streamer_name") or "").strip()
    anomalies = {}
    try:
        anomalies = json.loads(health_row.get("anomalies_json") or "{}") if health_row else {}
    except Exception:
        anomalies = {}

    signals = []

    # Stream quality
    status = str(health_row.get("status") or "unknown").lower()
    stale_seconds = float(health_row.get("stale_seconds") or 0)
    total_events = int(health_row.get("total_events") or 0)
    non_viewer_events = int(health_row.get("non_viewer_events") or 0)
    duplicate_winners = int((anomalies or {}).get("duplicate_winner_signals") or 0)
    generic_titles = int((anomalies or {}).get("generic_product_titles") or 0)
    quality_score = 50.0
    if status == "healthy":
        quality_score += 28
    elif status == "degraded":
        quality_score += 10
    elif status == "stale":
        quality_score -= 18
    quality_score += min(15.0, non_viewer_events / 20.0)
    quality_score -= min(18.0, stale_seconds / 25.0)
    quality_score -= min(10.0, duplicate_winners * 2.0)
    quality_score -= min(8.0, generic_titles * 0.35)
    quality_score = round(max(0.0, min(100.0, quality_score)), 1)
    quality_label = "strong" if quality_score >= 75 else "watch" if quality_score >= 50 else "weak"
    signals.append({
        "signal_type": "stream_quality",
        "signal_key": "overall",
        "signal_score": quality_score,
        "signal_label": quality_label,
        "reason": f"{status} stream · {non_viewer_events} non-viewer events · stale {int(round(stale_seconds or 0))}s",
        "payload": {
            "status": status,
            "stale_seconds": stale_seconds,
            "total_events": total_events,
            "non_viewer_events": non_viewer_events,
            "duplicate_winner_signals": duplicate_winners,
            "generic_product_titles": generic_titles,
        },
    })

    # Product hotness
    for row in products[:5]:
        score = round(max(0.0, min(100.0, float(row["demand_score"] or 0))), 1)
        signals.append({
            "signal_type": "product_hotness",
            "signal_key": str(row["product_name"] or "unknown").strip().lower(),
            "signal_score": score,
            "signal_label": "hot" if score >= 75 else "active" if score >= 45 else "watch",
            "reason": f"{int(row['times_sold'] or 0)} sold · avg {float(row['avg_sale_price'] or 0):.2f} · conf {float(row['resolver_confidence_avg'] or 0):.2f}",
            "payload": {
                "product_name": row["product_name"],
                "times_sold": int(row["times_sold"] or 0),
                "total_revenue": float(row["total_revenue"] or 0),
                "avg_sale_price": float(row["avg_sale_price"] or 0),
                "median_sale_price": float(row["median_sale_price"] or 0),
                "resolver_confidence_avg": float(row["resolver_confidence_avg"] or 0),
                "last_buyer": row["last_buyer"],
            },
        })

    # Buyer intent
    for row in buyers[:5]:
        score = round(
            max(
                0.0,
                min(
                    100.0,
                    (float(row["total_spend"] or 0) / 10.0)
                    + (float(row["lots_won"] or 0) * 10.0)
                    + (float(row["chat_messages"] or 0) * 0.8)
                    + (float(row["bids"] or 0) * 2.0),
                ),
            ),
            1,
        )
        signals.append({
            "signal_type": "buyer_intent",
            "signal_key": str(row["username"] or "").strip().lower(),
            "signal_score": score,
            "signal_label": "hot" if score >= 75 else "active" if score >= 40 else "watch",
            "reason": f"{float(row['total_spend'] or 0):.2f} spend · {int(row['lots_won'] or 0)} wins · {int(row['chat_messages'] or 0)} chats",
            "payload": {
                "username": row["username"],
                "total_spend": float(row["total_spend"] or 0),
                "lots_won": int(row["lots_won"] or 0),
                "chat_messages": int(row["chat_messages"] or 0),
                "bids": int(row["bids"] or 0),
                "avg_sale_price": float(row["avg_sale_price"] or 0),
                "buyer_tier": row["buyer_tier"],
            },
        })

    # Price opportunity from visible catalog vs realized fact prices
    listings = listings_payload.get("listings") or []
    listings_by_name = {
        str(item.get("product_name") or "").strip().lower(): item
        for item in listings
        if str(item.get("product_name") or "").strip()
    }
    for row in products[:8]:
        name_key = str(row["product_name"] or "").strip().lower()
        listing = listings_by_name.get(name_key)
        if not listing:
            continue
        starting_price = float(listing.get("starting_price") or 0)
        avg_sale = float(row["avg_sale_price"] or 0)
        if starting_price <= 0 or avg_sale <= 0:
            continue
        uplift = round(avg_sale - starting_price, 2)
        uplift_pct = round((uplift / starting_price) * 100.0, 1) if starting_price else 0.0
        score = round(max(0.0, min(100.0, 50.0 + uplift_pct)), 1)
        signals.append({
            "signal_type": "price_opportunity",
            "signal_key": name_key,
            "signal_score": score,
            "signal_label": "undervalued" if uplift_pct >= 20 else "fair" if uplift_pct >= -10 else "overpriced",
            "reason": f"start {starting_price:.2f} vs realized {avg_sale:.2f} ({uplift_pct:+.1f}%)",
            "payload": {
                "product_name": row["product_name"],
                "starting_price": starting_price,
                "avg_sale_price": avg_sale,
                "uplift": uplift,
                "uplift_pct": uplift_pct,
                "listing_type": listing.get("listing_type"),
            },
        })

    if _use_postgres_backend(db_path=db_path):
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals WHERE stream_id = %s",
                    (int(stream_id),),
                )
                for signal in signals:
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals (
                            stream_id, streamer_name, signal_type, signal_key, signal_score,
                            signal_label, reason, payload_json, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(stream_id),
                            streamer_name,
                            signal["signal_type"],
                            signal["signal_key"],
                            float(signal["signal_score"] or 0),
                            signal["signal_label"],
                            signal["reason"],
                            json.dumps(signal.get("payload") or {}),
                            now,
                            now,
                        ),
                    )
            conn.commit()
    else:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)
    return signals


def list_fact_lots(
    stream_id=None,
    streamer_name=None,
    confidence=None,
    from_ts=None,
    to_ts=None,
    limit=200,
    db_path=None,
):
    ensure_fact_tables(db_path=db_path)
    if _use_postgres_backend(db_path=db_path):
        where = ["1=1"]
        params = []
        if stream_id:
            where.append("stream_id = %s")
            params.append(int(stream_id))
        if streamer_name:
            where.append("LOWER(streamer_name) = %s")
            params.append(str(streamer_name).strip().lower())
        if confidence:
            where.append("confidence_label = %s")
            params.append(str(confidence).strip().lower())
        if from_ts:
            where.append("COALESCE(closed_at, updated_at) >= %s")
            params.append(from_ts)
        if to_ts:
            where.append("COALESCE(closed_at, updated_at) <= %s")
            params.append(to_ts)
        params.append(max(1, min(int(limit), 2000)))
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, stream_id, stream_url, streamer_name, lot_key, lot_number, opened_at, closed_at,
                           resolved_product_name, resolved_brand, winner_username, sale_price, last_bid,
                           confidence_score, confidence_label, source_flags_json, anomaly_flags_json,
                           raw_lot_title, created_at, updated_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.fact_lots
                    WHERE {' AND '.join(where)}
                    ORDER BY COALESCE(closed_at, updated_at) DESC, id DESC
                    LIMIT %s
                    """,
                    params,
                )
                rows = _fetchall_dict_pg(cur)
    else:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

    items = []
    for row in rows:
        item = dict(row)
        for key in ("source_flags_json", "anomaly_flags_json"):
            try:
                item[key.replace("_json", "")] = json.loads(item.pop(key) or "[]")
            except Exception:
                item[key.replace("_json", "")] = []
                item.pop(key, None)
        items.append(item)
    return items


def list_fact_buyers(
    stream_id=None,
    streamer_name=None,
    tier=None,
    q=None,
    min_spend=0,
    limit=200,
    db_path=None,
):
    ensure_fact_tables(db_path=db_path)
    if _use_postgres_backend(db_path=db_path):
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                if stream_id:
                    where = ["stream_id = %s"]
                    params = [int(stream_id)]
                    if tier:
                        where.append("buyer_tier = %s")
                        params.append(str(tier).strip().lower())
                    if q:
                        where.append("username LIKE %s")
                        params.append(f"%{str(q).strip().lower()}%")
                    if min_spend:
                        where.append("total_spend >= %s")
                        params.append(float(min_spend))
                    params.append(max(1, min(int(limit), 2000)))
                    cur.execute(
                        f"""
                        SELECT
                            username,
                            1 AS streams_seen,
                            lots_won,
                            total_spend,
                            avg_sale_price,
                            chat_messages,
                            bids,
                            first_seen,
                            last_seen,
                            buyer_tier,
                            0.0 AS cross_stream_score,
                            '[]' AS streamers_json
                        FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams
                        WHERE {' AND '.join(where)}
                        ORDER BY total_spend DESC, lots_won DESC, chat_messages DESC, username ASC
                        LIMIT %s
                        """,
                        params,
                    )
                    rows = _fetchall_dict_pg(cur)
                elif streamer_name:
                    where = ["LOWER(streamer_name) = %s"]
                    params = [str(streamer_name).strip().lower()]
                    if tier:
                        where.append("buyer_tier = %s")
                        params.append(str(tier).strip().lower())
                    if q:
                        where.append("username LIKE %s")
                        params.append(f"%{str(q).strip().lower()}%")
                    if min_spend:
                        where.append("total_spend >= %s")
                        params.append(float(min_spend))
                    params.append(max(1, min(int(limit), 2000)))
                    cur.execute(
                        f"""
                        SELECT
                            username,
                            COUNT(*) AS streams_seen,
                            SUM(lots_won) AS lots_won,
                            ROUND(SUM(total_spend)::numeric, 2) AS total_spend,
                            ROUND((CASE WHEN SUM(lots_won) > 0 THEN SUM(total_spend) / SUM(lots_won) ELSE 0 END)::numeric, 2) AS avg_sale_price,
                            SUM(chat_messages) AS chat_messages,
                            SUM(bids) AS bids,
                            MIN(first_seen) AS first_seen,
                            MAX(last_seen) AS last_seen,
                            MAX(buyer_tier) AS buyer_tier,
                            string_agg(DISTINCT streamer_name, ',' ORDER BY streamer_name) AS streamers_csv
                        FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyer_streams
                        WHERE {' AND '.join(where)}
                        GROUP BY username
                        ORDER BY total_spend DESC, lots_won DESC, chat_messages DESC, username ASC
                        LIMIT %s
                        """,
                        params,
                    )
                    rows = _fetchall_dict_pg(cur)
                else:
                    where = ["1=1"]
                    params = []
                    if tier:
                        where.append("buyer_tier = %s")
                        params.append(str(tier).strip().lower())
                    if q:
                        where.append("username LIKE %s")
                        params.append(f"%{str(q).strip().lower()}%")
                    if min_spend:
                        where.append("total_spend >= %s")
                        params.append(float(min_spend))
                    params.append(max(1, min(int(limit), 2000)))
                    cur.execute(
                        f"""
                        SELECT
                            username,
                            streams_seen,
                            lots_won,
                            total_spend,
                            avg_sale_price,
                            chat_messages,
                            bids,
                            first_seen,
                            last_seen,
                            buyer_tier,
                            cross_stream_score,
                            streamers_json
                        FROM {POSTGRES_SIDECAR_SCHEMA}.fact_buyers
                        WHERE {' AND '.join(where)}
                        ORDER BY total_spend DESC, streams_seen DESC, lots_won DESC, username ASC
                        LIMIT %s
                        """,
                        params,
                    )
                    rows = _fetchall_dict_pg(cur)
    else:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)

    items = []
    for row in rows:
        item = dict(row)
        item["username"] = str(item.get("username") or "").strip().lower()
        if stream_id:
            item["cross_stream_score"] = 0.0
            item["streamers"] = []
            item.pop("streamers_json", None)
        elif streamer_name:
            streamers = [s.strip() for s in str(item.pop("streamers_csv") or "").split(",") if s.strip()]
            item["cross_stream_score"] = _buyer_cross_stream_score(
                item.get("streams_seen"),
                item.get("lots_won"),
                item.get("total_spend"),
                chat_messages=item.get("chat_messages"),
            )
            item["streamers"] = [{"streamer_name": name} for name in sorted(streamers)]
        else:
            try:
                item["streamers"] = json.loads(item.pop("streamers_json") or "[]")
            except Exception:
                item["streamers"] = []
                item.pop("streamers_json", None)
        item["total_wins"] = int(item.get("lots_won") or 0)
        item["messages"] = int(item.get("chat_messages") or 0)
        items.append(item)
    return items


def list_fact_products(
    stream_id=None,
    streamer_name=None,
    q=None,
    min_sold=0,
    limit=200,
    db_path=None,
):
    ensure_fact_tables(db_path=db_path)
    if _use_postgres_backend(db_path=db_path):
        where = ["1=1"]
        params = []
        if stream_id:
            where.append("stream_id = %s")
            params.append(int(stream_id))
        if streamer_name:
            where.append("LOWER(streamer_name) = %s")
            params.append(str(streamer_name).strip().lower())
        if q:
            where.append("(product_name LIKE %s OR product_key LIKE %s)")
            needle = f"%{str(q).strip().lower()}%"
            params.extend([needle, needle])
        if min_sold:
            where.append("times_sold >= %s")
            params.append(int(min_sold))
        params.append(max(1, min(int(limit), 2000)))
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        stream_id, stream_url, streamer_name, product_key, product_name, brand,
                        times_sold, total_revenue, avg_sale_price, median_sale_price, demand_score,
                        resolver_confidence_avg, first_seen, last_seen, last_buyer, updated_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.fact_products
                    WHERE {' AND '.join(where)}
                    ORDER BY times_sold DESC, total_revenue DESC, demand_score DESC, product_name ASC
                    LIMIT %s
                    """,
                    params,
                )
                rows = _fetchall_dict_pg(cur)
    else:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)
    return [dict(row) for row in rows]


def list_intelligence_signals(stream_id, signal_type=None, limit=100, db_path=None):
    ensure_fact_tables(db_path=db_path)
    if _use_postgres_backend(db_path=db_path):
        where = ["stream_id = %s"]
        params = [int(stream_id)]
        if signal_type:
            where.append("signal_type = %s")
            params.append(str(signal_type).strip().lower())
        params.append(max(1, min(int(limit), 500)))
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, stream_id, streamer_name, signal_type, signal_key, signal_score,
                           signal_label, reason, payload_json, created_at, updated_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.intelligence_signals
                    WHERE {' AND '.join(where)}
                    ORDER BY signal_type ASC, signal_score DESC, updated_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                rows = _fetchall_dict_pg(cur)
    else:
        raise RuntimeError(RECONCILER_SQLITE_RUNTIME_RETIRED)
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
        except Exception:
            item["payload"] = {}
            item.pop("payload_json", None)
        items.append(item)
    return items
