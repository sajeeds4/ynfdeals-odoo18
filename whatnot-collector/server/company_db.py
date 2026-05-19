"""
Local company database helpers for the app-owned company runtime.
"""

import os
import time
import uuid
import json
import re
import hashlib
import hmac
import secrets
import threading
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from math import isclose
from pathlib import Path

from .config import API_SECRET_KEY, DASHBOARD_JWT_SECRET, DASHBOARD_POS_TOKEN_PEPPER, DASHBOARD_POS_TOKEN_TTL_DAYS, DB_PATH, POSTGRES_SIDECAR_SCHEMA
from .postgres_cutover import (
    _pg_connect,
    _fetchone_dict_pg,
    domain_validate_enabled,
    ensure_wave1_postgres_schema,
    domain_primary_backend,
    log_cutover_event,
    postgres_available,
    pg_domain_tx,
)


COMPANY_SCHEMA = ""

FRAGRANCE_RESEARCH_PROFILE_FIELDS = (
    "accords",
    "fragrance_family",
    "fragrance_dna",
    "best_for_seasons",
    "best_for_occasions",
    "best_for_time_of_day",
    "longevity",
    "projection",
    "sillage",
    "compliment_factor",
    "mood_keywords",
    "similar_signature",
    "inspired_by_signature",
    "source_confidence",
    "source_summary",
    "verified_sources_count",
    "needs_manual_review",
    "last_researched_at",
)

TIKTOK_PRODUCT_FIELD_DEFS = {
    "tiktok_title": "TEXT",
    "tiktok_category_id": "TEXT",
    "tiktok_category_name": "TEXT",
    "tiktok_brand": "TEXT",
    "tiktok_search_keywords": "TEXT",
    "tiktok_image_urls": "TEXT",
    "tiktok_pack_type": "TEXT",
    "tiktok_scent": "TEXT",
    "tiktok_region_of_origin": "TEXT",
    "tiktok_product_form": "TEXT",
    "tiktok_edition": "TEXT",
    "tiktok_contains_alcohol_or_aerosol": "TEXT",
    "tiktok_manufacturer": "TEXT",
    "tiktok_shelf_life": "TEXT",
    "tiktok_inactive_ingredients": "TEXT",
    "tiktok_age_group": "TEXT",
    "tiktok_item_name": "TEXT",
    "tiktok_feature": "TEXT",
    "tiktok_fragrance_concentration": "TEXT",
    "tiktok_material_type_free": "TEXT",
    "tiktok_ingredients": "TEXT",
    "tiktok_container_type": "TEXT",
    "tiktok_allergen_information": "TEXT",
    "tiktok_ingredient_feature": "TEXT",
    "tiktok_volume": "TEXT",
    "tiktok_description": "TEXT",
    "tiktok_highlights": "TEXT",
    "tiktok_quantity": "REAL",
    "tiktok_retail_price": "REAL",
    "tiktok_seller_sku": "TEXT",
    "tiktok_ean": "TEXT",
    "tiktok_product_identifier_code_type": "TEXT",
    "tiktok_ca_prop_65_repro_chems": "TEXT",
    "tiktok_ca_prop_65_carcinogens": "TEXT",
    "tiktok_flammable_liquid": "TEXT",
    "tiktok_aerosols": "TEXT",
    "tiktok_dangerous_goods_or_hazardous_materials": "TEXT",
    "tiktok_environmental_feature": "TEXT",
    "tiktok_sds_file_path": "TEXT",
    "tiktok_package_weight_oz": "REAL",
    "tiktok_package_length_in": "REAL",
    "tiktok_package_width_in": "REAL",
    "tiktok_package_height_in": "REAL",
}

TIKTOK_PRODUCT_FIELDS = tuple(TIKTOK_PRODUCT_FIELD_DEFS.keys())

PRODUCT_LIST_SELECT_FIELDS = (
    "id", "name", "sku", "barcode", "category_id", "brand", "gender", "supplier_name", "storage_bin",
    "product_type", "cost_price", "raw_cost", "cost_plus_12", "cost_plus_20", "retail_price",
    "on_hand_qty", "low_stock_threshold", "active", "notes", "notes_verified", "notes_verified_at",
    "note_top", "note_mid", "note_base", "media_url", "description", "ingredients", "script",
    "dupe_inspiration", "dupe_confidence", "dupe_classification", "dupe_notes",
    "similar_to", "image_gallery_urls", "source_fragrantica_url", "source_jomashop_url",
    "source_parfumo_url", "source_official_url", "size_oz", "size_ml", "volume_oz", "volume_ml",
    *TIKTOK_PRODUCT_FIELDS,
    "created_at", "updated_at",
)
_COMPANY_DB_READY = False
_COMPANY_DB_READY_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row):
    return dict(row) if row is not None else None


def _fetchone_dict(conn, query, params=()):
    return _row_to_dict(conn.execute(query, params).fetchone())


def _fetchall_dict(conn, query, params=()):
    return [_row_to_dict(row) for row in conn.execute(query, params).fetchall()]


def _pg_fetchall_dict(cur):
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in rows]


def _to_pg_placeholders(query: str) -> str:
    return query.replace("?", "%s")


def _company_read_prefers_postgres(domain: str) -> bool:
    return postgres_available() and domain_primary_backend(domain) == "postgres"


def _require_company_postgres_runtime(domain: str) -> None:
    if not _company_read_prefers_postgres(domain):
        raise RuntimeError(f"company_db_postgres_runtime_required:{domain}")


def _normalize_company_read_value(value):
    if isinstance(value, Decimal):
        return round(float(value), 6)
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_company_read_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_company_read_value(val) for key, val in value.items()}
    return value


def _validate_company_read_parity(operation: str, legacy_value, postgres_value, context: dict | None = None) -> None:
    if _normalize_company_read_value(legacy_value) != _normalize_company_read_value(postgres_value):
        log_cutover_event(
            "company_db_reads",
            operation,
            "company_db",
            (context or {}).get("identifier"),
            {
                "context": context or {},
                "legacy_value": _normalize_company_read_value(legacy_value),
                "postgres_value": _normalize_company_read_value(postgres_value),
            },
        )


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _values_differ(before, after):
    if before == after:
        return False
    try:
        return not isclose(float(before), float(after), rel_tol=0.0, abs_tol=0.0001)
    except Exception:
        return True


def _write_inventory_audit(conn, product_id, event_type, source=None, actor=None, changed_fields=None, metadata=None):
    conn.execute(
        """
        INSERT INTO inventory_audit_log (
            product_id, event_type, source, actor, changed_fields, metadata, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(product_id),
            str(event_type or "unknown"),
            source or None,
            actor or None,
            _json_dumps(changed_fields or {}),
            _json_dumps(metadata or {}),
            utc_now(),
        ),
    )


def _ensure_column(conn, table, column, ddl):
    raise RuntimeError("company_db_sqlite_schema_migration_retired")


def _pos_token_pepper() -> bytes:
    pepper = (DASHBOARD_POS_TOKEN_PEPPER or DASHBOARD_JWT_SECRET or API_SECRET_KEY or "").strip()
    if pepper:
        return pepper.encode("utf-8")
    return f"local-dev-pos-token-pepper:{Path(DB_PATH).resolve()}".encode("utf-8")


def _hash_pos_token(token):
    clean = str(token or "").strip()
    if not clean:
        return ""
    return hmac.new(_pos_token_pepper(), clean.encode("utf-8"), hashlib.sha256).hexdigest()


def _default_pos_token_expires_at() -> str | None:
    days = max(int(DASHBOARD_POS_TOKEN_TTL_DAYS or 0), 0)
    if days <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _iso_is_past(value) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= datetime.now(timezone.utc)
    except Exception:
        return raw < utc_now()


def _public_pos_token_row(row, *, reveal_token=False):
    if not row:
        return row
    sanitized = dict(row)
    stored = str(sanitized.get("token") or "")
    if not reveal_token or stored.startswith("sha256:"):
        sanitized.pop("token", None)
    else:
        sanitized["token"] = stored
    sanitized.pop("token_hash", None)
    sanitized["expired"] = _iso_is_past(sanitized.get("expires_at"))
    return sanitized


def _normalize_sale_order_sources(conn):
    conn.execute(
        """
        UPDATE sale_orders
        SET order_source = 'tiktok_live'
        WHERE order_source = 'whatnot'
          AND session_id IN (
              SELECT id
              FROM company_sessions
              WHERE lower(coalesce(show_id, '')) LIKE 'tiktok:%'
          )
        """
    )


def _employee_name_key(value):
    return " ".join(str(value or "").strip().lower().split())


def _ensure_employee_account_policy_columns(conn):
    _ensure_column(conn, "employee_accounts", "auto_approve_in_house_orders", "auto_approve_in_house_orders INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "employee_accounts", "allow_self_service_returns", "allow_self_service_returns INTEGER NOT NULL DEFAULT 0")


def _ensure_employee_account_txn(conn, employee_name=None, employee_id=None):
    _ensure_employee_account_policy_columns(conn)
    now = utc_now()
    if employee_id not in (None, ""):
        row = _fetchone_dict(conn, "SELECT * FROM employee_accounts WHERE id = ?", (int(employee_id),))
        if not row:
            raise ValueError("employee account not found")
        return row
    clean_name = " ".join(str(employee_name or "").strip().split())
    if not clean_name:
        raise ValueError("employee_name required")
    name_key = _employee_name_key(clean_name)
    row = _fetchone_dict(conn, "SELECT * FROM employee_accounts WHERE name_key = ?", (name_key,))
    if row:
        if row.get("name") != clean_name:
            conn.execute(
                "UPDATE employee_accounts SET name = ?, updated_at = ? WHERE id = ?",
                (clean_name, now, row["id"]),
            )
            row["name"] = clean_name
        return row
    cur = conn.execute(
        """
        INSERT INTO employee_accounts (name, name_key, active, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?)
        """,
        (clean_name, name_key, now, now),
    )
    return _fetchone_dict(conn, "SELECT * FROM employee_accounts WHERE id = ?", (cur.lastrowid,))


def _create_in_house_sale_txn(conn, employee_name=None, employee_id=None, product_id=None, barcode=None, sku=None, qty=1, unit_price=None, notes=None, sold_at=None, order_id=None, order_line_id=None, record_inventory=True):
    qty = float(qty or 0)
    if qty <= 0:
        raise ValueError("qty must be greater than 0")
    product = get_product(int(product_id)) if product_id else None
    if not product and (barcode or sku):
        product = find_product_by_code(barcode or sku)
    if not product:
        raise ValueError("product not found")

    now = utc_now()
    sold_at = sold_at or now
    unit_cost = float(product.get("cost_price") or 0)
    unit_price = unit_cost if unit_price in (None, "") else float(unit_price or 0)
    subtotal = round(qty * unit_price, 2)
    total_cost = round(qty * unit_cost, 2)
    profit = round(subtotal - total_cost, 2)
    account = _ensure_employee_account_txn(conn, employee_name=employee_name, employee_id=employee_id)
    cur = conn.execute(
        """
        INSERT INTO in_house_sales (
            employee_id, employee_name, product_id, product_name, barcode, sku,
            qty, unit_cost, unit_price, subtotal, total_cost, profit,
            notes, sold_at, created_at, updated_at, order_id, order_line_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(account["id"]),
            account["name"],
            int(product["id"]),
            product.get("name"),
            product.get("barcode"),
            product.get("sku"),
            qty,
            unit_cost,
            unit_price,
            subtotal,
            total_cost,
            profit,
            notes,
            sold_at,
            now,
            now,
            int(order_id) if order_id else None,
            int(order_line_id) if order_line_id else None,
        ),
    )
    sale_id = cur.lastrowid
    conn.execute(
        "UPDATE employee_accounts SET last_sale_at = ?, updated_at = ? WHERE id = ?",
        (sold_at, now, int(account["id"])),
    )
    if record_inventory:
        _record_inventory_movement_txn(
            conn,
            int(product["id"]),
            "sale",
            -qty,
            reason="in_house_employee_sale",
            reference_type="in_house_sale",
            reference_id=sale_id,
        )
    return _fetchone_dict(conn, "SELECT * FROM in_house_sales WHERE id = ?", (sale_id,))


def _backfill_in_house_employee_accounts(conn):
    _ensure_column(conn, "in_house_sales", "employee_id", "employee_id INTEGER")
    rows = _fetchall_dict(
        conn,
        """
        SELECT id, employee_name, employee_id, sold_at
        FROM in_house_sales
        ORDER BY id ASC
        """,
    )
    for row in rows:
        account = None
        if row.get("employee_id"):
            account = _fetchone_dict(conn, "SELECT * FROM employee_accounts WHERE id = ?", (int(row["employee_id"]),))
        if not account:
            account = _ensure_employee_account_txn(conn, employee_name=row.get("employee_name"))
        sold_at = row.get("sold_at")
        conn.execute(
            """
            UPDATE in_house_sales
            SET employee_id = ?, employee_name = ?
            WHERE id = ?
            """,
            (account["id"], account["name"], int(row["id"])),
        )
        if sold_at:
            conn.execute(
                """
                UPDATE employee_accounts
                SET last_sale_at = CASE
                    WHEN COALESCE(last_sale_at, '') = '' OR last_sale_at < ? THEN ?
                    ELSE last_sale_at
                END,
                    updated_at = ?
                WHERE id = ?
                """,
                (sold_at, sold_at, utc_now(), account["id"]),
            )


def _ensure_fragrance_research_tables(conn):
    raise RuntimeError("company_db_sqlite_fragrance_research_tables_retired")


def _ensure_fragrance_research_pg_tables(conn):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_profiles (
                id BIGSERIAL PRIMARY KEY,
                product_id BIGINT NOT NULL UNIQUE,
                accords TEXT,
                fragrance_family TEXT,
                fragrance_dna TEXT,
                best_for_seasons TEXT,
                best_for_occasions TEXT,
                best_for_time_of_day TEXT,
                longevity TEXT,
                projection TEXT,
                sillage TEXT,
                compliment_factor TEXT,
                mood_keywords TEXT,
                similar_signature TEXT,
                inspired_by_signature TEXT,
                source_confidence TEXT,
                source_summary TEXT,
                verified_sources_count BIGINT NOT NULL DEFAULT 0,
                needs_manual_review BIGINT NOT NULL DEFAULT 0,
                last_researched_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_research_sources (
                id BIGSERIAL PRIMARY KEY,
                product_id BIGINT NOT NULL,
                source_type TEXT NOT NULL,
                source_label TEXT,
                source_url TEXT,
                evidence_kind TEXT,
                evidence_excerpt TEXT,
                captured_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_pg_product_fragrance_profiles_product_id
            ON {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_profiles(product_id)
            """
        )
        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_pg_product_fragrance_research_sources_product_id
            ON {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_research_sources(product_id)
            """
        )


def _ensure_company_migrations(conn):
    raise RuntimeError("company_db_sqlite_migrations_retired")


def _normalize_identity_platform(platform):
    value = str(platform or "").strip().lower().replace("-", "_")
    return value or "whatnot"


def _normalize_identity_value(value):
    text = str(value or "").strip()
    return text or None


def _normalize_identity_key(value):
    text = _normalize_identity_value(value)
    return text.lower() if text else None


def _normalize_phone_key(value):
    text = _normalize_identity_value(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def _legacy_customer_key(platform, username=None, platform_user_id=None, email=None, phone=None, display_name=None):
    norm_platform = _normalize_identity_platform(platform)
    if norm_platform == "whatnot":
        candidate = _normalize_identity_key(username or platform_user_id or email or phone or display_name)
        return candidate or f"whatnot:{uuid.uuid4().hex[:12]}"
    candidate = (
        _normalize_identity_key(username)
        or _normalize_identity_key(platform_user_id)
        or _normalize_identity_key(email)
        or _normalize_phone_key(phone)
        or _normalize_identity_key(display_name)
        or uuid.uuid4().hex[:12]
    )
    safe = re.sub(r"[^a-z0-9:_-]+", "-", str(candidate).lower()).strip("-") or uuid.uuid4().hex[:12]
    return f"{norm_platform}:{safe}"


def _fetch_customer_identity_by_exact(conn, *, platform=None, platform_user_id=None, username=None):
    norm_platform = _normalize_identity_platform(platform)
    platform_user_id_key = _normalize_identity_key(platform_user_id)
    username_key = _normalize_identity_key(username)
    if platform_user_id_key:
        row = _fetchone_dict(
            conn,
            """
            SELECT ci.*, c.*
            FROM customer_identities ci
            JOIN customers c ON c.id = ci.customer_id
            WHERE LOWER(ci.platform) = ?
              AND LOWER(COALESCE(ci.platform_user_id, '')) = ?
            ORDER BY ci.id ASC
            LIMIT 1
            """,
            (norm_platform, platform_user_id_key),
        )
        if row:
            return row
    if username_key:
        row = _fetchone_dict(
            conn,
            """
            SELECT ci.*, c.*
            FROM customer_identities ci
            JOIN customers c ON c.id = ci.customer_id
            WHERE LOWER(ci.platform) = ?
              AND LOWER(COALESCE(ci.username, '')) = ?
            ORDER BY ci.id ASC
            LIMIT 1
            """,
            (norm_platform, username_key),
        )
        if row:
            return row
    return None


def _fetch_customer_by_contact_exact(conn, *, email=None, phone=None):
    email_key = _normalize_identity_key(email)
    phone_key = _normalize_phone_key(phone)
    if email_key:
        row = _fetchone_dict(
            conn,
            "SELECT * FROM customers WHERE LOWER(COALESCE(email, '')) = ? ORDER BY id ASC LIMIT 1",
            (email_key,),
        )
        if row:
            return row
    if phone_key:
        rows = _fetchall_dict(conn, "SELECT * FROM customers WHERE COALESCE(phone, '') <> '' ORDER BY id ASC")
        for row in rows:
            if _normalize_phone_key(row.get("phone")) == phone_key:
                return row
    return None


def _upsert_customer_identity_txn(
    conn,
    *,
    customer_id,
    platform,
    platform_user_id=None,
    username=None,
    display_name=None,
    email=None,
    phone=None,
):
    now = utc_now()
    norm_platform = _normalize_identity_platform(platform)
    platform_user_id_value = _normalize_identity_value(platform_user_id)
    username_value = _normalize_identity_value(username)
    display_name_value = _normalize_identity_value(display_name)
    email_value = _normalize_identity_value(email)
    phone_value = _normalize_identity_value(phone)
    existing = _fetch_customer_identity_by_exact(
        conn,
        platform=norm_platform,
        platform_user_id=platform_user_id_value,
        username=username_value,
    )
    if existing:
        conn.execute(
            """
            UPDATE customer_identities
            SET customer_id = ?,
                display_name = COALESCE(?, display_name),
                email = COALESCE(?, email),
                phone = COALESCE(?, phone),
                updated_at = ?
            WHERE id = ?
            """,
            (
                int(customer_id),
                display_name_value,
                email_value,
                phone_value,
                now,
                int(existing["id"]),
            ),
        )
        return _fetchone_dict(conn, "SELECT * FROM customer_identities WHERE id = ?", (int(existing["id"]),))

    cur = conn.execute(
        """
        INSERT INTO customer_identities (
            customer_id, platform, platform_user_id, username, display_name, email, phone, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(customer_id),
            norm_platform,
            platform_user_id_value,
            username_value,
            display_name_value,
            email_value,
            phone_value,
            now,
            now,
        ),
    )
    return _fetchone_dict(conn, "SELECT * FROM customer_identities WHERE id = ?", (int(cur.lastrowid),))


def _backfill_customer_identities(conn):
    rows = _fetchall_dict(conn, "SELECT * FROM customers ORDER BY id ASC")
    for customer in rows:
        customer_id = int(customer["id"])
        whatnot_rows = _fetchall_dict(
            conn,
            """
            SELECT DISTINCT winner_username AS username
            FROM auction_results
            WHERE customer_id = ?
              AND COALESCE(winner_username, '') <> ''
            """,
            (customer_id,),
        )
        whatnot_order_rows = _fetchall_dict(
            conn,
            """
            SELECT DISTINCT whatnot_buyer_username AS username
            FROM sale_orders
            WHERE customer_id = ?
              AND LOWER(COALESCE(order_source, 'whatnot')) = 'whatnot'
              AND COALESCE(whatnot_buyer_username, '') <> ''
            """,
            (customer_id,),
        )
        tiktok_live_rows = _fetchall_dict(
            conn,
            """
            SELECT DISTINCT whatnot_buyer_username AS username
            FROM sale_orders
            WHERE customer_id = ?
              AND LOWER(COALESCE(order_source, '')) = 'tiktok_live'
              AND COALESCE(whatnot_buyer_username, '') <> ''
            """,
            (customer_id,),
        )
        tiktok_shop_rows = _fetchall_dict(
            conn,
            """
            SELECT DISTINCT whatnot_buyer_username AS username
            FROM sale_orders
            WHERE customer_id = ?
              AND LOWER(COALESCE(order_source, '')) = 'tiktok_shop'
              AND COALESCE(whatnot_buyer_username, '') <> ''
            """,
            (customer_id,),
        )
        linked_any = False
        for row in whatnot_rows + whatnot_order_rows:
            username = _normalize_identity_value(row.get("username"))
            if not username:
                continue
            _upsert_customer_identity_txn(
                conn,
                customer_id=customer_id,
                platform="whatnot",
                platform_user_id=username,
                username=username,
                display_name=customer.get("display_name"),
                email=customer.get("email"),
                phone=customer.get("phone"),
            )
            linked_any = True
        for platform, source_rows in (("tiktok_live", tiktok_live_rows), ("tiktok_shop", tiktok_shop_rows)):
            for row in source_rows:
                username = _normalize_identity_value(row.get("username"))
                if not username:
                    continue
                _upsert_customer_identity_txn(
                    conn,
                    customer_id=customer_id,
                    platform=platform,
                    platform_user_id=username,
                    username=username,
                    display_name=customer.get("display_name"),
                    email=customer.get("email"),
                    phone=customer.get("phone"),
                )
                linked_any = True
        if not linked_any and _normalize_identity_value(customer.get("whatnot_username")):
            username = customer.get("whatnot_username")
            _upsert_customer_identity_txn(
                conn,
                customer_id=customer_id,
                platform="whatnot",
                platform_user_id=username,
                username=username,
                display_name=customer.get("display_name"),
                email=customer.get("email"),
                phone=customer.get("phone"),
            )


def _write_affiliate_audit(conn, affiliate_id=None, event_type="affiliate_event", actor=None, metadata=None):
    conn.execute(
        """
        INSERT INTO affiliate_audit_log (affiliate_id, actor, event_type, metadata, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(affiliate_id) if affiliate_id not in (None, "") else None,
            actor or None,
            str(event_type or "affiliate_event"),
            _json_dumps(metadata or {}),
            utc_now(),
        ),
    )


def _seed_default_affiliate_pricelists(conn):
    now = utc_now()
    defaults = [
        ("Retail", "company", "active", "fixed_retail", 0, 0, "Default company retail pricing."),
        ("Staff", "staff", "draft", "discount_from_retail", 20, 0, "Internal staff pricing policy."),
        ("Affiliate", "affiliate", "active", "discount_from_retail", 10, 0, "Default affiliate-facing pricing."),
        ("Wholesale", "wholesale", "draft", "discount_from_retail", 30, 0, "Bulk/wholesale pricing tier."),
        ("TV Scanner", "scanner", "draft", "fixed_retail", 0, 0, "Scanner and display-visible pricing."),
    ]
    for name, audience, status, model, discount, markup, notes in defaults:
        conn.execute(
            """
            INSERT OR IGNORE INTO affiliate_pricelists (
                name, audience, status, pricing_model, discount_pct, markup_pct,
                currency, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'USD', ?, ?, ?)
            """,
            (name, audience, status, model, float(discount), float(markup), notes, now, now),
        )
    conn.execute(
        "UPDATE affiliate_pricelists SET status = 'active', updated_at = ? WHERE name = 'Affiliate' AND status = 'draft'",
        (now,),
    )


def _pg_fetchone_dict(cur):
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip((desc[0] for desc in cur.description), row))


def _pg_ensure_employee_account_policy_columns(cur):
    cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ADD COLUMN IF NOT EXISTS auto_approve_in_house_orders BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ADD COLUMN IF NOT EXISTS allow_self_service_returns BOOLEAN NOT NULL DEFAULT FALSE")


def _pg_ensure_employee_account_txn(cur, employee_name=None, employee_id=None):
    _pg_ensure_employee_account_policy_columns(cur)
    now = utc_now()
    if employee_id not in (None, ""):
        cur.execute(
            f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.employee_accounts WHERE id = %s",
            (int(employee_id),),
        )
        row = _pg_fetchone_dict(cur)
        if not row:
            raise ValueError("employee account not found")
        return row
    clean_name = " ".join(str(employee_name or "").strip().split())
    if not clean_name:
        raise ValueError("employee_name required")
    name_key = _employee_name_key(clean_name)
    cur.execute(
        f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.employee_accounts WHERE name_key = %s",
        (name_key,),
    )
    row = _pg_fetchone_dict(cur)
    if row:
        if row.get("name") != clean_name:
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.employee_accounts SET name = %s, updated_at = %s WHERE id = %s",
                (clean_name, now, int(row["id"])),
            )
            row["name"] = clean_name
        return row
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.employee_accounts (name, name_key, active, created_at, updated_at)
        VALUES (%s, %s, 1, %s, %s)
        RETURNING *
        """,
        (clean_name, name_key, now, now),
    )
    return _pg_fetchone_dict(cur)


def _pg_default_company_session_name_txn(cur, when=None, whatnot_account="ynfdeals"):
    when = when or datetime.now()
    cur.execute(
        f"SELECT COUNT(*) AS c FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions WHERE whatnot_account = %s",
        (whatnot_account,),
    )
    row = _pg_fetchone_dict(cur) or {}
    session_number = int(row.get("c") or 0) + 1
    return (
        f"S{session_number} "
        f"{when.strftime('%A')} : "
        f"{when.strftime('%Y-%m-%d')} : "
        f"{when.strftime('%I:%M:%S %p')}"
    )


def _pg_create_in_house_sale_txn(cur, employee_name=None, employee_id=None, product_id=None, barcode=None, sku=None, qty=1, unit_price=None, notes=None, sold_at=None, order_id=None, order_line_id=None):
    qty = float(qty or 0)
    if qty <= 0:
        raise ValueError("qty must be greater than 0")
    product = get_product(int(product_id)) if product_id else None
    if not product and (barcode or sku):
        product = find_product_by_code(barcode or sku)
    if not product:
        raise ValueError("product not found")
    now = utc_now()
    sold_at = sold_at or now
    unit_cost = float(product.get("cost_price") or 0)
    unit_price = unit_cost if unit_price in (None, "") else float(unit_price or 0)
    subtotal = round(qty * unit_price, 2)
    total_cost = round(qty * unit_cost, 2)
    profit = round(subtotal - total_cost, 2)
    account = _pg_ensure_employee_account_txn(cur, employee_name=employee_name, employee_id=employee_id)
    cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.in_house_sales ADD COLUMN IF NOT EXISTS order_id BIGINT")
    cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.in_house_sales ADD COLUMN IF NOT EXISTS order_line_id BIGINT")
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.in_house_sales (
            employee_id, employee_name, product_id, product_name, barcode, sku,
            qty, unit_cost, unit_price, subtotal, total_cost, profit,
            notes, sold_at, created_at, updated_at, order_id, order_line_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            int(account["id"]),
            account["name"],
            int(product["id"]),
            product.get("name"),
            product.get("barcode"),
            product.get("sku"),
            qty,
            unit_cost,
            unit_price,
            subtotal,
            total_cost,
            profit,
            notes,
            sold_at,
            now,
            now,
            int(order_id) if order_id else None,
            int(order_line_id) if order_line_id else None,
        ),
    )
    sale = _pg_fetchone_dict(cur)
    cur.execute(
        f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.employee_accounts SET last_sale_at = %s, updated_at = %s WHERE id = %s",
        (sold_at, now, int(account["id"])),
    )
    return sale


def _pg_get_product_txn(cur, product_id=None, barcode=None, sku=None):
    if product_id not in (None, ""):
        cur.execute(
            f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.products WHERE id = %s",
            (int(product_id),),
        )
        return _pg_fetchone_dict(cur)
    code = (barcode or sku or "").strip()
    if not code:
        return None
    cur.execute(
        f"""
        SELECT *
        FROM {POSTGRES_SIDECAR_SCHEMA}.products
        WHERE barcode = %s OR sku = %s
        ORDER BY id ASC
        LIMIT 1
        """,
        (code, code),
    )
    return _pg_fetchone_dict(cur)


def _pg_write_inventory_audit_txn(cur, product_id, event_type, source=None, actor=None, changed_fields=None, metadata=None, created_at=None):
    created_at = created_at or utc_now()
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.inventory_audit_log (
            product_id, event_type, source, actor, changed_fields, metadata, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            int(product_id),
            str(event_type or "unknown"),
            source or None,
            actor or None,
            _json_dumps(changed_fields or {}),
            _json_dumps(metadata or {}),
            created_at,
        ),
    )
    return _pg_fetchone_dict(cur)


def _pg_record_inventory_movement_txn(cur, product_id, movement_type, qty_delta, reason=None, reference_type=None, reference_id=None):
    now = utc_now()
    cur.execute(
        f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.products WHERE id = %s",
        (int(product_id),),
    )
    before = _pg_fetchone_dict(cur)
    if not before:
        raise ValueError("product not found")
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.inventory_movements (
            product_id, movement_type, qty_delta, reason,
            reference_type, reference_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            int(product_id),
            movement_type,
            float(qty_delta),
            reason,
            reference_type,
            reference_id,
            now,
        ),
    )
    movement = _pg_fetchone_dict(cur)
    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.products
        SET on_hand_qty = COALESCE(on_hand_qty, 0) + %s,
            tiktok_quantity = CASE WHEN tiktok_quantity IS NOT NULL THEN tiktok_quantity + %s ELSE tiktok_quantity END,
            updated_at = %s
        WHERE id = %s
        RETURNING *
        """,
        (float(qty_delta), float(qty_delta), now, int(product_id)),
    )
    after = _pg_fetchone_dict(cur)
    audit_row = None
    if before and after:
        audit_row = _pg_write_inventory_audit_txn(
            cur,
            product_id,
            event_type="stock_movement",
            source=reference_type or movement_type,
            changed_fields={
                "on_hand_qty": {
                    "before": before.get("on_hand_qty"),
                    "after": after.get("on_hand_qty"),
                },
                "tiktok_quantity": {
                    "before": before.get("tiktok_quantity"),
                    "after": after.get("tiktok_quantity"),
                },
                "updated_at": {
                    "before": before.get("updated_at"),
                    "after": after.get("updated_at"),
                },
            },
            metadata={
                "movement_type": movement_type,
                "qty_delta": float(qty_delta),
                "reason": reason,
                "reference_type": reference_type,
                "reference_id": reference_id,
            },
            created_at=now,
        )
    return {"product": after, "movement": movement, "audit": audit_row}


def _record_inventory_movement_txn(conn, product_id, movement_type, qty_delta, reason=None, reference_type=None, reference_id=None):
    try:
        with pg_domain_tx("inventory_movements", "inventory_movements") as (_pg_conn, cur):
            _pg_record_inventory_movement_txn(
                cur,
                product_id,
                movement_type,
                qty_delta,
                reason=reason,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        return get_product(int(product_id))
    except Exception as exc:
        log_cutover_event("inventory_movements", "postgres_primary_failed_closed", "inventory_movements", product_id, {"error": str(exc)})
        raise


def _default_company_session_name(conn, when=None, whatnot_account="ynfdeals"):
    when = when or datetime.now()
    session_number = conn.execute(
        "SELECT COUNT(*) FROM company_sessions WHERE whatnot_account = ?",
        (whatnot_account,),
    ).fetchone()[0] + 1
    return (
        f"S{session_number} "
        f"{when.strftime('%A')} : "
        f"{when.strftime('%Y-%m-%d')} : "
        f"{when.strftime('%I:%M:%S %p')}"
    )


def _pg_get_company_session(session_id):
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT cs.*, s.stream_url, s.streamer_name, s.title
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = cs.stream_id
                WHERE cs.id = %s
                """,
                (int(session_id),),
            )
            return _fetchone_dict_pg(cur)


def _pg_get_company_session_for_stream(stream_id):
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT cs.*, s.stream_url, s.streamer_name, s.title
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = cs.stream_id
                WHERE cs.stream_id = %s
                ORDER BY
                  CASE
                    WHEN LOWER(COALESCE(cs.status, '')) = 'live' THEN 0
                    WHEN LOWER(COALESCE(cs.status, '')) IN ('open', 'draft') THEN 1
                    WHEN LOWER(COALESCE(cs.status, '')) = 'ended' THEN 2
                    ELSE 3
                  END,
                  COALESCE(cs.started_at, cs.created_at) DESC
                LIMIT 1
                """,
                (int(stream_id),),
            )
            return _fetchone_dict_pg(cur)


def _pg_list_company_sessions(whatnot_account="ynfdeals", status=None, limit=100, exclude_test_data=True):
    query = f"""
        SELECT cs.*, s.stream_url, s.streamer_name, s.title
        FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = cs.stream_id
        WHERE cs.whatnot_account = %s
    """
    params = [whatnot_account]
    if exclude_test_data:
        query += " AND LOWER(COALESCE(cs.show_id, '')) NOT LIKE 'smoke-%%'"
        query += " AND LOWER(COALESCE(cs.name, '')) NOT LIKE 'smoke test%%'"
    if status:
        query += " AND cs.status = %s"
        params.append(status)
    query += " ORDER BY COALESCE(cs.started_at, cs.created_at) DESC LIMIT %s"
    params.append(int(limit))
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = _pg_fetchall_dict(cur)
    for row in rows:
        if not row:
            continue
        session_title = str(row.get("name") or row.get("title") or "").strip()
        if session_title:
            row["title"] = session_title
        if row.get("sequence_no") in (None, "") and session_title:
            match = re.search(r"Session\s*[-#]?\s*(\d+)", session_title, re.IGNORECASE)
            if not match:
                match = re.search(r"\bSession\s+(\d+)\b", session_title, re.IGNORECASE)
            if match:
                row["sequence_no"] = int(match.group(1))
    return rows


def _pg_list_company_lots(session_id=None, status=None, limit=None):
    query = f"""
        SELECT cl.*, cs.name AS session_name
        FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots cl
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = cl.session_id
        WHERE 1=1
    """
    params = []
    if session_id:
        query += " AND cl.session_id = %s"
        params.append(int(session_id))
    if status:
        query += " AND cl.status = %s"
        params.append(status)
    query += " ORDER BY cl.id DESC"
    if limit:
        query += " LIMIT %s"
        params.append(int(limit))
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            return _pg_fetchall_dict(cur)


def create_company_session(stream_id=None, show_id=None, whatnot_account="ynfdeals", name=None, status="draft"):
    _require_company_postgres_runtime("company_sessions")
    now = utc_now()
    try:
        with pg_domain_tx("company_sessions", "company_sessions") as (_pg_conn, cur):
            session_name = name or _pg_default_company_session_name_txn(cur, datetime.now(), whatnot_account)
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.company_sessions (
                    stream_id, show_id, whatnot_account, name, status,
                    started_at, total_revenue, total_cost, total_profit,
                    total_products_sold, total_lots_sold, total_fees,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    stream_id,
                    show_id,
                    whatnot_account,
                    session_name,
                    status,
                    now,
                    0.0,
                    0.0,
                    0.0,
                    0,
                    0,
                    0.0,
                    now,
                    now,
                ),
            )
            row = _pg_fetchone_dict(cur)
        return get_company_session(int(row["id"]))
    except Exception as exc:
        log_cutover_event("company_sessions", "postgres_primary_failed_closed", "company_sessions", None, {"error": str(exc)})
        raise


def get_company_session(session_id):
    _require_company_postgres_runtime("company_sessions")
    return _pg_get_company_session(session_id)


def get_company_session_for_stream(stream_id):
    _require_company_postgres_runtime("company_sessions")
    return _pg_get_company_session_for_stream(stream_id)


def list_company_sessions(whatnot_account="ynfdeals", status=None, limit=100, exclude_test_data=True):
    _require_company_postgres_runtime("company_sessions")
    return _pg_list_company_sessions(
        whatnot_account=whatnot_account,
        status=status,
        limit=limit,
        exclude_test_data=exclude_test_data,
    )


def delete_company_session_tree(session_id):
    _require_company_postgres_runtime("company_sessions")
    session_id = int(session_id)
    postgres_deletes = (
        (
            f"""
            DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
            WHERE assignment_id IN (
                SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments WHERE session_id = %s
            )
            """,
            (session_id,),
        ),
        (f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments WHERE session_id = %s", (session_id,)),
        (
            f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines WHERE sale_order_id IN (SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders WHERE session_id = %s)",
            (session_id,),
        ),
        (f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.buyer_groups WHERE session_id = %s", (session_id,)),
        (f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders WHERE session_id = %s", (session_id,)),
        (f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE session_id = %s", (session_id,)),
        (
            f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items WHERE lot_id IN (SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots WHERE session_id = %s)",
            (session_id,),
        ),
        (f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots WHERE session_id = %s", (session_id,)),
        (f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions WHERE id = %s", (session_id,)),
    )
    try:
        with pg_domain_tx("company_sessions", "delete_company_session_tree") as (_pg_conn, cur):
            for statement, params in postgres_deletes:
                cur.execute(statement, params)
    except Exception as exc:
        log_cutover_event(
            "company_sessions",
            "postgres_primary_failed_closed",
            "company_sessions",
            session_id,
            {"error": str(exc)},
        )
        raise


def update_company_session(session_id, **fields):
    _require_company_postgres_runtime("company_sessions")
    allowed = {
        "stream_id", "show_id", "whatnot_account", "name", "status",
        "current_lot_number", "started_at", "ended_at",
        "total_revenue", "total_cost", "total_profit",
        "total_products_sold", "total_lots_sold",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_company_session(session_id)
    updates["updated_at"] = utc_now()
    try:
        with pg_domain_tx("company_sessions", "company_sessions_update") as (_pg_conn, cur):
            assignments = ", ".join(f"{key} = %s" for key in updates)
            params = list(updates.values()) + [int(session_id)]
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_sessions SET {assignments} WHERE id = %s RETURNING *",
                params,
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                raise ValueError(f"company session {session_id} not found")
        return get_company_session(session_id)
    except Exception as exc:
        log_cutover_event("company_sessions", "postgres_primary_failed_closed", "company_sessions", session_id, {"error": str(exc)})
        raise


def end_company_session(session_id):
    now = utc_now()
    return update_company_session(session_id, status="ended", ended_at=now)


def create_company_lot(session_id, lot_number, status="open"):
    _require_company_postgres_runtime("company_lots")
    now = utc_now()
    try:
        with pg_domain_tx("company_lots", "company_lots") as (_pg_conn, cur):
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.company_lots (
                    session_id, lot_number, status, fees, total_cost, total_profit,
                    total_products, sold_products, dropped_products, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id, lot_number) DO UPDATE
                SET status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
                RETURNING *
                """,
                (
                    int(session_id),
                    str(lot_number),
                    status,
                    0.0,
                    0.0,
                    0.0,
                    0,
                    0,
                    0,
                    now,
                    now,
                ),
            )
            row = _pg_fetchone_dict(cur)
        return get_company_lot_by_number(session_id, lot_number)
    except Exception as exc:
        log_cutover_event("company_lots", "postgres_primary_failed_closed", "company_lots", f"{session_id}:{lot_number}", {"error": str(exc)})
        raise


def get_company_lot_by_number(session_id, lot_number):
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots
                WHERE session_id = %s AND lot_number = %s
                """,
                (int(session_id), str(lot_number)),
            )
            return _pg_fetchone_dict(cur)


def list_company_lots(session_id=None, status=None, limit=None):
    _require_company_postgres_runtime("company_lots")
    return _pg_list_company_lots(session_id=session_id, status=status, limit=limit)


def update_company_lot(lot_id, **fields):
    _require_company_postgres_runtime("company_lots")
    allowed = {
        "status", "winner_username", "winning_price", "fees",
        "total_cost", "total_profit", "total_products",
        "sold_products", "dropped_products", "closed_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        ensure_wave1_postgres_schema()
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots WHERE id = %s",
                    (int(lot_id),),
                )
                return _pg_fetchone_dict(cur)
    updates["updated_at"] = utc_now()
    try:
        with pg_domain_tx("company_lots", "company_lots_update") as (_pg_conn, cur):
            assignments = ", ".join(f"{key} = %s" for key in updates)
            params = list(updates.values()) + [int(lot_id)]
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lots SET {assignments} WHERE id = %s RETURNING *",
                params,
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                raise ValueError(f"company lot {lot_id} not found")
        return row
    except Exception as exc:
        log_cutover_event("company_lots", "postgres_primary_failed_closed", "company_lots", lot_id, {"error": str(exc)})
        raise


def list_company_sessions(whatnot_account="ynfdeals", status=None, limit=100, exclude_test_data=True):
    _require_company_postgres_runtime("company_sessions")
    return _pg_list_company_sessions(
        whatnot_account=whatnot_account,
        status=status,
        limit=limit,
        exclude_test_data=exclude_test_data,
    )


def list_customer_identities(customer_id):
    _require_company_postgres_runtime("company_customers")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities
                WHERE customer_id = %s
                ORDER BY
                    CASE LOWER(COALESCE(platform, ''))
                        WHEN 'whatnot' THEN 1
                        WHEN 'tiktok_live' THEN 2
                        WHEN 'tiktok_shop' THEN 3
                        ELSE 9
                    END,
                    LOWER(COALESCE(username, platform_user_id, ''))
                """,
                (int(customer_id),),
            )
            return _pg_fetchall_dict(cur)


def upsert_customer(
    whatnot_username,
    display_name=None,
    email=None,
    phone=None,
    address=None,
    notes=None,
    *,
    platform="whatnot",
    platform_user_id=None,
    identity_username=None,
):
    _require_company_postgres_runtime("company_customers")
    now = utc_now()
    norm_platform = _normalize_identity_platform(platform)
    identity_username_value = _normalize_identity_value(identity_username or whatnot_username)
    platform_user_id_value = _normalize_identity_value(platform_user_id or identity_username_value)
    email_value = _normalize_identity_value(email)
    phone_value = _normalize_identity_value(phone)
    display_name_value = _normalize_identity_value(display_name)
    legacy_key = _normalize_identity_value(whatnot_username) or _legacy_customer_key(
        norm_platform,
        username=identity_username_value,
        platform_user_id=platform_user_id_value,
        email=email_value,
        phone=phone_value,
        display_name=display_name_value,
    )
    existing_customer = None
    try:
        ensure_wave1_postgres_schema()
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                if identity_username_value:
                    cur.execute(
                        f"""
                        SELECT c.*
                        FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities ci
                        JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = ci.customer_id
                        WHERE ci.platform = %s
                          AND (
                            (%s <> '' AND LOWER(COALESCE(ci.username, '')) = %s)
                            OR (%s <> '' AND LOWER(COALESCE(ci.platform_user_id, '')) = %s)
                          )
                        ORDER BY c.id ASC
                        LIMIT 1
                        """,
                        (
                            norm_platform,
                            identity_username_value,
                            _normalize_identity_key(identity_username_value),
                            platform_user_id_value or "",
                            _normalize_identity_key(platform_user_id_value or ""),
                        ),
                    )
                    existing_customer = _pg_fetchone_dict(cur)
                if not existing_customer and (email_value or phone_value):
                    cur.execute(
                        f"""
                        SELECT *
                        FROM {POSTGRES_SIDECAR_SCHEMA}.customers
                        WHERE (%s <> '' AND LOWER(COALESCE(email, '')) = %s)
                           OR (%s <> '' AND LOWER(COALESCE(phone, '')) = %s)
                        ORDER BY id ASC
                        LIMIT 1
                        """,
                        (
                            email_value or "",
                            _normalize_identity_key(email_value or ""),
                            phone_value or "",
                            _normalize_identity_key(phone_value or ""),
                        ),
                    )
                    existing_customer = _pg_fetchone_dict(cur)
                if not existing_customer and legacy_key:
                    cur.execute(
                        f"""
                        SELECT *
                        FROM {POSTGRES_SIDECAR_SCHEMA}.customers
                        WHERE LOWER(COALESCE(whatnot_username, '')) = %s
                        ORDER BY id ASC
                        LIMIT 1
                        """,
                        (_normalize_identity_key(legacy_key),),
                    )
                    existing_customer = _pg_fetchone_dict(cur)
    except Exception:
        existing_customer = None

    try:
        with pg_domain_tx("company_customers", "customers") as (_pg_conn, cur):
            existing = None
            if existing_customer:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.customers WHERE id = %s ORDER BY id ASC LIMIT 1",
                    (int(existing_customer["id"]),),
                )
                existing = _pg_fetchone_dict(cur)
            if not existing:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.customers WHERE whatnot_username = %s ORDER BY id ASC LIMIT 1",
                    (legacy_key,),
                )
                existing = _pg_fetchone_dict(cur)
            if existing:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.customers
                    SET display_name = COALESCE(%s, display_name),
                        email = COALESCE(%s, email),
                        phone = COALESCE(%s, phone),
                        address = COALESCE(%s, address),
                        notes = COALESCE(%s, notes),
                        updated_at = %s
                    WHERE id = %s
                    RETURNING *
                    """,
                    (display_name_value, email_value, phone_value, address, notes, now, int(existing["id"])),
                )
                row = _pg_fetchone_dict(cur)
            else:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.customers (
                        whatnot_username, display_name, email, phone, address, notes, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (legacy_key, display_name_value, email_value, phone_value, address, notes, now, now),
                )
                row = _pg_fetchone_dict(cur)
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.customer_identities (
                    customer_id, platform, platform_user_id, username, display_name, email, phone, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (platform, username)
                DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    platform_user_id = COALESCE(EXCLUDED.platform_user_id, {POSTGRES_SIDECAR_SCHEMA}.customer_identities.platform_user_id),
                    display_name = COALESCE(EXCLUDED.display_name, {POSTGRES_SIDECAR_SCHEMA}.customer_identities.display_name),
                    email = COALESCE(EXCLUDED.email, {POSTGRES_SIDECAR_SCHEMA}.customer_identities.email),
                    phone = COALESCE(EXCLUDED.phone, {POSTGRES_SIDECAR_SCHEMA}.customer_identities.phone),
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    int(row["id"]),
                    norm_platform,
                    platform_user_id_value,
                    identity_username_value,
                    display_name_value,
                    email_value,
                    phone_value,
                    now,
                    now,
                ),
            )
        return get_customer(int(row["id"]))
    except Exception as exc:
        log_cutover_event("company_customers", "postgres_primary_failed_closed", "customers", legacy_key, {"error": str(exc)})
        raise


def upsert_product(name, sku=None, barcode=None, category_id=None, brand=None, gender=None, supplier_name=None,
                   storage_bin=None, product_type="storable", cost_price=0, raw_cost=0,
                   cost_plus_12=0, cost_plus_20=0, retail_price=0, notes=None,
                   notes_verified=0, notes_verified_at=None, low_stock_threshold=3, size_oz=None, size_ml=None,
                   volume_oz=None, volume_ml=None,
                   description=None, script=None, note_top=None, note_mid=None, note_base=None, media_url=None,
                   dupe_inspiration=None, dupe_confidence=None, dupe_classification=None, dupe_notes=None):
    now = utc_now()
    if domain_primary_backend("inventory_products") == "postgres":
        try:
            audit_row = None
            changed_fields = {}
            matched_by = "barcode" if barcode else "sku"
            created_product = False
            with pg_domain_tx("inventory_products", "products") as (_pg_conn, cur):
                existing = None
                if barcode:
                    cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.products WHERE barcode = %s ORDER BY id ASC LIMIT 1", (barcode,))
                    existing = _pg_fetchone_dict(cur)
                if not existing and sku:
                    cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.products WHERE sku = %s ORDER BY id ASC LIMIT 1", (sku,))
                    existing = _pg_fetchone_dict(cur)
                if existing:
                    before = existing
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.products
                        SET name = %s,
                            sku = %s,
                            barcode = %s,
                            category_id = %s,
                            brand = %s,
                            gender = %s,
                            supplier_name = %s,
                            storage_bin = %s,
                            product_type = %s,
                            cost_price = %s,
                            raw_cost = %s,
                            cost_plus_12 = %s,
                            cost_plus_20 = %s,
                            retail_price = %s,
                            size_oz = %s,
                            size_ml = %s,
                            volume_oz = %s,
                            volume_ml = %s,
                            low_stock_threshold = %s,
                            notes = %s,
                            notes_verified = %s,
                            notes_verified_at = %s,
                            description = %s,
                            script = %s,
                            note_top = %s,
                            note_mid = %s,
                            note_base = %s,
                            media_url = %s,
                            dupe_inspiration = %s,
                            dupe_confidence = %s,
                            dupe_classification = %s,
                            dupe_notes = %s,
                            updated_at = %s
                        WHERE id = %s
                        RETURNING *
                        """,
                        (
                            name, sku, barcode, category_id, brand, gender, supplier_name, storage_bin,
                            product_type, cost_price, raw_cost, cost_plus_12, cost_plus_20, retail_price, size_oz, size_ml, volume_oz, volume_ml, low_stock_threshold,
                            notes, 1 if notes_verified else 0, notes_verified_at,
                            description, script, note_top, note_mid, note_base, media_url,
                            dupe_inspiration, dupe_confidence, dupe_classification, dupe_notes,
                            now, int(existing["id"]),
                        ),
                    )
                    after = _pg_fetchone_dict(cur)
                    if before and after:
                        for key in (
                            "name", "sku", "barcode", "category_id", "brand", "gender", "supplier_name",
                            "storage_bin", "product_type", "cost_price", "raw_cost", "cost_plus_12", "cost_plus_20",
                            "retail_price", "size_oz", "size_ml", "volume_oz", "volume_ml", "low_stock_threshold",
                            "notes", "notes_verified", "notes_verified_at",
                            "description", "script", "note_top", "note_mid", "note_base", "media_url",
                            "dupe_inspiration", "dupe_confidence", "dupe_classification", "dupe_notes",
                        ):
                            if _values_differ(before.get(key), after.get(key)):
                                changed_fields[key] = {"before": before.get(key), "after": after.get(key)}
                    if changed_fields and domain_primary_backend("inventory_audit") == "postgres":
                        audit_row = _pg_write_inventory_audit_txn(
                            cur,
                            int(existing["id"]),
                            event_type="product_update",
                            source="product_upsert",
                            changed_fields=changed_fields,
                            metadata={"matched_by": matched_by},
                        )
                    product_id = int(existing["id"])
                else:
                    created_product = True
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.products (
                            name, sku, barcode, category_id, brand, gender, supplier_name, storage_bin, product_type,
                            cost_price, raw_cost, cost_plus_12, cost_plus_20, retail_price, size_oz, size_ml, volume_oz, volume_ml, on_hand_qty, low_stock_threshold, active,
                            notes, notes_verified, notes_verified_at, description, script, note_top, note_mid, note_base, media_url,
                            dupe_inspiration, dupe_confidence, dupe_classification, dupe_notes, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            name, sku, barcode, category_id, brand, gender, supplier_name, storage_bin, product_type,
                            cost_price, raw_cost, cost_plus_12, cost_plus_20, retail_price, size_oz, size_ml, volume_oz, volume_ml, 0, low_stock_threshold, 1,
                            notes, 1 if notes_verified else 0, notes_verified_at, description, script, note_top, note_mid, note_base, media_url,
                            dupe_inspiration, dupe_confidence, dupe_classification, dupe_notes,
                            now, now,
                        ),
                    )
                    created = _pg_fetchone_dict(cur)
                    product_id = int(created["id"])
                    if domain_primary_backend("inventory_audit") == "postgres":
                        audit_row = _pg_write_inventory_audit_txn(
                            cur,
                            product_id,
                            event_type="product_create",
                            source="product_upsert",
                            changed_fields={
                                "name": {"before": None, "after": name},
                                "sku": {"before": None, "after": sku},
                                "barcode": {"before": None, "after": barcode},
                                "category_id": {"before": None, "after": category_id},
                                "brand": {"before": None, "after": brand},
                                "gender": {"before": None, "after": gender},
                                "supplier_name": {"before": None, "after": supplier_name},
                                "storage_bin": {"before": None, "after": storage_bin},
                                "product_type": {"before": None, "after": product_type},
                                "cost_price": {"before": None, "after": cost_price},
                                "raw_cost": {"before": None, "after": raw_cost},
                                "cost_plus_12": {"before": None, "after": cost_plus_12},
                                "cost_plus_20": {"before": None, "after": cost_plus_20},
                                "retail_price": {"before": None, "after": retail_price},
                                "size_oz": {"before": None, "after": size_oz},
                                "size_ml": {"before": None, "after": size_ml},
                                "volume_oz": {"before": None, "after": volume_oz},
                                "volume_ml": {"before": None, "after": volume_ml},
                                "notes": {"before": None, "after": notes},
                                "notes_verified": {"before": None, "after": 1 if notes_verified else 0},
                                "notes_verified_at": {"before": None, "after": notes_verified_at},
                            },
                        )
            return get_product(product_id)
        except Exception as exc:
            log_cutover_event("inventory_products", "postgres_primary_failed_closed", "products", barcode or sku or name, {"error": str(exc)})
            raise
    raise RuntimeError("postgres_runtime_required:inventory_products")


def add_lot_item(lot_id, product_id=None, barcode=None, sku=None, product_name=None, notes=None, unit_cost=0, qty_snapshot=1, status="open"):
    _require_company_postgres_runtime("company_lots")
    now = utc_now()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.company_lot_items (
                    lot_id, product_id, barcode, sku, product_name, notes,
                    unit_cost, qty_snapshot, scanned_at, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (int(lot_id), product_id, barcode, sku, product_name, notes, unit_cost, qty_snapshot, now, status),
            )
            item = _pg_fetchone_dict(cur)
        conn.commit()
    _recalc_lot_totals(lot_id)
    return item


def replace_lot_items_for_scan(lot_id, product_id=None, barcode=None, sku=None, product_name=None, notes=None, unit_cost=0, qty_snapshot=1, status="open"):
    """Keep operator-created TikTok lots to one current item per lot.

    The operator scan sheet is a lot map, not a multi-item bundle builder, so
    rescanning a row should replace the previous barcode/product cleanly.
    """
    now = utc_now()
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items WHERE lot_id = %s",
                (int(lot_id),),
            )
            item = None
            if str(barcode or "").strip() or product_id or str(product_name or "").strip():
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.company_lot_items (
                        lot_id, product_id, barcode, sku, product_name, notes,
                        unit_cost, qty_snapshot, scanned_at, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (int(lot_id), product_id, barcode, sku, product_name, notes, unit_cost, qty_snapshot, now, status),
                )
                item = _pg_fetchone_dict(cur)
        conn.commit()
    _recalc_lot_totals(lot_id)
    return item


def list_lot_items(lot_id):
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT li.*, p.name AS linked_product_name, p.on_hand_qty
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items li
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = li.product_id
                WHERE li.lot_id = %s
                ORDER BY li.id ASC
                """,
                (int(lot_id),),
            )
            return _pg_fetchall_dict(cur)


def get_lot_item(item_id):
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT li.*, p.name AS linked_product_name, p.on_hand_qty
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items li
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = li.product_id
                WHERE li.id = %s
                """,
                (int(item_id),),
            )
            return _pg_fetchone_dict(cur)


def update_lot_item(item_id, **fields):
    _require_company_postgres_runtime("company_lots")
    allowed = {"status", "qty_snapshot", "product_name", "barcode", "sku", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_lot_item(item_id)
    assignments = ", ".join(f"{key} = ?" for key in updates)
    params = list(updates.values()) + [int(item_id)]
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lot_items SET {assignments.replace('?', '%s')} WHERE id = %s",
                params,
            )
        conn.commit()
    row = get_lot_item(item_id)
    if row:
        _recalc_lot_totals(row["lot_id"])
    return row


def find_product_by_code(code):
    _require_company_postgres_runtime("inventory_products")
    code = (code or "").strip()
    if not code:
        return None
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT p.*, pc.name AS category_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.products p
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
                WHERE p.barcode = %s OR p.sku = %s
                LIMIT 1
                """,
                (code, code),
            )
            return _pg_fetchone_dict(cur)


def reserved_qty_for_product(session_id, product_id, exclude_lot_id=None):
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    query = f"""
        SELECT COALESCE(SUM(li.qty_snapshot), 0)
        FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items li
        JOIN {POSTGRES_SIDECAR_SCHEMA}.company_lots cl ON cl.id = li.lot_id
        JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = cl.session_id
        WHERE li.product_id = %s
          AND li.status IN ('open', 'active', 'queued')
          AND cl.status IN ('open', 'awaiting_auction')
          AND LOWER(COALESCE(cs.status, '')) NOT IN ('ended', 'archived')
    """
    params = [int(product_id)]
    if exclude_lot_id is not None:
        query += " AND cl.id != %s"
        params.append(int(exclude_lot_id))
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            row = cur.fetchone()
            return float((row[0] if row else 0) or 0)


def sync_pending_winner_assignment_items_from_lot(assignment_id, lot_id):
    _require_company_postgres_runtime("company_pending")
    assignment = get_pending_winner_assignment(assignment_id)
    if not assignment or assignment.get("status") == "confirmed":
        return assignment
    now = utc_now()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items
                WHERE lot_id = %s
                  AND status IN ('open', 'active', 'queued')
                  AND product_id IS NOT NULL
                ORDER BY id ASC
                """,
                (int(lot_id),),
            )
            lot_items = _pg_fetchall_dict(cur)
        aggregated = {}
        for item in lot_items:
            product_id = int(item.get("product_id") or 0)
            if product_id <= 0:
                continue
            key = product_id
            bucket = aggregated.setdefault(
                key,
                {
                    "product_id": product_id,
                    "barcode": item.get("barcode"),
                    "sku": item.get("sku"),
                    "product_name": item.get("product_name"),
                    "unit_cost": float(item.get("unit_cost") or 0),
                    "qty": 0,
                },
            )
            bucket["qty"] += int(item.get("qty_snapshot") or 0) or 1

        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items WHERE assignment_id = %s",
                (int(assignment_id),),
            )

        ordered_rows = list(aggregated.values())
        for row in ordered_rows:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items (
                        assignment_id, product_id, barcode, sku, product_name, unit_cost, qty, reserved_qty, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s)
                    """,
                    (
                        int(assignment_id),
                        int(row["product_id"]),
                        row.get("barcode"),
                        row.get("sku"),
                        row.get("product_name"),
                        float(row.get("unit_cost") or 0),
                        int(row.get("qty") or 0) or 1,
                        now,
                        now,
                    ),
                )

        if ordered_rows:
            total_cost = round(sum(float(row.get("unit_cost") or 0) * int(row.get("qty") or 0) for row in ordered_rows), 2)
            total_qty = sum(int(row.get("qty") or 0) for row in ordered_rows)
            summary_name = ", ".join(
                f"{row.get('product_name')} x{int(row.get('qty') or 0)}" for row in ordered_rows
            )
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET assigned_product_id = NULL,
                        assigned_barcode = NULL,
                        assigned_sku = NULL,
                        assigned_product_name = %s,
                        assigned_cost_price = %s,
                        assigned_at = %s,
                        status = CASE WHEN status = 'needs_review' THEN status ELSE 'assigned' END,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        summary_name if total_qty > 1 else ordered_rows[0].get("product_name"),
                        total_cost,
                        now,
                        now,
                        int(assignment_id),
                    ),
                )
        else:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET assigned_product_id = NULL,
                        assigned_barcode = NULL,
                        assigned_sku = NULL,
                        assigned_product_name = NULL,
                        assigned_cost_price = 0,
                        assigned_at = NULL,
                        status = CASE WHEN status = 'needs_review' THEN status ELSE 'pending' END,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (now, int(assignment_id)),
                )
        conn.commit()
    return get_pending_winner_assignment(int(assignment_id))


def get_current_company_lot(session_id):
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots
                WHERE session_id = %s
                  AND status IN ('open', 'awaiting_auction')
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(session_id),),
            )
            return _pg_fetchone_dict(cur)


def ensure_company_bucket(session_id):
    session = get_company_session(session_id)
    if not session:
        return None
    existing = get_current_company_lot(session_id)
    if existing:
        return existing
    lot_number = f"P-{int(datetime.now().timestamp())}"
    lot = create_company_lot(session_id, lot_number, status="open")
    update_company_session(session_id, current_lot_number=lot_number)
    return lot


def rename_company_lot(lot_id, lot_number):
    _require_company_postgres_runtime("company_lots")
    lot_number = str(lot_number).strip()
    if not lot_number:
        return None
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lots SET lot_number = %s WHERE id = %s",
                (lot_number, int(lot_id)),
            )
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots WHERE id = %s",
                (int(lot_id),),
            )
            lot = _pg_fetchone_dict(cur)
        conn.commit()
    if lot:
        update_company_session(lot["session_id"], current_lot_number=lot_number)
    return lot


def mark_lot_items_status(lot_id, from_statuses=None, to_status="dropped"):
    _require_company_postgres_runtime("company_lots")
    statuses = tuple(from_statuses or ("open", "active", "queued"))
    params = [to_status, int(lot_id), *statuses]
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lot_items SET status = %s WHERE lot_id = %s AND status IN ({','.join(['%s' for _ in statuses])})",
                params,
            )
        conn.commit()
    _recalc_lot_totals(lot_id)


def latest_reusable_lot(session_id):
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots
                WHERE session_id = %s
                  AND status IN ('dropped', 'released')
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(session_id),),
            )
            return _pg_fetchone_dict(cur)


def create_buyer_group(session_id, buyer_username, customer_id=None):
    _require_company_postgres_runtime("company_orders")
    now = utc_now()
    try:
        with pg_domain_tx("company_orders", "buyer_groups") as (_pg_conn, cur):
            return _pg_upsert_buyer_group_txn(cur, session_id, buyer_username, customer_id=customer_id)
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "buyer_groups", f"{session_id}:{buyer_username}", {"error": str(exc)})
        raise


def get_auction_result_by_source_event_id(source_event_id):
    if not source_event_id:
        return None
    _require_company_postgres_runtime("company_results")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE source_event_id = %s",
                (str(source_event_id),),
            )
            return _pg_fetchone_dict(cur)


def get_auction_result(result_id):
    _require_company_postgres_runtime("company_results")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE id = %s",
                (int(result_id),),
            )
            return _pg_fetchone_dict(cur)


def find_duplicate_auction_result(session_id, lot_id=None, lot_number=None, winner_username=None, sale_price=None):
    if not session_id:
        return None
    _require_company_postgres_runtime("company_results")
    rows = []
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if lot_id or lot_number:
                cur.execute(
                    f"""
                    SELECT *
                    FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results
                    WHERE session_id = %s
                      AND (
                            (%s IS NOT NULL AND lot_id = %s)
                         OR (%s IS NOT NULL AND lot_number = %s)
                      )
                    ORDER BY COALESCE(sale_price, 0) DESC, id DESC
                    LIMIT 5
                    """,
                    (
                        int(session_id),
                        int(lot_id) if lot_id else None,
                        int(lot_id) if lot_id else None,
                        str(lot_number) if lot_number else None,
                        str(lot_number) if lot_number else None,
                    ),
                )
                rows = _pg_fetchall_dict(cur)
            if not rows and winner_username and (lot_id or lot_number):
                cur.execute(
                    f"""
                    SELECT *
                    FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results
                    WHERE session_id = %s
                      AND LOWER(COALESCE(winner_username, '')) = LOWER(COALESCE(%s, ''))
                      AND (
                            (%s IS NOT NULL AND lot_id = %s)
                         OR (%s IS NOT NULL AND lot_number = %s)
                      )
                    ORDER BY COALESCE(sale_price, 0) DESC, id DESC
                    LIMIT 5
                    """,
                    (
                        int(session_id),
                        winner_username,
                        int(lot_id) if lot_id else None,
                        int(lot_id) if lot_id else None,
                        str(lot_number) if lot_number else None,
                        str(lot_number) if lot_number else None,
                    ),
                )
                rows = _pg_fetchall_dict(cur)
    target_price = float(sale_price or 0)
    if target_price <= 0:
        return rows[0] if rows else None
    # Same-lot rows should collapse into one record even when Whatnot emits a
    # weaker provisional price after the stronger/final one. Prefer the
    # strongest existing row instead of creating a second auction result.
    if rows:
        best_row = rows[0]
        best_price = float(best_row.get("sale_price") or 0)
        if best_price >= target_price:
            return best_row
    for row in rows:
        row_price = float(row.get("sale_price") or 0)
        if row_price <= 0 or isclose(row_price, target_price, rel_tol=0.0, abs_tol=0.0001):
            return row
    return None


def record_auction_result(session_id, lot_id=None, lot_number=None, winner_username=None, customer_id=None,
                          sale_price=0, fees=0, cost_price=0, product_name=None, barcode=None, sku=None,
                          products_sold_count=0, source_event_id=None):
    _require_company_postgres_runtime("company_results")
    now = utc_now()
    sale_price = float(sale_price or 0)
    fees = float(fees or 0)
    cost_price = float(cost_price or 0)
    profit = sale_price - fees - cost_price
    margin_pct = (profit / sale_price * 100.0) if sale_price else 0.0
    result_source_event_id = source_event_id or f"local-{uuid.uuid4()}"
    existing = get_auction_result_by_source_event_id(result_source_event_id)
    if not existing:
        existing = find_duplicate_auction_result(
            session_id,
            lot_id=lot_id,
            lot_number=lot_number,
            winner_username=winner_username,
            sale_price=sale_price,
        )
    if existing:
        existing_id = int(existing["id"])
        existing_price = float(existing.get("sale_price") or 0)
        should_upgrade = False
        if sale_price > 0 and existing_price <= 0:
            should_upgrade = True
        elif sale_price > existing_price:
            should_upgrade = True
        if should_upgrade:
            try:
                with pg_domain_tx("company_results", "auction_results_upsert") as (_pg_conn, cur):
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results
                        SET sold_at = %s,
                            sale_price = %s,
                            fees = %s,
                            cost_price = %s,
                            profit = %s,
                            margin_pct = %s,
                            winner_username = COALESCE(%s, winner_username),
                            product_name = COALESCE(%s, product_name),
                            barcode = COALESCE(%s, barcode),
                            sku = COALESCE(%s, sku),
                            source_event_id = COALESCE(%s, source_event_id)
                        WHERE id = %s
                        RETURNING *
                        """,
                        (
                            now,
                            sale_price,
                            fees,
                            cost_price,
                            profit,
                            margin_pct,
                            winner_username,
                            product_name,
                            barcode,
                            sku,
                            result_source_event_id,
                            existing_id,
                        ),
                    )
                row = _pg_fetchone_dict(cur)
                if not row:
                    raise ValueError(f"auction result {existing_id} not found")
                existing = get_auction_result(existing_id)
            except Exception as exc:
                log_cutover_event(
                    "company_results",
                    "postgres_primary_failed_closed",
                    "auction_results",
                    existing_id,
                    {"error": str(exc)},
                )
                raise
            _recalc_session_totals(session_id)
        existing["_created"] = False
        return existing
    try:
        with pg_domain_tx("company_results", "auction_results_insert") as (_pg_conn, cur):
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.auction_results (
                    session_id, lot_id, lot_number, winner_username, customer_id,
                    sold_at, sale_price, fees, cost_price, profit, margin_pct,
                    product_name, barcode, sku, products_sold_count, source_event_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_event_id) DO NOTHING
                RETURNING *
                """,
                (
                    int(session_id), lot_id, str(lot_number) if lot_number is not None else None,
                    winner_username, customer_id, now, sale_price, fees, cost_price,
                    profit, margin_pct, product_name, barcode, sku,
                    int(products_sold_count or 0), result_source_event_id,
                ),
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE source_event_id = %s",
                    (result_source_event_id,),
                )
                row = _pg_fetchone_dict(cur)
            if not row:
                raise ValueError("auction result insert did not return a row")
        result = get_auction_result(int(row["id"]))
        if winner_username:
            create_buyer_group(session_id, winner_username, customer_id=customer_id)
            _recalc_buyer_group(session_id, winner_username)
        _recalc_session_totals(session_id)
        result["_created"] = True
        return result
    except Exception as exc:
        log_cutover_event(
            "company_results",
            "postgres_primary_failed_closed",
            "auction_results",
            result_source_event_id,
            {"error": str(exc)},
        )
        raise


def update_auction_result(result_id, **fields):
    _require_company_postgres_runtime("company_results")
    allowed = {
        "lot_number", "winner_username", "customer_id", "sold_at",
        "sale_price", "fees", "cost_price", "product_name", "barcode",
        "sku", "products_sold_count",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    result_id = int(result_id)
    current = get_auction_result(result_id)
    if not current:
        return None

    sale_price = float(updates.get("sale_price", current.get("sale_price") or 0) or 0)
    fees = float(updates.get("fees", current.get("fees") or 0) or 0)
    cost_price = float(updates.get("cost_price", current.get("cost_price") or 0) or 0)
    updates["sale_price"] = sale_price
    updates["fees"] = fees
    updates["cost_price"] = cost_price
    updates["profit"] = sale_price - fees - cost_price
    updates["margin_pct"] = (updates["profit"] / sale_price * 100.0) if sale_price else 0.0

    old_winner = current.get("winner_username")
    session_id = int(current.get("session_id"))

    try:
        linked_id = None
        with pg_domain_tx("company_results", "auction_results_update") as (_pg_conn, cur):
                assignments = ", ".join(f"{key} = %s" for key in updates)
                params = list(updates.values()) + [result_id]
                cur.execute(
                    f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results SET {assignments} WHERE id = %s RETURNING *",
                    params,
                )
                row = _pg_fetchone_dict(cur)
                if not row:
                    raise ValueError(f"auction result {result_id} not found")
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments WHERE auction_result_id = %s",
                    (result_id,),
                )
                linked = _pg_fetchone_dict(cur)
                if linked:
                    linked_id = int(linked["id"])
                    pwa_updates = {}
                    if "lot_number" in updates:
                        pwa_updates["lot_number"] = updates["lot_number"]
                    if "winner_username" in updates:
                        pwa_updates["winner_username"] = updates["winner_username"]
                    if "sale_price" in updates:
                        pwa_updates["sale_price"] = sale_price
                    if "product_name" in updates:
                        product_name = str(updates["product_name"] or "").strip()
                        if product_name.endswith(" x1"):
                            product_name = product_name[:-3]
                        pwa_updates["assigned_product_name"] = product_name or None
                    if "barcode" in updates:
                        pwa_updates["assigned_barcode"] = updates["barcode"]
                    if "sku" in updates:
                        pwa_updates["assigned_sku"] = updates["sku"]
                    if "cost_price" in updates:
                        pwa_updates["assigned_cost_price"] = cost_price
                    if pwa_updates:
                        pwa_updates["updated_at"] = utc_now()
                        pwa_sql = ", ".join(f"{key} = %s" for key in pwa_updates)
                        cur.execute(
                            f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments SET {pwa_sql} WHERE id = %s",
                            list(pwa_updates.values()) + [linked_id],
                        )
    except Exception as exc:
        log_cutover_event(
            "company_results",
            "postgres_primary_failed_closed",
            "auction_results",
            result_id,
            {"error": str(exc)},
        )
        raise

    if old_winner:
        _recalc_buyer_group(session_id, old_winner)
    new_winner = updates.get("winner_username") or old_winner
    if new_winner:
        create_buyer_group(session_id, new_winner, customer_id=updates.get("customer_id", current.get("customer_id")))
        _recalc_buyer_group(session_id, new_winner)
    _recalc_session_totals(session_id)
    return get_auction_result(result_id)


def update_pending_winner_assignment_lot_number(assignment_id, lot_number):
    _require_company_postgres_runtime("company_pending")
    assignment = get_pending_winner_assignment(assignment_id)
    normalized_lot = str(lot_number or "").strip()
    if not assignment or not normalized_lot:
        return None

    old_lot = str(assignment.get("lot_number") or "").strip()
    session_id = int(assignment.get("session_id") or 0) if assignment.get("session_id") else None
    lot_id = assignment.get("lot_id")
    now = utc_now()

    if session_id:
        lot = None
        if lot_id:
            lot = rename_company_lot(int(lot_id), normalized_lot)
            lot_id = lot.get("id") if lot else lot_id
        else:
            if old_lot:
                lot = get_company_lot_by_number(session_id, old_lot)
            if not lot:
                lot = get_company_lot_by_number(session_id, normalized_lot)
            if not lot:
                lot = create_company_lot(session_id, normalized_lot, status="open")
            elif str(lot.get("lot_number") or "").strip() != normalized_lot:
                lot = rename_company_lot(int(lot["id"]), normalized_lot)
            lot_id = lot.get("id") if lot else lot_id

        session_row = get_company_session(session_id)
        if session_row and str(session_row.get("current_lot_number") or "").strip() == old_lot:
            update_company_session(session_id, current_lot_number=normalized_lot)

    try:
        with pg_domain_tx("company_pending", "pending_winner_assignments_lot_number") as (_pg_conn, cur):
            if lot_id:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET lot_number = %s, lot_id = %s, updated_at = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (normalized_lot, int(lot_id), now, int(assignment_id)),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET lot_number = %s, updated_at = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (normalized_lot, now, int(assignment_id)),
                )
            row = _fetchone_dict_pg(cur)
            if not row:
                raise ValueError(f"pending assignment {assignment_id} not found in postgres")
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignments",
            assignment_id,
            {"error": str(exc), "operation": "update_lot_number"},
        )
        raise

    if assignment.get("auction_result_id"):
        update_auction_result(int(assignment["auction_result_id"]), lot_number=normalized_lot)

    if session_id:
        try:
            _recalc_session_totals(int(session_id))
        except Exception:
            pass
    return get_pending_winner_assignment(assignment_id)


def delete_pending_winner_assignment(assignment_id):
    _require_company_postgres_runtime("company_pending")
    _require_company_postgres_runtime("company_results")
    _require_company_postgres_runtime("company_orders")
    _require_company_postgres_runtime("company_lots")
    assignment = get_pending_winner_assignment(assignment_id)
    if not assignment:
        return False

    current_status = str(assignment.get("status") or "").strip().lower()
    if current_status == "confirmed":
        assignment = undo_confirm_pending_winner_assignment(int(assignment_id))
        if not assignment:
            return False

    assignment = get_pending_winner_assignment(assignment_id)
    if not assignment:
        return False

    for item in list(assignment.get("assigned_items") or []):
        try:
            remove_pending_winner_assignment_item(int(assignment_id), int(item["id"]))
        except Exception:
            pass

    assignment = get_pending_winner_assignment(assignment_id)
    if not assignment:
        return False

    session_id = int(assignment.get("session_id") or 0) if assignment.get("session_id") else None
    auction_result_id = int(assignment.get("auction_result_id") or 0) if assignment.get("auction_result_id") else None
    lot_id = int(assignment.get("lot_id") or 0) if assignment.get("lot_id") else None
    lot_number = str(assignment.get("lot_number") or "").strip()
    winner_username = str(assignment.get("winner_username") or "").strip()

    try:
        with pg_domain_tx("company_pending", "pending_winner_assignment_delete") as (_pg_conn, cur):
            sale_order_ids = []
            if auction_result_id:
                cur.execute(
                    f"""
                    SELECT DISTINCT sale_order_id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                    WHERE auction_result_id = %s
                      AND sale_order_id IS NOT NULL
                    """,
                    (auction_result_id,),
                )
                sale_order_ids = [int(row[0]) for row in cur.fetchall() if row[0]]
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines WHERE auction_result_id = %s",
                    (auction_result_id,),
                )

            cur.execute(
                f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items WHERE assignment_id = %s",
                (int(assignment_id),),
            )
            cur.execute(
                f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments WHERE id = %s",
                (int(assignment_id),),
            )

            if auction_result_id:
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE id = %s",
                    (auction_result_id,),
                )

            if lot_id:
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items WHERE lot_id = %s",
                    (lot_id,),
                )
                cur.execute(
                    f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments WHERE lot_id = %s LIMIT 1",
                    (lot_id,),
                )
                remaining_assignment = _pg_fetchone_dict(cur)
                cur.execute(
                    f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE lot_id = %s LIMIT 1",
                    (lot_id,),
                )
                remaining_result = _pg_fetchone_dict(cur)
                if not remaining_assignment and not remaining_result:
                    cur.execute(
                        f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots WHERE id = %s",
                        (lot_id,),
                    )

            for sale_order_id in sale_order_ids:
                _pg_recalc_sale_order_txn(cur, int(sale_order_id))
                cur.execute(
                    f"SELECT COUNT(*) AS c FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines WHERE sale_order_id = %s",
                    (int(sale_order_id),),
                )
                line_count_row = _pg_fetchone_dict(cur) or {}
                if not int(line_count_row.get("c") or 0):
                    cur.execute(
                        f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders WHERE id = %s",
                        (int(sale_order_id),),
                    )
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignment_delete",
            assignment_id,
            {"error": str(exc)},
        )
        raise

    if session_id and lot_number and winner_username:
        try:
            _recalc_buyer_group(int(session_id), winner_username)
        except Exception:
            pass
    if session_id:
        try:
            session_row = get_company_session(int(session_id))
            if session_row and str(session_row.get("current_lot_number") or "").strip() == lot_number:
                update_company_session(int(session_id), current_lot_number=None)
        except Exception:
            pass
        try:
            _recalc_session_totals(int(session_id))
        except Exception:
            pass
    return True


def get_pending_winner_assignment(assignment_id):
    _require_company_postgres_runtime("company_pending")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT pwa.*, p.name AS assigned_product_display_name, p.media_url AS assigned_product_image_url
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = pwa.assigned_product_id
                WHERE pwa.id = %s
                """,
                (int(assignment_id),),
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                return None
            cur.execute(
                f"""
                SELECT pwai.*, p.media_url AS image_url, p.on_hand_qty
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items pwai
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = pwai.product_id
                WHERE pwai.assignment_id = %s
                ORDER BY pwai.id ASC
                """,
                (int(assignment_id),),
            )
            row["assigned_items"] = _pg_fetchall_dict(cur)
            postgres_value = _hydrate_pending_winner_assignment(None, row)
    return postgres_value


def list_pending_winner_assignments(session_id=None, statuses=None, limit=200):
    query = """
        SELECT pwa.*, p.name AS assigned_product_display_name, p.media_url AS assigned_product_image_url
        FROM {table_pwa} pwa
        LEFT JOIN {table_products} p ON p.id = pwa.assigned_product_id
        WHERE 1=1
    """
    clean_statuses = [str(s).strip() for s in (statuses or []) if str(s).strip()]
    _require_company_postgres_runtime("company_pending")
    ensure_wave1_postgres_schema()
    pg_query = query.format(
        table_pwa=f"{POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments",
        table_products=f"{POSTGRES_SIDECAR_SCHEMA}.products",
    )
    pg_params = []
    if session_id is not None:
        pg_query += " AND pwa.session_id = %s"
        pg_params.append(int(session_id))
    if clean_statuses:
        pg_query += f" AND pwa.status IN ({','.join('%s' for _ in clean_statuses)})"
        pg_params.extend(clean_statuses)
    pg_query += " ORDER BY CASE WHEN pwa.status = 'pending' THEN 0 WHEN pwa.status = 'assigned' THEN 1 ELSE 2 END, pwa.detected_at DESC LIMIT %s"
    pg_params.append(int(limit))
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(pg_query, tuple(pg_params))
            rows = _pg_fetchall_dict(cur)
            for row in rows:
                cur.execute(
                    f"""
                    SELECT pwai.*, p.media_url AS image_url, p.on_hand_qty
                    FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items pwai
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = pwai.product_id
                    WHERE pwai.assignment_id = %s
                    ORDER BY pwai.id ASC
                    """,
                    (int(row["id"]),),
                )
                row["assigned_items"] = _pg_fetchall_dict(cur)
            postgres_value = [_hydrate_pending_winner_assignment(None, row) for row in rows]
    return postgres_value


def _list_pending_winner_assignment_items(conn, assignment_id):
    return _fetchall_dict(
        conn,
        """
        SELECT pwai.*, p.media_url AS image_url, p.on_hand_qty
        FROM pending_winner_assignment_items pwai
        LEFT JOIN products p ON p.id = pwai.product_id
        WHERE pwai.assignment_id = ?
        ORDER BY pwai.id ASC
        """,
        (int(assignment_id),),
    )


def _hydrate_pending_winner_assignment(conn, row):
    if not row:
        return row
    items = row.get("assigned_items") if isinstance(row, dict) and row.get("assigned_items") is not None else _list_pending_winner_assignment_items(conn, row["id"])
    row["assigned_items"] = items
    row["assigned_items_count"] = sum(int(item.get("qty") or 0) for item in items)
    row["assigned_items_cost"] = round(sum(float(item.get("unit_cost") or 0) * int(item.get("qty") or 0) for item in items), 2)
    if items:
        if len(items) == 1 and int(items[0].get("qty") or 0) == 1:
            item = items[0]
            row["assigned_product_id"] = item.get("product_id")
            row["assigned_barcode"] = item.get("barcode")
            row["assigned_sku"] = item.get("sku")
            row["assigned_product_name"] = item.get("product_name")
            row["assigned_cost_price"] = float(item.get("unit_cost") or 0)
            row["assigned_product_display_name"] = item.get("product_name")
            row["assigned_product_image_url"] = item.get("image_url")
        else:
            row["assigned_product_id"] = None
            row["assigned_barcode"] = None
            row["assigned_sku"] = None
            row["assigned_product_name"] = ", ".join(
                f"{item.get('product_name')} x{int(item.get('qty') or 0)}" for item in items
            )
            row["assigned_cost_price"] = row["assigned_items_cost"]
            row["assigned_product_display_name"] = row["assigned_product_name"]
            row["assigned_product_image_url"] = items[0].get("image_url")
    return row


def _pg_recalc_sale_order_txn(cur, sale_order_id):
    cur.execute(
        f"""
        SELECT COALESCE(SUM(subtotal), 0) AS subtotal
        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
        WHERE sale_order_id = %s
        """,
        (int(sale_order_id),),
    )
    row = _pg_fetchone_dict(cur) or {}
    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_orders
        SET subtotal = %s,
            total_amount = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (
            row.get("subtotal") or 0,
            row.get("subtotal") or 0,
            utc_now(),
            int(sale_order_id),
        ),
    )


def _pg_recalc_buyer_group_txn(cur, session_id, buyer_username):
    cur.execute(
        f"""
        SELECT
            COUNT(*) AS total_lots_won,
            COALESCE(SUM(products_sold_count), 0) AS total_items,
            COALESCE(SUM(sale_price), 0) AS total_revenue,
            COALESCE(SUM(cost_price), 0) AS total_cost,
            COALESCE(SUM(fees), 0) AS total_fees,
            COALESCE(SUM(profit), 0) AS total_profit
        FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results
        WHERE session_id = %s AND winner_username = %s
        """,
        (int(session_id), buyer_username),
    )
    row = _pg_fetchone_dict(cur) or {}
    revenue = float(row.get("total_revenue") or 0)
    profit = float(row.get("total_profit") or 0)
    margin = (profit / revenue * 100.0) if revenue else 0.0
    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.buyer_groups
        SET total_items = %s,
            total_lots_won = %s,
            total_revenue = %s,
            total_cost = %s,
            total_fees = %s,
            total_profit = %s,
            overall_margin = %s,
            updated_at = %s
        WHERE session_id = %s AND buyer_username = %s
        """,
        (
            int(row.get("total_items") or 0),
            int(row.get("total_lots_won") or 0),
            revenue,
            float(row.get("total_cost") or 0),
            float(row.get("total_fees") or 0),
            profit,
            margin,
            utc_now(),
            int(session_id),
            buyer_username,
        ),
    )


def _pg_upsert_buyer_group_txn(cur, session_id, buyer_username, customer_id=None):
    now = utc_now()
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.buyer_groups (
            session_id, customer_id, buyer_username,
            total_items, total_lots_won, total_revenue, total_cost, total_profit, overall_margin, total_fees,
            created_at, updated_at
        ) VALUES (%s, %s, %s, 0, 0, 0, 0, 0, 0, 0, %s, %s)
        ON CONFLICT (session_id, buyer_username)
        DO UPDATE SET customer_id = COALESCE(EXCLUDED.customer_id, {POSTGRES_SIDECAR_SCHEMA}.buyer_groups.customer_id),
                      updated_at = EXCLUDED.updated_at
        RETURNING *
        """,
        (int(session_id), customer_id, buyer_username, now, now),
    )
    return _pg_fetchone_dict(cur)


def _pg_create_sale_order_txn(
    cur,
    *,
    session_id=None,
    customer_id=None,
    buyer_group_id=None,
    whatnot_buyer_username=None,
    state="draft",
    subtotal=0,
    total_amount=0,
    ordered_at=None,
    notes=None,
    order_source="whatnot",
    external_order_ref=None,
    fulfillment_status="pending",
    payment_status="unpaid",
    tracking_carrier="usps",
):
    now = utc_now()
    order_number = f"SO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.sale_orders (
            order_number, session_id, customer_id, buyer_group_id,
            whatnot_buyer_username, order_source, external_order_ref,
            state, fulfillment_status, payment_status, subtotal, total_amount,
            notes, ordered_at, created_at, updated_at, tracking_carrier
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            order_number,
            session_id,
            customer_id,
            buyer_group_id,
            whatnot_buyer_username,
            order_source or "whatnot",
            external_order_ref,
            state,
            fulfillment_status,
            payment_status,
            subtotal,
            total_amount,
            notes,
            ordered_at or now,
            now,
            now,
            tracking_carrier or "usps",
        ),
    )
    row = _pg_fetchone_dict(cur)
    if buyer_group_id:
        cur.execute(
            f"""
            UPDATE {POSTGRES_SIDECAR_SCHEMA}.buyer_groups
            SET sale_order_id = %s, updated_at = %s
            WHERE id = %s
            """,
            (int(row["id"]), now, int(buyer_group_id)),
        )
    return row


def _pg_add_sale_order_line_txn(
    cur,
    *,
    sale_order_id,
    product_id=None,
    lot_id=None,
    auction_result_id=None,
    description=None,
    qty=1,
    unit_price=0,
    inventory_applied=0,
):
    now = utc_now()
    qty_value = float(qty or 0)
    unit_price_value = float(unit_price or 0)
    subtotal = qty_value * unit_price_value
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines (
            sale_order_id, product_id, lot_id, auction_result_id,
            description, qty, unit_price, subtotal,
            inventory_applied, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            int(sale_order_id),
            product_id,
            lot_id,
            auction_result_id,
            description,
            qty_value,
            unit_price_value,
            subtotal,
            1 if inventory_applied else 0,
            now,
            now,
        ),
    )
    line = _pg_fetchone_dict(cur)
    _pg_recalc_sale_order_txn(cur, int(sale_order_id))
    return line


def queue_pending_winner_assignment(session_id, lot_id=None, auction_result_id=None, lot_number=None,
                                    winner_username=None, sale_price=0, source_event_id=None,
                                    detected_at=None, notes=None):
    _require_company_postgres_runtime("company_pending")
    now = utc_now()
    detected_at = detected_at or now
    norm_lot_number = str(lot_number or '').strip() or None
    norm_winner = str(winner_username or '').strip() or None
    norm_sale_price = float(sale_price or 0)
    try:
        with pg_domain_tx("company_pending", "pending_winner_assignments_queue") as (_pg_conn, cur):
            existing = None
            assignment_id = None
            lot_id_value = int(lot_id) if lot_id is not None else None
            auction_result_id_value = int(auction_result_id) if auction_result_id is not None else None

            if norm_lot_number:
                cur.execute(
                    f"""
                    SELECT id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    WHERE session_id = %s
                      AND COALESCE(lot_number, '') = COALESCE(%s, '')
                      AND status = 'confirmed'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (int(session_id), norm_lot_number),
                )
                confirmed_for_lot = _pg_fetchone_dict(cur)
                if confirmed_for_lot:
                    assignment_id = int(confirmed_for_lot["id"])

            if assignment_id is None and source_event_id:
                cur.execute(
                    f"""
                    SELECT id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    WHERE source_event_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (str(source_event_id),),
                )
                existing = _pg_fetchone_dict(cur)

            if assignment_id is None and not existing and auction_result_id_value:
                cur.execute(
                    f"""
                    SELECT id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    WHERE auction_result_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (auction_result_id_value,),
                )
                existing = _pg_fetchone_dict(cur)

            if assignment_id is None and not existing and norm_lot_number and norm_winner:
                cur.execute(
                    f"""
                    SELECT id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    WHERE session_id = %s
                      AND LOWER(COALESCE(winner_username, '')) = LOWER(COALESCE(%s, ''))
                      AND COALESCE(lot_number, '') = COALESCE(%s, '')
                      AND status IN ('pending', 'assigned', 'needs_review')
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (int(session_id), norm_winner, norm_lot_number),
                )
                existing = _pg_fetchone_dict(cur)

            if assignment_id is None and existing:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET lot_id = COALESCE(%s, lot_id),
                        auction_result_id = COALESCE(%s, auction_result_id),
                        sale_price = CASE
                            WHEN %s > COALESCE(sale_price, 0) THEN %s
                            ELSE COALESCE(sale_price, 0)
                        END,
                        source_event_id = COALESCE(%s, source_event_id),
                        detected_at = CASE
                            WHEN COALESCE(detected_at, '') < COALESCE(%s, '') THEN %s
                            ELSE detected_at
                        END,
                        notes = COALESCE(%s, notes),
                        updated_at = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        lot_id_value,
                        auction_result_id_value,
                        norm_sale_price,
                        norm_sale_price,
                        str(source_event_id) if source_event_id else None,
                        detected_at,
                        detected_at,
                        notes,
                        now,
                        int(existing["id"]),
                    ),
                )
                row = _pg_fetchone_dict(cur)
                if not row:
                    raise ValueError(f"pending assignment {existing['id']} not found in postgres")
                assignment_id = int(row["id"])

            if assignment_id is None:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments (
                        session_id, lot_id, auction_result_id, lot_number, winner_username, sale_price,
                        source_event_id, detected_at, status, assigned_cost_price, notes, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        int(session_id),
                        lot_id_value,
                        auction_result_id_value,
                        norm_lot_number,
                        norm_winner,
                        norm_sale_price,
                        str(source_event_id) if source_event_id else None,
                        detected_at,
                        0.0,
                        notes,
                        now,
                        now,
                    ),
                )
                row = _pg_fetchone_dict(cur)
                assignment_id = int(row["id"])
        return get_pending_winner_assignment(assignment_id)
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignments_queue",
            f"{session_id}:{norm_lot_number or ''}:{norm_winner or ''}",
            {"error": str(exc), "source_event_id": source_event_id, "auction_result_id": auction_result_id},
        )
        raise

def assign_pending_winner_product(assignment_id, product_id):
    _require_company_postgres_runtime("company_pending")
    assignment_id = int(assignment_id)
    product_id = int(product_id)
    now = utc_now()
    existing_assignment = get_pending_winner_assignment(assignment_id)
    if not existing_assignment:
        return existing_assignment
    # Allow adding more items even if a lot was already confirmed:
    # we transparently undo the confirm and proceed with adding the next product.
    if existing_assignment.get("status") == "confirmed":
        try:
            undo_confirm_pending_winner_assignment(assignment_id)
        except Exception:
            pass
        existing_assignment = get_pending_winner_assignment(assignment_id)
        if not existing_assignment:
            return None
    product = get_product(product_id)
    if not product:
        return None
    try:
        with pg_domain_tx("company_pending", "pending_winner_assignment_items_assign") as (_pg_conn, cur):
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                WHERE assignment_id = %s AND product_id = %s
                ORDER BY id DESC LIMIT 1
                """,
                (assignment_id, product_id),
            )
            existing_item = _pg_fetchone_dict(cur)
            if existing_item:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                    SET qty = qty + 1,
                        updated_at = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (now, int(existing_item["id"])),
                )
                _pg_fetchone_dict(cur)
            else:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items (
                        assignment_id, product_id, barcode, sku, product_name, unit_cost, qty, reserved_qty, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 1, 0, %s, %s)
                    RETURNING id
                    """,
                    (
                        assignment_id,
                        product_id,
                        product.get("barcode"),
                        product.get("sku"),
                        product.get("name"),
                        float(product.get("cost_price") or 0),
                        now,
                        now,
                    ),
                )
                _pg_fetchone_dict(cur)
            cur.execute(
                f"""
                SELECT product_name, unit_cost, qty
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                WHERE assignment_id = %s
                ORDER BY id ASC
                """,
                (assignment_id,),
            )
            item_rows = [
                {"product_name": row[0], "unit_cost": float(row[1] or 0), "qty": int(row[2] or 0)}
                for row in cur.fetchall()
            ]
            total_cost = round(sum(float(item.get("unit_cost") or 0) * int(item.get("qty") or 0) for item in item_rows), 2)
            total_qty = sum(int(item.get("qty") or 0) for item in item_rows)
            summary_name = ", ".join(
                f"{item.get('product_name')} x{int(item.get('qty') or 0)}" for item in item_rows
            )
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                SET assigned_product_id = NULL,
                    assigned_barcode = NULL,
                    assigned_sku = NULL,
                    assigned_product_name = %s,
                    assigned_cost_price = %s,
                    assigned_at = %s,
                    status = 'assigned',
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    summary_name if total_qty > 1 else product.get("name"),
                    total_cost,
                    now,
                    now,
                    assignment_id,
                ),
            )
        return get_pending_winner_assignment(assignment_id)
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignment_items",
            assignment_id,
            {"error": str(exc), "product_id": product_id},
        )
        raise


def remove_pending_winner_assignment_item(assignment_id, item_id):
    _require_company_postgres_runtime("company_pending")
    assignment_id = int(assignment_id)
    item_id = int(item_id)
    now = utc_now()
    assignment = get_pending_winner_assignment(assignment_id)
    if not assignment or assignment.get("status") == "confirmed":
        return assignment
    try:
        with pg_domain_tx("company_pending", "pending_winner_assignment_items_remove") as (_pg_conn, cur):
            cur.execute(
                f"""
                SELECT product_id, reserved_qty
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                WHERE id = %s AND assignment_id = %s
                """,
                (item_id, assignment_id),
            )
            item = _pg_fetchone_dict(cur)
            if not item:
                return get_pending_winner_assignment(assignment_id)
            reserved_qty = int(item.get("reserved_qty") or 0)
            if reserved_qty > 0:
                _pg_record_inventory_movement_txn(
                    cur,
                    int(item["product_id"]),
                    "in",
                    reserved_qty,
                    reason=f"Winner assignment released: lot {assignment.get('lot_number') or '—'} @ {assignment.get('winner_username') or 'unknown'}",
                    reference_type="winner_assignment_release",
                    reference_id=item_id,
                )
            cur.execute(
                f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items WHERE id = %s AND assignment_id = %s",
                (item_id, assignment_id),
            )
            cur.execute(
                f"""
                SELECT product_name, unit_cost, qty
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                WHERE assignment_id = %s
                ORDER BY id ASC
                """,
                (assignment_id,),
            )
            item_rows = [
                {"product_name": row[0], "unit_cost": float(row[1] or 0), "qty": int(row[2] or 0)}
                for row in cur.fetchall()
            ]
            if item_rows:
                total_cost = round(sum(float(row.get("unit_cost") or 0) * int(row.get("qty") or 0) for row in item_rows), 2)
                total_qty = sum(int(row.get("qty") or 0) for row in item_rows)
                summary_name = ", ".join(
                    f"{row.get('product_name')} x{int(row.get('qty') or 0)}" for row in item_rows
                )
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET assigned_product_id = NULL,
                        assigned_barcode = NULL,
                        assigned_sku = NULL,
                        assigned_product_name = %s,
                        assigned_cost_price = %s,
                        assigned_at = COALESCE(assigned_at, %s),
                        status = 'assigned',
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        summary_name if total_qty > 1 else item_rows[0].get("product_name"),
                        total_cost,
                        now,
                        now,
                        assignment_id,
                    ),
                )
            else:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET assigned_product_id = NULL,
                        assigned_barcode = NULL,
                        assigned_sku = NULL,
                        assigned_product_name = NULL,
                        assigned_cost_price = 0,
                        assigned_at = NULL,
                        status = 'pending',
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (now, assignment_id),
                )
        return get_pending_winner_assignment(assignment_id)
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignment_items",
            item_id,
            {"error": str(exc), "assignment_id": assignment_id},
        )
        raise


def _reopen_linked_sale_orders_for_assignment_txn(conn, auction_result_id):
    if not auction_result_id:
        return
    now = utc_now()
    conn.execute(
        """
        UPDATE sale_orders
        SET state = CASE WHEN state = 'cancel' THEN 'draft' ELSE state END,
            fulfillment_status = CASE
                WHEN fulfillment_status IS NULL OR fulfillment_status = '' THEN 'pending'
                ELSE fulfillment_status
            END,
            payment_status = CASE
                WHEN payment_status IS NULL OR payment_status = '' OR payment_status = 'unpaid' THEN 'unpaid'
                ELSE payment_status
            END,
            updated_at = ?
        WHERE id IN (
            SELECT DISTINCT sale_order_id
            FROM sale_order_lines
            WHERE auction_result_id = ?
              AND sale_order_id IS NOT NULL
        )
        """,
        (now, int(auction_result_id)),
    )


def _pg_reopen_linked_sale_orders_for_assignment_txn(cur, auction_result_id):
    if not auction_result_id:
        return
    now = utc_now()
    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_orders
        SET state = CASE WHEN state = 'cancel' THEN 'draft' ELSE state END,
            fulfillment_status = CASE
                WHEN fulfillment_status IS NULL OR fulfillment_status = '' THEN 'pending'
                ELSE fulfillment_status
            END,
            payment_status = CASE
                WHEN payment_status IS NULL OR payment_status = '' OR payment_status = 'unpaid' THEN 'unpaid'
                ELSE payment_status
            END,
            updated_at = %s
        WHERE id IN (
            SELECT DISTINCT sale_order_id
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
            WHERE auction_result_id = %s
              AND sale_order_id IS NOT NULL
        )
        """,
        (now, int(auction_result_id)),
    )


def _restore_assignment_financials_txn(conn, assignment):
    if not assignment or not assignment.get("auction_result_id"):
        return
    session_row = get_company_session(int(assignment["session_id"])) if assignment.get("session_id") else None
    order_source = _session_order_source(session_row)
    ar = _fetchone_dict(
        conn,
        "SELECT * FROM auction_results WHERE id = ?",
        (int(assignment["auction_result_id"]),),
    )
    if not ar:
        return
    item_rows = _fetchall_dict(
        conn,
        "SELECT * FROM pending_winner_assignment_items WHERE assignment_id = ? ORDER BY id ASC",
        (int(assignment["id"]),),
    )
    sale_price = float(assignment.get("sale_price") or ar.get("sale_price") or 0)
    total_qty = sum(int(item.get("qty") or 0) for item in item_rows) or int(ar.get("products_sold_count") or 0) or 1
    total_cost = round(
        sum(float(item.get("unit_cost") or 0) * int(item.get("qty") or 0) for item in item_rows),
        2,
    )
    fees = float(ar.get("fees") or 0)
    if fees <= 0 and sale_price > 0:
        fees = _estimate_platform_fees(sale_price, order_source=order_source)
    profit = sale_price - fees - total_cost
    margin_pct = (profit / sale_price * 100.0) if sale_price else 0.0

    if len(item_rows) == 1 and int(item_rows[0].get("qty") or 0) == 1:
        product_name = item_rows[0].get("product_name") or ar.get("product_name")
        barcode = item_rows[0].get("barcode")
        sku = item_rows[0].get("sku")
    elif item_rows:
        product_name = ", ".join(
            f"{item.get('product_name')} x{int(item.get('qty') or 0)}"
            for item in item_rows
        )
        barcode = None
        sku = None
    else:
        product_name = assignment.get("assigned_product_name") or ar.get("product_name") or (assignment.get("lot_number") or "Awaiting product assignment")
        barcode = assignment.get("assigned_barcode") or ar.get("barcode")
        sku = assignment.get("assigned_sku") or ar.get("sku")

    conn.execute(
        """
        UPDATE auction_results
        SET product_name = ?,
            barcode = ?,
            sku = ?,
            cost_price = ?,
            fees = ?,
            profit = ?,
            margin_pct = ?,
            products_sold_count = ?
        WHERE id = ?
        """,
        (
            product_name,
            barcode,
            sku,
            total_cost,
            fees,
            profit,
            margin_pct,
            total_qty,
            int(assignment["auction_result_id"]),
        ),
    )
    _sync_linked_sale_orders_for_assignment(conn, int(assignment["auction_result_id"]))


def _pg_restore_assignment_financials_txn(cur, assignment):
    if not assignment or not assignment.get("auction_result_id"):
        return
    session_row = get_company_session(int(assignment["session_id"])) if assignment.get("session_id") else None
    order_source = _session_order_source(session_row)
    cur.execute(
        f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE id = %s",
        (int(assignment["auction_result_id"]),),
    )
    ar = _pg_fetchone_dict(cur)
    if not ar:
        return
    cur.execute(
        f"""
        SELECT *
        FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
        WHERE assignment_id = %s
        ORDER BY id ASC
        """,
        (int(assignment["id"]),),
    )
    item_rows = _pg_fetchall_dict(cur)
    sale_price = float(assignment.get("sale_price") or ar.get("sale_price") or 0)
    total_qty = sum(int(item.get("qty") or 0) for item in item_rows) or int(ar.get("products_sold_count") or 0) or 1
    total_cost = round(
        sum(float(item.get("unit_cost") or 0) * int(item.get("qty") or 0) for item in item_rows),
        2,
    )
    fees = float(ar.get("fees") or 0)
    if fees <= 0 and sale_price > 0:
        fees = _estimate_platform_fees(sale_price, order_source=order_source)
    profit = sale_price - fees - total_cost
    margin_pct = (profit / sale_price * 100.0) if sale_price else 0.0

    if len(item_rows) == 1 and int(item_rows[0].get("qty") or 0) == 1:
        product_name = item_rows[0].get("product_name") or ar.get("product_name")
        barcode = item_rows[0].get("barcode")
        sku = item_rows[0].get("sku")
    elif item_rows:
        product_name = ", ".join(
            f"{item.get('product_name')} x{int(item.get('qty') or 0)}"
            for item in item_rows
        )
        barcode = None
        sku = None
    else:
        product_name = assignment.get("assigned_product_name") or ar.get("product_name") or (assignment.get("lot_number") or "Awaiting product assignment")
        barcode = assignment.get("assigned_barcode") or ar.get("barcode")
        sku = assignment.get("assigned_sku") or ar.get("sku")

    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results
        SET product_name = %s,
            barcode = %s,
            sku = %s,
            cost_price = %s,
            fees = %s,
            profit = %s,
            margin_pct = %s,
            products_sold_count = %s
        WHERE id = %s
        """,
        (
            product_name,
            barcode,
            sku,
            total_cost,
            fees,
            profit,
            margin_pct,
            total_qty,
            int(assignment["auction_result_id"]),
        ),
    )
    _pg_sync_linked_sale_orders_for_assignment_txn(cur, int(assignment["auction_result_id"]))


def reserve_pending_winner_assignment_items(assignment_id, *, reason_prefix="TikTok pending order reserved"):
    _require_company_postgres_runtime("company_pending")
    assignment = get_pending_winner_assignment(assignment_id)
    if not assignment:
        return None
    now = utc_now()
    try:
        with pg_domain_tx("company_pending", "pending_winner_assignment_items_reserve") as (_pg_conn, cur):
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                SET reserved_qty = qty,
                    updated_at = %s
                WHERE assignment_id = %s
                  AND COALESCE(reserved_qty, 0) < COALESCE(qty, 0)
                """,
                (now, int(assignment_id)),
            )
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignment_items_reserve",
            assignment_id,
            {"error": str(exc)},
        )
        raise
    return get_pending_winner_assignment(assignment_id)


def update_pending_winner_assignment_status(assignment_id, status, notes=None):
    _require_company_postgres_runtime("company_pending")
    status = str(status or "").strip().lower()
    if status not in {"pending", "assigned", "needs_review", "confirmed", "payment_review", "payment_cancelled"}:
      return None
    assignment = get_pending_winner_assignment(assignment_id)
    if not assignment:
        return None
    current_status = str(assignment.get("status") or "").strip().lower()
    if status == "confirmed":
        if current_status in {"payment_review", "payment_cancelled"} and assignment.get("auction_result_id"):
            with pg_domain_tx("company_pending", "pending_winner_assignment_pre_confirm_reopen") as (_pg_conn, cur):
                _pg_reopen_linked_sale_orders_for_assignment_txn(cur, int(assignment["auction_result_id"]))
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET status = 'assigned',
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (utc_now(), int(assignment_id)),
                )
        return confirm_pending_winner_assignment(int(assignment_id))
    if current_status == "confirmed":
        assignment = undo_confirm_pending_winner_assignment(int(assignment_id))
        if not assignment:
            return None
        current_status = str(assignment.get("status") or "").strip().lower()
    now = utc_now()
    try:
        with pg_domain_tx("company_pending", "pending_winner_assignment_status_update") as (_pg_conn, cur):
            if current_status in {"payment_review", "payment_cancelled"} and status in {"pending", "assigned", "needs_review"}:
                cur.execute(
                    f"""
                    SELECT *
                    FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                    WHERE assignment_id = %s
                    ORDER BY id ASC
                    """,
                    (int(assignment_id),),
                )
                _pg_fetchall_dict(cur)
                if assignment.get("auction_result_id"):
                    _pg_reopen_linked_sale_orders_for_assignment_txn(cur, int(assignment["auction_result_id"]))
                    _pg_restore_assignment_financials_txn(cur, assignment)
            if status in {"payment_review", "payment_cancelled"}:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                    SET reserved_qty = 0,
                        updated_at = %s
                    WHERE assignment_id = %s
                      AND COALESCE(reserved_qty, 0) > 0
                    """,
                    (now, int(assignment_id)),
                )
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                SET status = %s,
                    notes = COALESCE(%s, notes),
                    updated_at = %s
                WHERE id = %s
                """,
                (status, notes, now, int(assignment_id)),
            )
            if status in {"payment_review", "payment_cancelled"} and assignment.get("auction_result_id"):
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results
                    SET cost_price = 0,
                        fees = 0,
                        profit = 0,
                        margin_pct = 0,
                        products_sold_count = 0
                    WHERE id = %s
                    """,
                    (int(assignment["auction_result_id"]),),
                )
                _pg_sync_linked_sale_orders_for_assignment_txn(cur, int(assignment["auction_result_id"]))
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignment_status_update",
            assignment_id,
            {"error": str(exc), "status": status},
        )
        raise
    if assignment.get("session_id"):
        try:
            _recalc_session_totals(int(assignment["session_id"]))
        except Exception:
            pass
    return get_pending_winner_assignment(assignment_id)


def _estimate_whatnot_fees(sale_price, fee_pct=10.9, fixed_fee=0.50):
    sale_price = float(sale_price or 0)
    if sale_price <= 0:
        return 0.0
    return round(sale_price * float(fee_pct or 0) / 100.0 + float(fixed_fee or 0), 2)


def _session_order_source(session_row):
    session_stream_url = str((session_row or {}).get("stream_url") or (session_row or {}).get("show_id") or "").strip().lower()
    if session_stream_url.startswith("tiktok:"):
        return "tiktok_live"
    return "whatnot"


def _estimate_platform_fees(sale_price, order_source="whatnot", fee_pct=10.9, fixed_fee=0.50):
    sale_price = float(sale_price or 0)
    source = str(order_source or "").strip().lower()
    if sale_price <= 0:
        return 0.0
    if source == "tiktok_live":
        return round(sale_price * 0.06, 2)
    return _estimate_whatnot_fees(sale_price, fee_pct=fee_pct, fixed_fee=fixed_fee)


def confirm_pending_winner_assignment(assignment_id):
    _require_company_postgres_runtime("company_pending")
    _require_company_postgres_runtime("company_results")
    _require_company_postgres_runtime("company_orders")
    _require_company_postgres_runtime("company_lots")
    assignment = get_pending_winner_assignment(assignment_id)
    # A fast operator can trigger confirm immediately after scan assignment.
    # Give the just-written assignment a brief chance to become visible across
    # DB connections before we declare the confirm failed.
    if assignment and not (assignment.get("assigned_items_count") or assignment.get("assigned_product_id")) and assignment.get("status") in {"pending", "assigned"}:
        for _ in range(4):
            time.sleep(0.06)
            assignment = get_pending_winner_assignment(assignment_id)
            if assignment and (assignment.get("assigned_items_count") or assignment.get("assigned_product_id")):
                break
    if assignment and assignment.get("status") == "confirmed":
        return assignment
    if not assignment or not (assignment.get("assigned_items_count") or assignment.get("assigned_product_id")):
        return None
    now = utc_now()
    sale_price = float(assignment.get("sale_price") or 0)
    items = assignment.get("assigned_items") or []
    if not items and assignment.get("assigned_product_id"):
        items = [{
            "product_id": assignment.get("assigned_product_id"),
            "barcode": assignment.get("assigned_barcode"),
            "sku": assignment.get("assigned_sku"),
            "product_name": assignment.get("assigned_product_name"),
            "unit_cost": float(assignment.get("assigned_cost_price") or 0),
            "qty": 1,
        }]
    total_qty = sum(int(item.get("qty") or 0) for item in items) or 1
    cost_price = round(sum(float(item.get("unit_cost") or 0) * int(item.get("qty") or 0) for item in items), 2)
    sale_order = None
    session_order_source = "whatnot"
    session_row = None
    if assignment.get("session_id"):
        try:
            session_row = get_company_session(int(assignment["session_id"]))
        except Exception:
            session_row = None
        session_order_source = _session_order_source(session_row)
    if assignment.get("session_id") and assignment.get("winner_username"):
        customer_id = None
        ar_lookup = get_auction_result(int(assignment["auction_result_id"])) if assignment.get("auction_result_id") else None
        customer_id = ar_lookup.get("customer_id") if ar_lookup else None
        sale_order = get_or_create_buyer_sale_order(
            int(assignment["session_id"]),
            assignment["winner_username"],
            customer_id=customer_id,
            order_source=session_order_source,
        )
    try:
        with pg_domain_tx("company_pending", "pending_winner_assignment_confirm") as (_pg_conn, cur):
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                WHERE assignment_id = %s
                ORDER BY id ASC
                """,
                (int(assignment_id),),
            )
            items = _pg_fetchall_dict(cur) or items
            total_qty = sum(int(item.get("qty") or 0) for item in items) or 1
            cost_price = round(sum(float(item.get("unit_cost") or 0) * int(item.get("qty") or 0) for item in items), 2)
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                SET reserved_qty = qty,
                    updated_at = %s
                WHERE assignment_id = %s
                  AND COALESCE(reserved_qty, 0) <> COALESCE(qty, 0)
                """,
                (now, int(assignment_id)),
            )
            ar = None
            if assignment.get("auction_result_id"):
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE id = %s",
                    (int(assignment["auction_result_id"]),),
                )
                ar = _pg_fetchone_dict(cur)
            if ar:
                fees = float(ar.get("fees") or 0)
                if fees <= 0 and sale_price > 0:
                    fees = _estimate_platform_fees(sale_price, order_source=session_order_source)
                profit = sale_price - fees - cost_price
                margin_pct = (profit / sale_price * 100.0) if sale_price else 0.0
                joined_name = ", ".join(f"{item.get('product_name')} x{int(item.get('qty') or 0)}" for item in items)
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results
                    SET product_name = %s,
                        barcode = NULL,
                        sku = NULL,
                        cost_price = %s,
                        fees = %s,
                        profit = %s,
                        margin_pct = %s,
                        products_sold_count = %s
                    WHERE id = %s
                    """,
                    (
                        joined_name,
                        cost_price,
                        fees,
                        profit,
                        margin_pct,
                        total_qty,
                        int(assignment["auction_result_id"]),
                    ),
                )
                ar["fees"] = fees
                if sale_order:
                    for item in items:
                        product_id = int(item["product_id"])
                        qty = int(item.get("qty") or 0) or 1
                        cur.execute(
                            f"""
                            SELECT id
                            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                            WHERE auction_result_id = %s AND product_id = %s
                            ORDER BY id ASC
                            LIMIT 1
                            """,
                            (int(assignment["auction_result_id"]), product_id),
                        )
                        if _pg_fetchone_dict(cur):
                            continue
                        unit_price = round(float(sale_price or 0) / total_qty, 4)
                        _pg_add_sale_order_line_txn(
                            cur,
                            sale_order_id=int(sale_order["id"]),
                            product_id=product_id,
                            lot_id=assignment.get("lot_id"),
                            auction_result_id=int(assignment["auction_result_id"]),
                            description=item.get("product_name"),
                            qty=qty,
                            unit_price=unit_price,
                            inventory_applied=0,
                        )
                    _pg_recalc_sale_order_txn(cur, int(sale_order["id"]))
            if assignment.get("lot_id"):
                for item in items:
                    cur.execute(
                        f"""
                        SELECT id
                        FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items
                        WHERE lot_id = %s AND product_id = %s AND status = 'sold'
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (int(assignment["lot_id"]), int(item["product_id"])),
                    )
                    if _pg_fetchone_dict(cur):
                        continue
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.company_lot_items (
                            lot_id, product_id, barcode, sku, product_name, unit_cost, qty_snapshot, scanned_at, status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'sold')
                        """,
                        (
                            int(assignment["lot_id"]),
                            int(item["product_id"]),
                            item.get("barcode"),
                            item.get("sku"),
                            item.get("product_name"),
                            float(item.get("unit_cost") or 0),
                            int(item.get("qty") or 0) or 1,
                            now,
                        ),
                    )
                if ar:
                    lot_profit = float(ar.get("sale_price") or sale_price) - float(ar.get("fees") or 0) - cost_price
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lots
                        SET total_cost = %s,
                            total_profit = %s,
                            sold_products = %s,
                            total_products = CASE WHEN total_products < %s THEN %s ELSE total_products END,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (cost_price, lot_profit, total_qty, total_qty, total_qty, now, int(assignment["lot_id"])),
                    )
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                SET status = 'confirmed',
                    confirmed_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (now, now, int(assignment_id)),
            )
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignment_confirm",
            assignment_id,
            {"error": str(exc)},
        )
        raise
    if sale_order and sale_order.get("id"):
        apply_sale_order_inventory(int(sale_order["id"]))
        with pg_domain_tx("company_pending", "pending_winner_assignment_confirm_release_reservation") as (_pg_conn, cur):
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                SET reserved_qty = 0,
                    updated_at = %s
                WHERE assignment_id = %s
                """,
                (utc_now(), int(assignment_id)),
            )
    if assignment.get("session_id"):
        try:
            _recalc_session_totals(int(assignment["session_id"]))
        except Exception:
            pass
    return get_pending_winner_assignment(assignment_id)


def approve_payments_from_picklist_lots(session_id, lot_numbers):
    _require_company_postgres_runtime("company_pending")
    _require_company_postgres_runtime("company_results")
    _require_company_postgres_runtime("company_orders")
    """
    Treat lots found on uploaded Whatnot labels/packing slips as paid proof.

    Whatnot can approve payment hours after a stream. If an operator had already
    moved a lot to payment_review/payment_cancelled, seeing that lot in the
    official label PDF means we should restore it to the paid sale flow.
    """
    if not session_id:
        return {"approved_lots": 0, "approved_orders": 0, "assignment_ids": []}
    normalized_lots = []
    seen = set()
    for lot in lot_numbers or []:
        value = str(lot or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized_lots.append(value)
    if not normalized_lots:
        return {"approved_lots": 0, "approved_orders": 0, "assignment_ids": []}

    placeholders = ",".join("%s" for _ in normalized_lots)
    params = [int(session_id), *normalized_lots]
    now = utc_now()
    approved_order_ids = set()
    with pg_domain_tx("company_pending", "picklist_payment_approval_prepare") as (_pg_conn, cur):
        cur.execute(
            f"""
            SELECT
                pwa.id AS assignment_id,
                pwa.status AS assignment_status,
                pwa.winner_username,
                pwa.auction_result_id,
                pwa.session_id,
                ar.lot_number,
                ar.sale_price,
                ar.fees,
                ar.cost_price,
                ar.lot_id
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa
                ON pwa.auction_result_id = ar.id
            WHERE ar.session_id = %s
              AND TRIM(COALESCE(ar.lot_number, '')) IN ({placeholders})
              AND COALESCE(pwa.status, '') IN ('payment_review', 'payment_cancelled')
            ORDER BY ar.sold_at ASC, ar.id ASC
            """,
            tuple(params),
        )
        rows = _pg_fetchall_dict(cur)
        for row in rows:
            buyer = (row.get("winner_username") or "").strip()
            if not buyer:
                continue
            cur.execute(
                f"""
                SELECT id
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders
                WHERE session_id = %s
                  AND LOWER(COALESCE(whatnot_buyer_username, '')) = LOWER(%s)
                """,
                (int(session_id), buyer),
            )
            existing_orders = _pg_fetchall_dict(cur)
            approved_order_ids.update(int(order["id"]) for order in existing_orders if order.get("id"))
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_orders
                SET state = 'sale',
                    payment_status = 'paid',
                    fulfillment_status = CASE
                        WHEN fulfillment_status IS NULL OR fulfillment_status = '' THEN 'pending'
                        ELSE fulfillment_status
                    END,
                    updated_at = %s
                WHERE session_id = %s
                  AND LOWER(COALESCE(whatnot_buyer_username, '')) = LOWER(%s)
                """,
                (now, int(session_id), buyer),
            )

    approved_assignment_ids = []
    approved_lots = set()
    touched_result_ids = set()
    try:
        session_row = get_company_session(int(session_id))
    except Exception:
        session_row = None
    session_order_source = _session_order_source(session_row)
    for row in rows:
        assignment_id = row.get("assignment_id")
        if not assignment_id:
            continue
        approved_lots.add(str(row.get("lot_number") or "").strip())
        confirmed = confirm_pending_winner_assignment(int(assignment_id))
        if confirmed:
            approved_assignment_ids.append(int(assignment_id))
            if row.get("auction_result_id"):
                touched_result_ids.add(int(row["auction_result_id"]))
        else:
            sale_price = float(row.get("sale_price") or 0)
            cost_price = float(row.get("cost_price") or 0)
            fees = float(row.get("fees") or 0) or _estimate_platform_fees(sale_price, order_source=session_order_source)
            profit = sale_price - fees - cost_price
            margin_pct = (profit / sale_price * 100.0) if sale_price else 0.0
            with pg_domain_tx("company_pending", "picklist_payment_approval_manual_confirm") as (_pg_conn, cur):
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                    SET status = 'confirmed',
                        confirmed_at = COALESCE(confirmed_at, %s),
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (now, now, int(assignment_id)),
                )
                if row.get("auction_result_id"):
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results
                        SET fees = %s,
                            profit = %s,
                            margin_pct = %s
                        WHERE id = %s
                        """,
                        (fees, profit, margin_pct, int(row["auction_result_id"])),
                    )
                    touched_result_ids.add(int(row["auction_result_id"]))
            approved_assignment_ids.append(int(assignment_id))

    with pg_domain_tx("company_orders", "picklist_payment_approval_recalc_orders") as (_pg_conn, cur):
        for order_id in approved_order_ids:
            try:
                _pg_recalc_sale_order_txn(cur, int(order_id))
            except Exception:
                pass
    try:
        _recalc_session_totals(int(session_id))
    except Exception:
        pass
    return {
        "approved_lots": len(approved_lots),
        "approved_orders": len(approved_order_ids),
        "assignment_ids": approved_assignment_ids,
    }


def undo_confirm_pending_winner_assignment(assignment_id):
    _require_company_postgres_runtime("company_pending")
    _require_company_postgres_runtime("company_results")
    _require_company_postgres_runtime("company_orders")
    _require_company_postgres_runtime("company_lots")
    assignment = get_pending_winner_assignment(assignment_id)
    if not assignment or assignment.get("status") != "confirmed":
        return None
    now = utc_now()
    sale_price = float(assignment.get("sale_price") or 0)
    items = assignment.get("assigned_items") or []
    if not items and assignment.get("assigned_product_id"):
        items = [{
            "product_id": assignment.get("assigned_product_id"),
            "barcode": assignment.get("assigned_barcode"),
            "sku": assignment.get("assigned_sku"),
            "product_name": assignment.get("assigned_product_name"),
            "unit_cost": float(assignment.get("assigned_cost_price") or 0),
            "qty": 1,
        }]
    sale_order_ids = []
    try:
        with pg_domain_tx("company_pending", "pending_winner_assignment_undo_confirm_snapshot") as (_pg_conn, cur):
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                WHERE assignment_id = %s
                ORDER BY id ASC
                """,
                (int(assignment_id),),
            )
            item_rows = _pg_fetchall_dict(cur)
            for item in item_rows:
                qty = int(item.get("qty") or 0) or 1
                reserved_qty = int(item.get("reserved_qty") or 0)
                if reserved_qty < qty:
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignment_items
                        SET reserved_qty = qty,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (now, int(item["id"])),
                    )
            if assignment.get("auction_result_id"):
                cur.execute(
                    f"""
                    SELECT DISTINCT sale_order_id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                    WHERE auction_result_id = %s
                      AND sale_order_id IS NOT NULL
                    """,
                    (int(assignment["auction_result_id"]),),
                )
                sale_order_ids = [int(row[0]) for row in cur.fetchall() if row[0]]
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignment_undo_confirm_snapshot",
            assignment_id,
            {"error": str(exc)},
        )
        raise

    for sale_order_id in sale_order_ids:
        try:
            reverse_sale_order_inventory(int(sale_order_id))
        except Exception:
            pass

    try:
        with pg_domain_tx("company_pending", "pending_winner_assignment_undo_confirm") as (_pg_conn, cur):
            ar = None
            if assignment.get("auction_result_id"):
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results WHERE id = %s",
                    (int(assignment["auction_result_id"]),),
                )
                ar = _pg_fetchone_dict(cur)
            if ar:
                fees = float(ar.get("fees") or 0)
                profit = sale_price - fees
                margin_pct = (profit / sale_price * 100.0) if sale_price else 0.0
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results
                    SET product_name = %s,
                        barcode = NULL,
                        sku = NULL,
                        cost_price = 0,
                        profit = %s,
                        margin_pct = %s,
                        products_sold_count = 0
                    WHERE id = %s
                    """,
                    (
                        assignment.get("lot_number") or "Awaiting product assignment",
                        profit,
                        margin_pct,
                        int(assignment["auction_result_id"]),
                    ),
                )
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines WHERE auction_result_id = %s",
                    (int(assignment["auction_result_id"]),),
                )
                for sale_order_id in sale_order_ids:
                    _pg_recalc_sale_order_txn(cur, int(sale_order_id))
            if assignment.get("lot_id"):
                for item in items:
                    cur.execute(
                        f"""
                        DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items
                        WHERE lot_id = %s AND product_id = %s AND status = 'sold'
                        """,
                        (int(assignment["lot_id"]), int(item["product_id"])),
                    )
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lots
                    SET total_cost = 0,
                        total_profit = CASE WHEN winning_price IS NOT NULL THEN winning_price - fees ELSE total_profit END,
                        sold_products = 0,
                        total_products = CASE WHEN total_products > 0 THEN total_products ELSE 0 END,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (now, int(assignment["lot_id"])),
                )
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
                SET status = 'assigned',
                    confirmed_at = NULL,
                    updated_at = %s
                WHERE id = %s
                """,
                (now, int(assignment_id)),
            )
    except Exception as exc:
        log_cutover_event(
            "company_pending",
            "postgres_primary_failed_closed",
            "pending_winner_assignment_undo_confirm",
            assignment_id,
            {"error": str(exc)},
        )
        raise
    if assignment.get("session_id"):
        try:
            _recalc_session_totals(int(assignment["session_id"]))
        except Exception:
            pass
    return get_pending_winner_assignment(assignment_id)


def recalc_all_fees(fee_pct=10.9, fixed_fee=0.50):
    """Retroactively apply correct fees to ALL existing auction_results where fees == 0.

    Recalculates profit and margin, then cascades to buyer_groups and sessions.
    Returns count of updated records.
    """
    _require_company_postgres_runtime("company_results")
    ensure_wave1_postgres_schema()
    updated = 0
    affected_sessions = set()
    affected_buyers = set()
    with pg_domain_tx("company_results", "recalc_all_fees") as (_pg_conn, cur):
        cur.execute(
            f"""
            SELECT id, session_id, sale_price, cost_price, winner_username, lot_id
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results
            WHERE fees = 0 AND sale_price > 0
            """
        )
        rows = _pg_fetchall_dict(cur)
        for row in rows:
            sp = float(row["sale_price"] or 0)
            cp = float(row["cost_price"] or 0)
            try:
                session_row = get_company_session(int(row["session_id"])) if row.get("session_id") else None
            except Exception:
                session_row = None
            order_source = _session_order_source(session_row)
            fees = _estimate_platform_fees(sp, order_source=order_source, fee_pct=fee_pct, fixed_fee=fixed_fee)
            profit = sp - fees - cp
            margin = (profit / sp * 100.0) if sp else 0.0
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results
                SET fees = %s, profit = %s, margin_pct = %s
                WHERE id = %s
                """,
                (fees, profit, margin, int(row["id"])),
            )
            updated += 1
            affected_sessions.add(row["session_id"])
            if row.get("winner_username"):
                affected_buyers.add((row["session_id"], row["winner_username"]))
            if row.get("lot_id"):
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lots
                    SET fees = %s, total_profit = %s
                    WHERE id = %s
                    """,
                    (fees, profit, int(row["lot_id"])),
                )
            _pg_sync_linked_sale_orders_for_assignment_txn(cur, int(row["id"]))
    # Cascade recalc
    for sid, buyer in affected_buyers:
        try:
            _recalc_buyer_group(sid, buyer)
        except Exception:
            pass
    for sid in affected_sessions:
        try:
            _recalc_session_totals(sid)
        except Exception:
            pass
    return updated


def get_or_create_buyer_sale_order(session_id, winner_username, customer_id=None, order_source="whatnot"):
    _require_company_postgres_runtime("company_orders")
    """Return the existing draft sale order for this buyer/session, or create one."""
    try:
        with pg_domain_tx("company_orders", "sale_orders_get_or_create") as (_pg_conn, cur):
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.buyer_groups
                WHERE session_id = %s AND buyer_username = %s
                LIMIT 1
                """,
                (int(session_id), winner_username),
            )
            bg = _pg_fetchone_dict(cur)
            if not bg:
                bg = _pg_upsert_buyer_group_txn(cur, session_id, winner_username, customer_id=customer_id)
            elif customer_id and not bg.get("customer_id"):
                bg = _pg_upsert_buyer_group_txn(cur, session_id, winner_username, customer_id=customer_id)
            if bg.get("sale_order_id"):
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders WHERE id = %s",
                    (int(bg["sale_order_id"]),),
                )
                so = _pg_fetchone_dict(cur)
                if so and so.get("state") not in ("cancel",):
                    order_id = int(so["id"])
                else:
                    so = _pg_create_sale_order_txn(
                        cur,
                        session_id=int(session_id),
                        customer_id=customer_id,
                        buyer_group_id=int(bg["id"]),
                        whatnot_buyer_username=winner_username,
                        order_source=(order_source or "whatnot"),
                        state="draft",
                        subtotal=0,
                        total_amount=0,
                    )
                    order_id = int(so["id"])
            else:
                so = _pg_create_sale_order_txn(
                    cur,
                    session_id=int(session_id),
                    customer_id=customer_id,
                    buyer_group_id=int(bg["id"]),
                    whatnot_buyer_username=winner_username,
                    order_source=(order_source or "whatnot"),
                    state="draft",
                    subtotal=0,
                    total_amount=0,
                )
                order_id = int(so["id"])
        return get_sale_order(order_id)
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "sale_orders", f"{session_id}:{winner_username}", {"error": str(exc)})
        raise


def add_sale_order_line_for_item(sale_order_id, product_id=None, description=None, qty=1, unit_price=0,
                                 lot_id=None, auction_result_id=None):
    _require_company_postgres_runtime("company_orders")
    """Add a line to a sale order for a specific lot item. Does not touch inventory."""
    try:
        with pg_domain_tx("company_orders", "sale_order_lines") as (_pg_conn, cur):
            line = _pg_add_sale_order_line_txn(
                cur,
                sale_order_id=sale_order_id,
                product_id=product_id,
                lot_id=lot_id,
                auction_result_id=auction_result_id,
                description=description,
                qty=qty,
                unit_price=unit_price,
                inventory_applied=0,
            )
        return get_sale_order_line(int(line["id"]))
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "sale_order_lines", sale_order_id, {"error": str(exc)})
        raise


def _sale_order_inventory_should_be_applied(order):
    source = str((order or {}).get("order_source") or "").strip().lower()
    state = str((order or {}).get("state") or "").strip().lower()
    payment_status = str((order or {}).get("payment_status") or "").strip().lower()
    if source == "tiktok_live":
        return (
            int((order or {}).get("session_id") or 0) > 0
            and state == "sale"
            and payment_status == "paid"
            and str((order or {}).get("external_order_ref") or "").strip().lower().startswith("tiktok_live:")
        )
    return state == "sale" and payment_status == "paid"


def apply_sale_order_inventory(order_id):
    """Deduct inventory for all un-applied lines when order is confirmed."""
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    now = utc_now()
    applied = 0
    with pg_domain_tx("company_orders", "sale_order_inventory_apply") as (_pg_conn, cur):
        cur.execute(
            f"""
            SELECT order_number, session_id, order_source, state, payment_status,
                   fulfillment_status, tracking_status, delivered_at, external_order_ref
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders
            WHERE id = %s
            """,
            (int(order_id),),
        )
        order = _pg_fetchone_dict(cur)
        if not _sale_order_inventory_should_be_applied(order):
            return 0
        cur.execute(
            f"""
            SELECT *
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
            WHERE sale_order_id = %s AND product_id IS NOT NULL
            ORDER BY id ASC
            """,
            (int(order_id),),
        )
        lines = _pg_fetchall_dict(cur)
        for line in lines:
            qty = float(line.get("qty") or 1)
            cur.execute(
                f"""
                SELECT id
                FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
                WHERE product_id = %s
                  AND (
                        (reference_type = 'sale_order_line' AND reference_id = %s)
                     OR (reference_type = 'sale_order' AND reference_id = %s)
                  )
                LIMIT 1
                """,
                (int(line["product_id"]), int(line["id"]), int(order_id)),
            )
            existing_movement = _pg_fetchone_dict(cur)
            if existing_movement and line.get("inventory_applied"):
                continue
            if not existing_movement:
                _pg_record_inventory_movement_txn(
                    cur,
                    int(line["product_id"]),
                    "out",
                    -qty,
                    reason=f"Sale order confirmed: {(order or {}).get('order_number', order_id)}",
                    reference_type="sale_order_line",
                    reference_id=int(line["id"]),
                )
                applied += 1
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                SET inventory_applied = 1, updated_at = %s
                WHERE id = %s
                """,
                (now, int(line["id"])),
            )
    return applied


def reverse_sale_order_inventory(order_id):
    """Return inventory for all applied lines when order is cancelled."""
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    now = utc_now()
    reversed_count = 0
    with pg_domain_tx("company_orders", "sale_order_inventory_reverse") as (_pg_conn, cur):
        cur.execute(
            f"SELECT order_number FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders WHERE id = %s",
            (int(order_id),),
        )
        order = _pg_fetchone_dict(cur)
        cur.execute(
            f"""
            SELECT *
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
            WHERE sale_order_id = %s AND inventory_applied = 1 AND product_id IS NOT NULL
            ORDER BY id ASC
            """,
            (int(order_id),),
        )
        lines = _pg_fetchall_dict(cur)
        for line in lines:
            qty = float(line.get("qty") or 1)
            cur.execute(
                f"""
                SELECT id
                FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
                WHERE reference_type = 'sale_order_cancel'
                  AND reference_id = %s
                  AND product_id = %s
                LIMIT 1
                """,
                (int(order_id), int(line["product_id"])),
            )
            existing_movement = _pg_fetchone_dict(cur)
            if not existing_movement:
                _pg_record_inventory_movement_txn(
                    cur,
                    int(line["product_id"]),
                    "in",
                    qty,
                    reason=f"Sale order cancelled: {(order or {}).get('order_number', order_id)}",
                    reference_type="sale_order_cancel",
                    reference_id=int(order_id),
                )
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                SET inventory_applied = 0, updated_at = %s
                WHERE id = %s
                """,
                (now, int(line["id"])),
            )
            reversed_count += 1
    return reversed_count


def _sync_sale_order_inventory_state(order_id):
    order = get_sale_order(int(order_id))
    if not order:
        return {"applied": 0, "reversed": 0, "status": "missing"}
    if _sale_order_inventory_should_be_applied(order):
        applied = apply_sale_order_inventory(int(order_id))
        return {"applied": int(applied or 0), "reversed": 0, "status": "applied"}
    if str(order.get("order_source") or "").strip().lower() == "tiktok_live":
        return {"applied": 0, "reversed": 0, "status": "not_reversed_tiktok_live"}
    reversed_count = reverse_sale_order_inventory(int(order_id))
    return {"applied": 0, "reversed": int(reversed_count or 0), "status": "reversed"}


def list_auction_results(session_id=None, limit=500):
    _require_company_postgres_runtime("company_results")
    _auto_cancel_overdue_payment_reviews(session_id=session_id)
    pg_select_sql = f"""
        SELECT
            ar.id,
            ar.session_id,
            ar.lot_id,
            ar.lot_number,
            ar.winner_username,
            ar.customer_id,
            ar.sold_at,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.sale_price END AS sale_price,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.fees END AS fees,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.cost_price END AS cost_price,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.profit END AS profit,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.margin_pct END AS margin_pct,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.products_sold_count END AS products_sold_count,
            ar.product_name,
            ar.barcode,
            ar.sku,
            ar.source_event_id,
            ar.sale_price AS original_sale_price,
            ar.fees AS original_fees,
            ar.cost_price AS original_cost_price,
            ar.profit AS original_profit,
            ar.margin_pct AS original_margin_pct,
            pwa_status.id AS assignment_id,
            COALESCE(pwa_status.status, 'confirmed') AS assignment_status,
            c.display_name,
            c.whatnot_username
        FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = ar.customer_id
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa_status ON pwa_status.id = (
            SELECT pwa.id
            FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa
            WHERE pwa.auction_result_id = ar.id
            ORDER BY pwa.id DESC
            LIMIT 1
        )
    """
    dedup_filter_sql = _DEDUPED_AUCTION_RESULT_FILTER.replace(
        "FROM pending_winner_assignments",
        f"FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments",
    )
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if session_id is not None:
                cur.execute(
                    f"""
                    {pg_select_sql}
                    WHERE ar.session_id = %s
                      AND {dedup_filter_sql}
                    ORDER BY ar.sold_at DESC
                    LIMIT %s
                    """,
                    (int(session_id), int(limit)),
                )
            else:
                cur.execute(
                    f"""
                    {pg_select_sql}
                    WHERE {dedup_filter_sql}
                    ORDER BY ar.sold_at DESC
                    LIMIT %s
                    """,
                    (int(limit),),
                )
            return _pg_fetchall_dict(cur)


def list_auction_results_for_sessions(session_ids, limit_per_session=5000):
    _require_company_postgres_runtime("company_results")
    normalized_ids = [int(value) for value in (session_ids or []) if value is not None]
    if not normalized_ids:
        return []
    _auto_cancel_overdue_payment_reviews()

    pg_select_sql = f"""
        SELECT
            ar.id,
            ar.session_id,
            ar.lot_id,
            ar.lot_number,
            ar.winner_username,
            ar.customer_id,
            ar.sold_at,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.sale_price END AS sale_price,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.fees END AS fees,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.cost_price END AS cost_price,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.profit END AS profit,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.margin_pct END AS margin_pct,
            CASE WHEN COALESCE(pwa_status.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.products_sold_count END AS products_sold_count,
            ar.product_name,
            ar.barcode,
            ar.sku,
            ar.source_event_id,
            ar.sale_price AS original_sale_price,
            ar.fees AS original_fees,
            ar.cost_price AS original_cost_price,
            ar.profit AS original_profit,
            ar.margin_pct AS original_margin_pct,
            pwa_status.id AS assignment_id,
            COALESCE(pwa_status.status, 'confirmed') AS assignment_status,
            c.display_name,
            c.whatnot_username
        FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = ar.customer_id
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa_status ON pwa_status.id = (
            SELECT pwa.id
            FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa
            WHERE pwa.auction_result_id = ar.id
            ORDER BY pwa.id DESC
            LIMIT 1
        )
    """
    dedup_filter_sql = _DEDUPED_AUCTION_RESULT_FILTER.replace(
        "FROM pending_winner_assignments",
        f"FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments",
    )
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH ranked AS (
                    SELECT
                        base_rows.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY base_rows.session_id
                            ORDER BY base_rows.sold_at DESC, base_rows.id DESC
                        ) AS _session_rank
                    FROM (
                        {pg_select_sql}
                        WHERE ar.session_id = ANY(%s)
                          AND {dedup_filter_sql}
                    ) base_rows
                )
                SELECT *
                FROM ranked
                WHERE _session_rank <= %s
                ORDER BY sold_at DESC, id DESC
                """,
                (normalized_ids, max(1, int(limit_per_session or 5000))),
            )
            rows = _pg_fetchall_dict(cur)
    for row in rows:
        row.pop("_session_rank", None)
    return rows


def create_sale_order(session_id=None, customer_id=None, buyer_group_id=None, whatnot_buyer_username=None,
                      state="draft", subtotal=0, total_amount=0, ordered_at=None, notes=None,
                      order_source="whatnot", external_order_ref=None,
                      fulfillment_status="pending", payment_status="unpaid"):
    _require_company_postgres_runtime("company_orders")
    try:
        with pg_domain_tx("company_orders", "sale_orders") as (_pg_conn, cur):
            row = _pg_create_sale_order_txn(
                cur,
                session_id=session_id,
                customer_id=customer_id,
                buyer_group_id=buyer_group_id,
                whatnot_buyer_username=whatnot_buyer_username,
                state=state,
                subtotal=subtotal,
                total_amount=total_amount,
                ordered_at=ordered_at,
                notes=notes,
                order_source=order_source,
                external_order_ref=external_order_ref,
                fulfillment_status=fulfillment_status,
                payment_status=payment_status,
            )
        return get_sale_order(int(row["id"]))
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "sale_orders", buyer_group_id or customer_id or session_id, {"error": str(exc)})
        raise


def add_sale_order_line(sale_order_id, product_id=None, description=None, qty=1, unit_price=0, inventory_applied=0, lot_id=None):
    _require_company_postgres_runtime("company_orders")
    try:
        with pg_domain_tx("company_orders", "sale_order_lines") as (_pg_conn, cur):
            line = _pg_add_sale_order_line_txn(
                cur,
                sale_order_id=sale_order_id,
                product_id=product_id,
                description=description,
                qty=qty,
                unit_price=unit_price,
                inventory_applied=inventory_applied,
                lot_id=lot_id,
            )
        return get_sale_order_line(int(line["id"]))
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "sale_order_lines", sale_order_id, {"error": str(exc)})
        raise


def record_inventory_movement(product_id, movement_type, qty_delta, reason=None, reference_type=None, reference_id=None):
    _require_company_postgres_runtime("inventory_movements")
    return _record_inventory_movement_txn(
        None,
        product_id,
        movement_type,
        qty_delta,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
    )


def deduct_inventory_for_lot(lot_id, reason_prefix="Auction win"):
    """Deduct inventory for all items in a lot that have a product_id.

    Skips items already deducted (checks inventory_movements by reference).
    """
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    deducted = []
    with pg_domain_tx("company_lots", "deduct_inventory_for_lot") as (_pg_conn, cur):
        cur.execute(
            f"""
            SELECT *
            FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items
            WHERE lot_id = %s AND product_id IS NOT NULL AND status = 'sold'
            ORDER BY id ASC
            """,
            (int(lot_id),),
        )
        items = _pg_fetchall_dict(cur)
        for item in items:
            product_id = int(item["product_id"])
            qty = float(item.get("qty_snapshot") or 1)
            ref_id = int(item["id"])
            cur.execute(
                f"""
                SELECT id
                FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
                WHERE reference_type = 'auction_lot_item' AND reference_id = %s
                LIMIT 1
                """,
                (ref_id,),
            )
            existing = _pg_fetchone_dict(cur)
            if existing:
                continue
            _pg_record_inventory_movement_txn(
                cur,
                product_id,
                "out",
                -qty,
                reason=f"{reason_prefix}: lot {lot_id}, item {item.get('product_name', '')}",
                reference_type="auction_lot_item",
                reference_id=ref_id,
            )
            deducted.append(ref_id)
    return deducted


def _pg_list_products(active_only=False, low_stock_only=False, limit=None, offset=0, include_sales_metrics=True):
    select_cols = ",\n            ".join(f"p.{field}" for field in PRODUCT_LIST_SELECT_FIELDS)
    sales_metrics_sql = """
                        (
                            COALESCE((
                                SELECT COUNT(*)
                                FROM {schema}.auction_results ar
                                WHERE {canon}
                                    AND (
                                        (p.sku IS NOT NULL AND p.sku != '' AND LOWER(COALESCE(ar.sku, '')) = LOWER(p.sku))
                                        OR (p.barcode IS NOT NULL AND p.barcode != '' AND COALESCE(ar.barcode, '') = p.barcode)
                                        OR (p.name IS NOT NULL AND p.name != '' AND LOWER(COALESCE(ar.product_name, '')) = LOWER(p.name))
                                    )
                            ), 0)
                        ) AS times_sold,
                        (
                            (
                                SELECT MAX(sold_at)
                                FROM (
                                    SELECT ar.sold_at AS sold_at
                                    FROM {schema}.auction_results ar
                                    WHERE {canon}
                                        AND (
                                            (p.sku IS NOT NULL AND p.sku != '' AND LOWER(COALESCE(ar.sku, '')) = LOWER(p.sku))
                                            OR (p.barcode IS NOT NULL AND p.barcode != '' AND COALESCE(ar.barcode, '') = p.barcode)
                                            OR (p.name IS NOT NULL AND p.name != '' AND LOWER(COALESCE(ar.product_name, '')) = LOWER(p.name))
                                        )
                                ) sold_rows
                            )
                        ) AS last_sold_at,
                        (
                            COALESCE((
                                SELECT COALESCE(SUM(ar.sale_price), 0)
                                FROM {schema}.auction_results ar
                                WHERE {canon}
                                    AND (
                                        (p.sku IS NOT NULL AND p.sku != '' AND LOWER(COALESCE(ar.sku, '')) = LOWER(p.sku))
                                        OR (p.barcode IS NOT NULL AND p.barcode != '' AND COALESCE(ar.barcode, '') = p.barcode)
                                        OR (p.name IS NOT NULL AND p.name != '' AND LOWER(COALESCE(ar.product_name, '')) = LOWER(p.name))
                                    )
                            ), 0)
                        ) AS sales_revenue
    """.format(schema=POSTGRES_SIDECAR_SCHEMA, canon=_PG_CANONICAL_AUCTION_RESULT_FILTER)
    if not include_sales_metrics:
        sales_metrics_sql = """
                        0 AS times_sold,
                        NULL AS last_sold_at,
                        0 AS sales_revenue
        """
    query = f"""
        SELECT
            {select_cols},
            pc.name AS category_name,
                        {sales_metrics_sql}
        FROM {POSTGRES_SIDECAR_SCHEMA}.products p
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
        WHERE 1=1
    """
    if active_only:
        query += " AND p.active = 1"
    if low_stock_only:
        query += " AND p.on_hand_qty <= p.low_stock_threshold"
    query += " ORDER BY LOWER(COALESCE(p.name, '')) ASC, p.id ASC"
    params = []
    if limit is not None:
        query += " LIMIT %s OFFSET %s"
        params.extend([max(1, int(limit or 100)), max(0, int(offset or 0))])
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params) if params else None)
            return _pg_fetchall_dict(cur)


def list_products(active_only=False, low_stock_only=False, limit=None, offset=0, include_sales_metrics=True):
    _require_company_postgres_runtime("inventory_products")
    postgres_value = _pg_list_products(
        active_only=active_only,
        low_stock_only=low_stock_only,
        limit=limit,
        offset=offset,
        include_sales_metrics=include_sales_metrics,
    )
    with _pg_connect() as conn:
        _ensure_fragrance_research_pg_tables(conn)
        with conn.cursor() as cur:
            return _pg_attach_fragrance_research_many(cur, postgres_value)


def upsert_setting(key, value):
    _require_company_postgres_runtime("settings")
    try:
        now = utc_now()
        with pg_domain_tx("settings", "app_settings") as (_pg_conn, cur):
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.app_settings (key, value, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT(key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                RETURNING key, value, updated_at
                """,
                (key, str(value), now),
            )
            row = _pg_fetchone_dict(cur)
        return row
    except Exception as exc:
        log_cutover_event("settings", "postgres_primary_failed_closed", "app_settings", key, {"error": str(exc)})
        raise


def list_settings():
    _require_company_postgres_runtime("settings")
    try:
        with pg_domain_tx("settings", "app_settings_list") as (_pg_conn, cur):
            cur.execute(
                f"""
                SELECT key, value, updated_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.app_settings
                ORDER BY key ASC
                """
            )
            return _pg_fetchall_dict(cur)
    except Exception as exc:
        log_cutover_event("settings", "postgres_primary_failed_closed", "app_settings_list", "all", {"error": str(exc)})
        raise


def get_setting_map():
    return {row["key"]: row["value"] for row in list_settings()}


def _normalize_review_username(value):
    return str(value or "").strip().lstrip("@").lower()


def upsert_customer_review(
    review_key,
    seller_username,
    reviewer_username,
    reviewer_display_name=None,
    rating=None,
    review_text=None,
    reply_text=None,
    source_url=None,
    raw_payload=None,
):
    _require_company_postgres_runtime("reviews")
    try:
        clean_review_key = str(review_key or "").strip()
        clean_seller = _normalize_review_username(seller_username)
        clean_reviewer = _normalize_review_username(reviewer_username)
        if not clean_review_key or not clean_seller or not clean_reviewer:
            return None
        now = utc_now()
        display_name = " ".join(str(reviewer_display_name or "").strip().split()) or clean_reviewer
        review_body = re.sub(r"\s+", " ", str(review_text or "")).strip()
        reply_body = re.sub(r"\s+", " ", str(reply_text or "")).strip()
        try:
            rating_value = None if rating in (None, "") else float(rating)
        except Exception:
            rating_value = None
        payload_json = _json_dumps(raw_payload or {})
        with pg_domain_tx("reviews", "customer_reviews") as (_pg_conn, cur):
            cur.execute(
                f"""
                SELECT id
                FROM {POSTGRES_SIDECAR_SCHEMA}.customers
                WHERE LOWER(COALESCE(whatnot_username, '')) = %s
                LIMIT 1
                """,
                (clean_reviewer,),
            )
            customer = _pg_fetchone_dict(cur)
            matched_customer_id = customer.get("id") if customer else None
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.customer_reviews (
                    review_key, seller_username, reviewer_username, reviewer_display_name,
                    matched_customer_id, rating, review_text, reply_text,
                    source_url, raw_payload, scraped_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(review_key)
                DO UPDATE SET
                    seller_username = EXCLUDED.seller_username,
                    reviewer_username = EXCLUDED.reviewer_username,
                    reviewer_display_name = EXCLUDED.reviewer_display_name,
                    matched_customer_id = EXCLUDED.matched_customer_id,
                    rating = EXCLUDED.rating,
                    review_text = EXCLUDED.review_text,
                    reply_text = EXCLUDED.reply_text,
                    source_url = EXCLUDED.source_url,
                    raw_payload = EXCLUDED.raw_payload,
                    scraped_at = EXCLUDED.scraped_at,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
                """,
                (
                    clean_review_key,
                    clean_seller,
                    clean_reviewer,
                    display_name,
                    matched_customer_id,
                    rating_value,
                    review_body or None,
                    reply_body or None,
                    source_url or None,
                    payload_json,
                    now,
                    now,
                ),
            )
            row = _pg_fetchone_dict(cur)
        if row and row.get("id"):
            with pg_domain_tx("reviews", "customer_reviews_readback") as (_pg_conn, cur):
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.customer_reviews WHERE id = %s",
                    (int(row["id"]),),
                )
                return _pg_fetchone_dict(cur)
        return None
    except Exception as exc:
        log_cutover_event("reviews", "postgres_primary_failed_closed", "customer_reviews", review_key, {"error": str(exc)})
        raise


def list_customer_reviews(customer_id, limit=50):
    _require_company_postgres_runtime("reviews")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    cr.*,
                    c.display_name AS customer_name,
                    c.whatnot_username AS customer_username
                FROM {POSTGRES_SIDECAR_SCHEMA}.customer_reviews cr
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = cr.matched_customer_id
                WHERE cr.matched_customer_id = %s
                ORDER BY COALESCE(cr.updated_at, cr.scraped_at) DESC, cr.id DESC
                LIMIT %s
                """,
                (int(customer_id), int(limit or 50)),
            )
            return _pg_fetchall_dict(cur)


def list_reviews_feed(q=None, matched_only=False, limit=250):
    _require_company_postgres_runtime("reviews")
    query = f"""
        SELECT
            cr.*,
            c.display_name AS customer_name,
            c.whatnot_username AS customer_username
        FROM {POSTGRES_SIDECAR_SCHEMA}.customer_reviews cr
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = cr.matched_customer_id
        WHERE 1=1
    """
    params = []
    if matched_only:
        query += " AND cr.matched_customer_id IS NOT NULL"
    if q:
        ql = f"%{str(q or '').strip().lower()}%"
        query += """
            AND (
                LOWER(COALESCE(cr.reviewer_username, '')) LIKE %s
                OR LOWER(COALESCE(cr.reviewer_display_name, '')) LIKE %s
                OR LOWER(COALESCE(cr.review_text, '')) LIKE %s
                OR LOWER(COALESCE(cr.reply_text, '')) LIKE %s
                OR LOWER(COALESCE(c.display_name, '')) LIKE %s
                OR LOWER(COALESCE(c.whatnot_username, '')) LIKE %s
            )
        """
        params.extend([ql, ql, ql, ql, ql, ql])
    query += """
        ORDER BY COALESCE(cr.updated_at, cr.scraped_at) DESC, cr.id DESC
        LIMIT %s
    """
    params.append(int(limit or 250))
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_reviews,
                    SUM(CASE WHEN matched_customer_id IS NOT NULL THEN 1 ELSE 0 END) AS matched_reviews,
                    SUM(CASE WHEN COALESCE(reply_text, '') <> '' THEN 1 ELSE 0 END) AS replied_reviews,
                    COALESCE(AVG(rating), 0) AS avg_rating
                FROM {POSTGRES_SIDECAR_SCHEMA}.customer_reviews
                """
            )
            summary = _pg_fetchone_dict(cur) or {}
    return {"rows": rows, "summary": summary}


def _pg_inventory_summary():
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_products,
                    SUM(on_hand_qty * cost_price) AS total_stock_value,
                    SUM(CASE WHEN on_hand_qty <= low_stock_threshold THEN 1 ELSE 0 END) AS low_stock_count,
                    SUM(CASE WHEN on_hand_qty <= 0 AND product_type IN ('product', 'storable') THEN 1 ELSE 0 END) AS out_of_stock_count,
                    SUM(CASE WHEN COALESCE(barcode, '') = '' THEN 1 ELSE 0 END) AS missing_barcode_count,
                    SUM(CASE WHEN COALESCE(media_url, '') = '' AND COALESCE(image_path, '') = '' THEN 1 ELSE 0 END) AS missing_image_count,
                    SUM(CASE WHEN COALESCE(notes_verified, 0) = 0 THEN 1 ELSE 0 END) AS unverified_notes_count
                FROM {POSTGRES_SIDECAR_SCHEMA}.products
                WHERE active = 1
                """
            )
            row = _fetchone_dict_pg(cur) or {}
            return {
                "total_products": row.get("total_products") or 0,
                "total_stock_value": round(float(row.get("total_stock_value") or 0), 2),
                "low_stock_count": row.get("low_stock_count") or 0,
                "out_of_stock_count": row.get("out_of_stock_count") or 0,
                "missing_barcode_count": row.get("missing_barcode_count") or 0,
                "missing_image_count": row.get("missing_image_count") or 0,
                "unverified_notes_count": row.get("unverified_notes_count") or 0,
            }


def inventory_summary():
    _require_company_postgres_runtime("inventory_products")
    return _pg_inventory_summary()


def create_in_house_sale(employee_name=None, employee_id=None, product_id=None, barcode=None, sku=None, qty=1, unit_price=None, notes=None, sold_at=None):
    _require_company_postgres_runtime("in_house")
    try:
        with pg_domain_tx("in_house", "in_house_sales") as (_pg_conn, cur):
            sale = _pg_create_in_house_sale_txn(
                cur,
                employee_name=employee_name,
                employee_id=employee_id,
                product_id=product_id,
                barcode=barcode,
                sku=sku,
                qty=qty,
                unit_price=unit_price,
                notes=notes,
                sold_at=sold_at,
            )
            if sale and sale.get("id"):
                _pg_record_inventory_movement_txn(
                    cur,
                    int(sale["product_id"]),
                    "sale",
                    -float(sale.get("qty") or 0),
                    reason="in_house_employee_sale",
                    reference_type="in_house_sale",
                    reference_id=int(sale["id"]),
                )
        return sale if sale and sale.get("id") else None
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "in_house_sales", None, {"error": str(exc)})
        raise


def complete_in_house_checkout(employee_name=None, employee_id=None, lines=None, payment_method="cash", notes=None, discount_amount=0, tax_amount=0, buyer_type=None, buyer_phone=None, buyer_email=None, approved_by="pos_auto"):
    lines = list(lines or [])
    if not lines:
        raise ValueError("at least one line is required")
    order = create_in_house_order(
        employee_name=employee_name,
        employee_id=employee_id,
        lines=lines,
        payment_method=payment_method,
        notes=notes,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        buyer_type=buyer_type,
        buyer_phone=buyer_phone,
        buyer_email=buyer_email,
    )
    if not order or not order.get("id"):
        raise ValueError("receipt could not be created")
    return approve_in_house_order(order["id"], approved_by=approved_by)


def create_employee_pos_token(employee_id=None, employee_name=None, device_label=None, expires_at=None):
    _require_company_postgres_runtime("employees")
    token = secrets.token_urlsafe(32)
    token_hash = _hash_pos_token(token)
    stored_token = f"sha256:{token_hash}"
    expires_at = expires_at or _default_pos_token_expires_at()
    try:
        with pg_domain_tx("employees", "employee_pos_tokens") as (_pg_conn, cur):
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.employee_pos_tokens ADD COLUMN IF NOT EXISTS token_hash TEXT")
            account = _pg_ensure_employee_account_txn(cur, employee_name=employee_name, employee_id=employee_id)
            now = utc_now()
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.employee_pos_tokens (
                    employee_id, token, token_hash, device_label, active, expires_at, created_at, last_used_at
                ) VALUES (%s, %s, %s, %s, 1, %s, %s, NULL)
                RETURNING *
                """,
                (int(account["id"]), stored_token, token_hash, (device_label or "").strip() or None, expires_at, now),
            )
            row = _pg_fetchone_dict(cur)
        if row:
            row["employee_name"] = account.get("name")
            row["token"] = token
            return _public_pos_token_row(row, reveal_token=True)
    except Exception as exc:
        log_cutover_event("employees", "postgres_primary_failed_closed", "employee_pos_tokens", employee_id or employee_name, {"error": str(exc)})
        raise


def get_employee_pos_token(token):
    _require_company_postgres_runtime("employees")
    token = str(token or "").strip()
    if not token:
        return None
    token_hash = _hash_pos_token(token)
    try:
        with pg_domain_tx("employees", "employee_pos_tokens_lookup") as (_pg_conn, cur):
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.employee_pos_tokens ADD COLUMN IF NOT EXISTS token_hash TEXT")
            cur.execute(
                f"""
                SELECT ept.*, ea.name AS employee_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.employee_pos_tokens ept
                JOIN {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ea ON ea.id = ept.employee_id
                WHERE ept.token_hash = %s OR ept.token = %s
                """,
                (token_hash, token),
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                return None
            if not int(row.get("active") or 0):
                return None
            expires_at = row.get("expires_at")
            if _iso_is_past(expires_at):
                return None
            now = utc_now()
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.employee_pos_tokens SET last_used_at = %s WHERE id = %s",
                (now, int(row["id"])),
            )
            row["last_used_at"] = now
        return row
    except Exception as exc:
        log_cutover_event("employees", "postgres_primary_failed_closed", "employee_pos_tokens_lookup", token, {"error": str(exc)})
        raise


def list_employee_pos_tokens(employee_id=None, employee_name=None, include_inactive=True, limit=200):
    _require_company_postgres_runtime("employees")
    limit = max(1, min(int(limit or 200), 500))
    try:
        with pg_domain_tx("employees", "employee_pos_tokens_list") as (_pg_conn, cur):
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.employee_pos_tokens ADD COLUMN IF NOT EXISTS token_hash TEXT")
            where = []
            params = []
            if employee_id:
                where.append("ept.employee_id = %s")
                params.append(int(employee_id))
            if employee_name:
                where.append("lower(ea.name) = lower(%s)")
                params.append(str(employee_name).strip())
            if not include_inactive:
                where.append("ept.active = 1")
            where_sql = " AND ".join(where) if where else "1=1"
            cur.execute(
                f"""
                SELECT ept.*, ea.name AS employee_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.employee_pos_tokens ept
                JOIN {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ea ON ea.id = ept.employee_id
                WHERE {where_sql}
                ORDER BY ept.created_at DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            return [_public_pos_token_row(row) for row in _pg_fetchall_dict(cur)]
    except Exception as exc:
        log_cutover_event("employees", "postgres_primary_failed_closed", "employee_pos_tokens_list", employee_id or employee_name, {"error": str(exc)})
        raise


def revoke_employee_pos_token(token_id, revoked_by=None):
    _require_company_postgres_runtime("employees")
    token_id = int(token_id or 0)
    if token_id <= 0:
        raise ValueError("token id required")
    try:
        with pg_domain_tx("employees", "employee_pos_tokens_revoke") as (_pg_conn, cur):
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.employee_pos_tokens
                SET active = 0
                WHERE id = %s
                RETURNING *
                """,
                (token_id,),
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                raise ValueError("POS token not found")
        return _public_pos_token_row(row)
    except ValueError:
        raise
    except Exception as exc:
        log_cutover_event("employees", "postgres_primary_failed_closed", "employee_pos_tokens_revoke", token_id, {"error": str(exc), "revoked_by": revoked_by})
        raise


def rotate_employee_pos_token(token_id, revoked_by=None, device_label=None, expires_at=None):
    token_id = int(token_id or 0)
    existing = None
    tokens = list_employee_pos_tokens(limit=500)
    for row in tokens:
        if int(row.get("id") or 0) == token_id:
            existing = row
            break
    if not existing:
        raise ValueError("POS token not found")
    revoke_employee_pos_token(token_id, revoked_by=revoked_by)
    return create_employee_pos_token(
        employee_id=existing.get("employee_id"),
        device_label=device_label or existing.get("device_label"),
        expires_at=expires_at,
    )


def list_internal_pos_products(q=None, code=None, limit=80):
    _require_company_postgres_runtime("inventory_products")
    try:
        query = f"""
            SELECT
                p.id,
                p.name,
                p.sku,
                p.barcode,
                p.cost_price,
                p.retail_price,
                p.on_hand_qty,
                p.low_stock_threshold,
                p.media_url,
                p.storage_bin,
                pc.name AS category_name
            FROM {POSTGRES_SIDECAR_SCHEMA}.products p
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
            WHERE COALESCE(p.active, 1) = 1
        """
        params = []
        if code:
            query += " AND (LOWER(COALESCE(p.barcode, '')) = %s OR LOWER(COALESCE(p.sku, '')) = %s)"
            code_norm = str(code or "").strip().lower()
            params.extend([code_norm, code_norm])
        elif q:
            ql = f"%{str(q).strip().lower()}%"
            query += """
                AND (
                    LOWER(COALESCE(p.name, '')) LIKE %s
                    OR LOWER(COALESCE(p.barcode, '')) LIKE %s
                    OR LOWER(COALESCE(p.sku, '')) LIKE %s
                    OR LOWER(COALESCE(pc.name, '')) LIKE %s
                )
            """
            params.extend([ql, ql, ql, ql])
        query += " ORDER BY LOWER(COALESCE(p.name, '')) ASC LIMIT %s"
        params.append(int(limit or 80))
        with _pg_connect() as pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return _pg_fetchall_dict(cur)
    except Exception as exc:
        log_cutover_event("inventory_products", "postgres_primary_failed_closed", "list_internal_pos_products", code or q or "all", {"error": str(exc)})
        raise


def _recalc_in_house_order_totals_txn(conn, order_id):
    totals = _fetchone_dict(
        conn,
        """
        SELECT
            COALESCE(SUM(line_total), 0) AS subtotal
        FROM in_house_order_lines
        WHERE order_id = ?
        """,
        (int(order_id),),
    ) or {}
    order = _fetchone_dict(conn, "SELECT discount_amount, tax_amount FROM in_house_orders WHERE id = ?", (int(order_id),)) or {}
    subtotal = round(float(totals.get("subtotal") or 0), 2)
    discount_amount = round(float(order.get("discount_amount") or 0), 2)
    tax_amount = round(float(order.get("tax_amount") or 0), 2)
    total_amount = round(max(subtotal - discount_amount, 0) + tax_amount, 2)
    conn.execute(
        """
        UPDATE in_house_orders
        SET subtotal = ?, total_amount = ?, updated_at = ?
        WHERE id = ?
        """,
        (subtotal, total_amount, utc_now(), int(order_id)),
    )


def _pg_recalc_in_house_order_totals_txn(cur, order_id):
    cur.execute(
        f"""
        SELECT COALESCE(SUM(line_total), 0) AS subtotal
        FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines
        WHERE order_id = %s
        """,
        (int(order_id),),
    )
    totals = _pg_fetchone_dict(cur) or {}
    cur.execute(
        f"""
        SELECT discount_amount, tax_amount
        FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders
        WHERE id = %s
        """,
        (int(order_id),),
    )
    order = _pg_fetchone_dict(cur) or {}
    subtotal = round(float(totals.get("subtotal") or 0), 2)
    discount_amount = round(float(order.get("discount_amount") or 0), 2)
    tax_amount = round(float(order.get("tax_amount") or 0), 2)
    total_amount = round(max(subtotal - discount_amount, 0) + tax_amount, 2)
    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders
        SET subtotal = %s, total_amount = %s, updated_at = %s
        WHERE id = %s
        """,
        (subtotal, total_amount, utc_now(), int(order_id)),
    )


def create_in_house_order(token=None, employee_id=None, employee_name=None, lines=None, payment_method="payroll", notes=None, discount_amount=0, tax_amount=0, buyer_type=None, buyer_phone=None, buyer_email=None, invoice_parent_id=None, status="pending_approval"):
    _require_company_postgres_runtime("in_house")
    if not isinstance(lines, list) or not lines:
        raise ValueError("at least one line is required")
    try:
        resolved_employee_id = employee_id
        resolved_employee_name = employee_name
        if token:
            token_row = get_employee_pos_token(token)
            if not token_row:
                raise ValueError("invalid employee POS token")
            resolved_employee_id = token_row.get("employee_id")
            resolved_employee_name = token_row.get("employee_name")
        with pg_domain_tx("in_house", "in_house_orders") as (_pg_conn, cur):
            account = _pg_ensure_employee_account_txn(cur, employee_name=resolved_employee_name, employee_id=resolved_employee_id)
            should_auto_approve = bool(account.get("auto_approve_in_house_orders"))
            now = utc_now()
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders ADD COLUMN IF NOT EXISTS buyer_type TEXT")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders ADD COLUMN IF NOT EXISTS buyer_phone TEXT")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders ADD COLUMN IF NOT EXISTS buyer_email TEXT")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders ADD COLUMN IF NOT EXISTS tax_amount DOUBLE PRECISION NOT NULL DEFAULT 0")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders ADD COLUMN IF NOT EXISTS invoice_parent_id BIGINT")
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.in_house_orders (
                    employee_id, status, payment_method, notes, submitted_at,
                    discount_amount, tax_amount, buyer_type, buyer_phone, buyer_email, invoice_parent_id, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    int(account["id"]),
                    (status or "pending_approval").strip() or "pending_approval",
                    (payment_method or "payroll").strip() or "payroll",
                    notes or None,
                    now,
                    float(discount_amount or 0),
                    float(tax_amount or 0),
                    (buyer_type or "").strip() or None,
                    (buyer_phone or "").strip() or None,
                    (buyer_email or "").strip() or None,
                    int(invoice_parent_id) if invoice_parent_id else None,
                    now,
                    now,
                ),
            )
            order_row = _pg_fetchone_dict(cur)
            order_id = int(order_row["id"])
            created_line_ids = []
            for line in lines:
                product = None
                if line.get("product_id"):
                    product = get_product(int(line.get("product_id")))
                if not product and (line.get("barcode") or line.get("sku")):
                    product = find_product_by_code(line.get("barcode") or line.get("sku"))
                if not product:
                    raise ValueError("product not found for one of the lines")
                qty = float(line.get("qty") or 0)
                if qty <= 0:
                    raise ValueError("qty must be greater than 0")
                unit_cost = float(product.get("cost_price") or 0)
                unit_price = unit_cost if line.get("unit_price") in (None, "") else float(line.get("unit_price") or 0)
                line_total = round(qty * unit_price, 2)
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines (
                        order_id, product_id, description, barcode, sku,
                        qty, unit_cost, unit_price, line_total, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        order_id,
                        int(product["id"]),
                        product.get("name"),
                        product.get("barcode"),
                        product.get("sku"),
                        qty,
                        unit_cost,
                        unit_price,
                        line_total,
                        now,
                        now,
                    ),
                )
                created_line = _pg_fetchone_dict(cur)
                if created_line and created_line.get("id"):
                    created_line_ids.append(int(created_line["id"]))
            cur.execute(
                f"""
                SELECT COALESCE(SUM(line_total), 0) AS subtotal
                FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines
                WHERE order_id = %s
                """,
                (order_id,),
            )
            subtotal = float((_pg_fetchone_dict(cur) or {}).get("subtotal") or 0)
            total_amount = round(max(subtotal - float(discount_amount or 0), 0) + float(tax_amount or 0), 2)
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders
                SET subtotal = %s, total_amount = %s, updated_at = %s
                WHERE id = %s
                """,
                (round(subtotal, 2), total_amount, utc_now(), order_id),
            )
        order = get_in_house_order(order_id)
        if should_auto_approve and str(order.get("status") or "") in {"pending_approval", "draft", "rejected"}:
            return approve_in_house_order(order_id, approved_by="trusted_employee_policy")
        return order
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "in_house_orders", employee_id or employee_name, {"error": str(exc)})
        raise


def list_in_house_orders(status=None, employee_id=None, buyer_name=None, token=None, limit=200):
    _require_company_postgres_runtime("in_house")
    token_row = None
    if token:
        token_row = get_employee_pos_token(token)
        if not token_row:
            raise ValueError("invalid employee POS token")
        employee_id = token_row.get("employee_id")
    try:
        query = f"""
            SELECT
                iho.*,
                ea.name AS employee_name,
                COALESCE(COUNT(ihol.id), 0) AS line_count,
                COALESCE(SUM(ihol.qty), 0) AS units_requested
            FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders iho
            JOIN {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ea ON ea.id = iho.employee_id
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines ihol ON ihol.order_id = iho.id
            WHERE 1=1
        """
        params = []
        if status:
            if isinstance(status, (list, tuple, set)):
                values = [str(v).strip() for v in status if str(v).strip()]
                if values:
                    query += f" AND iho.status IN ({','.join('%s' for _ in values)})"
                    params.extend(values)
            else:
                query += " AND iho.status = %s"
                params.append(str(status).strip())
        if employee_id not in (None, ""):
            query += " AND iho.employee_id = %s"
            params.append(int(employee_id))
        if buyer_name:
            query += " AND lower(ea.name) = lower(%s)"
            params.append(str(buyer_name).strip())
        query += """
            GROUP BY iho.id, ea.name
            ORDER BY COALESCE(iho.submitted_at, iho.created_at) DESC, iho.id DESC
            LIMIT %s
        """
        params.append(int(limit or 200))
        with _pg_connect() as pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return _pg_fetchall_dict(cur)
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "list_in_house_orders", employee_id or buyer_name or "all", {"error": str(exc)})
        raise


def _pg_get_in_house_order(order_id):
    with pg_domain_tx("in_house", "get_in_house_order") as (_pg_conn, cur):
        cur.execute(
            f"""
            SELECT iho.*, ea.name AS employee_name
            FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders iho
            JOIN {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ea ON ea.id = iho.employee_id
            WHERE iho.id = %s
            """,
            (int(order_id),),
        )
        order = _pg_fetchone_dict(cur)
        if not order:
            return None
        cur.execute(
            f"""
            SELECT
                ihol.*,
                p.on_hand_qty,
                p.low_stock_threshold,
                p.media_url,
                p.storage_bin
            FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines ihol
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = ihol.product_id
            WHERE ihol.order_id = %s
            ORDER BY ihol.id ASC
            """,
            (int(order_id),),
        )
        lines = _pg_fetchall_dict(cur)
        order["lines"] = lines
        order["line_count"] = len(lines)
        order["units_requested"] = round(sum(float(line.get("qty") or 0) for line in lines), 2)
        return order


def get_in_house_order(order_id):
    _require_company_postgres_runtime("in_house")
    try:
        return _pg_get_in_house_order(order_id)
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "get_in_house_order", order_id, {"error": str(exc)})
        raise


def _match_pg_in_house_sales_for_order(cur, order, lines):
    order_id = int(order["id"])
    cur.execute(
        f"""
        SELECT *
        FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_sales
        WHERE order_id = %s
           OR (
                employee_id = %s
            AND notes LIKE %s
           )
        ORDER BY id ASC
        """,
        (order_id, int(order.get("employee_id") or 0), f"%#{order_id}%"),
    )
    sale_rows = _pg_fetchall_dict(cur)
    grouped = {}
    for sale in sale_rows:
        key = str(sale.get("order_line_id") or "")
        grouped.setdefault(key, []).append(sale)
    used_ids = set()
    matched = {}
    for line in lines:
        direct = None
        for sale in grouped.get(str(line["id"]), []):
            if int(sale["id"]) not in used_ids:
                direct = sale
                break
        if direct:
            matched[int(line["id"])] = direct
            used_ids.add(int(direct["id"]))
            continue
        for sale in sale_rows:
            if int(sale["id"]) in used_ids:
                continue
            if int(sale.get("product_id") or 0) != int(line.get("product_id") or 0):
                continue
            matched[int(line["id"])] = sale
            used_ids.add(int(sale["id"]))
            break
    return matched


def update_in_house_order(order_id, employee_name=None, payment_method=None, notes=None, discount_amount=None, tax_amount=None, buyer_type=None, buyer_phone=None, buyer_email=None, lines=None):
    _require_company_postgres_runtime("in_house")
    order_id = int(order_id or 0)
    if order_id <= 0:
        raise ValueError("order id required")
    if not isinstance(lines, list) or not lines:
        raise ValueError("at least one line is required")
    try:
        with pg_domain_tx("in_house", "update_in_house_order") as (_pg_conn, cur):
                cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders WHERE id = %s", (order_id,))
                order = _pg_fetchone_dict(cur)
                if not order:
                    raise ValueError("order not found")
                status = str(order.get("status") or "")
                if status in {"cancelled"}:
                    raise ValueError("cancelled orders cannot be edited")
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines WHERE order_id = %s ORDER BY id ASC",
                    (order_id,),
                )
                existing_lines = _pg_fetchall_dict(cur)
                existing_map = {int(line["id"]): line for line in existing_lines}
                payload_ids = {int(line.get("id") or 0) for line in lines}
                if status == "approved" and payload_ids != set(existing_map):
                    raise ValueError("approved invoices can only edit existing lines right now")
                sale_map = _match_pg_in_house_sales_for_order(cur, order, existing_lines) if status == "approved" else {}
                account = _pg_ensure_employee_account_txn(cur, employee_name=employee_name or order.get("employee_name"), employee_id=order.get("employee_id"))
                now = utc_now()
                removed_ids = sorted(set(existing_map) - payload_ids)
                added_lines = [line for line in lines if int(line.get("id") or 0) <= 0]
                for removed_id in removed_ids:
                    current = existing_map[removed_id]
                    if status == "approved":
                        sale = sale_map.get(removed_id)
                        if not sale:
                            raise ValueError("approved invoice is missing a linked sale row")
                        _pg_record_inventory_movement_txn(
                            cur,
                            int(current["product_id"]),
                            "adjustment",
                            float(sale.get("qty") or 0),
                            reason="in_house_invoice_remove_line",
                            reference_type="in_house_sale",
                            reference_id=int(sale["id"]),
                        )
                        cur.execute(
                            f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_sales WHERE id = %s",
                            (int(sale["id"]),),
                        )
                    cur.execute(
                        f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines WHERE id = %s",
                        (removed_id,),
                    )
                for line in lines:
                    line_id = int(line.get("id") or 0)
                    current = existing_map.get(line_id)
                    if not current:
                        continue
                    if int(current.get("product_id") or 0) != int(line.get("product_id") or current.get("product_id") or 0):
                        raise ValueError("approved invoice lines cannot change product")
                    qty = float(line.get("qty") or 0)
                    if qty <= 0:
                        raise ValueError("qty must be greater than 0")
                    unit_price = float(line.get("unit_price") or 0)
                    unit_cost = float(current.get("unit_cost") or 0)
                    line_total = round(qty * unit_price, 2)
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines
                        SET qty = %s, unit_price = %s, line_total = %s, updated_at = %s
                        WHERE id = %s
                        """,
                        (qty, unit_price, line_total, now, line_id),
                    )
                    if status == "approved":
                        sale = sale_map.get(line_id)
                        if not sale:
                            raise ValueError("approved invoice is missing a linked sale row")
                        old_qty = float(current.get("qty") or 0)
                        qty_delta = round(old_qty - qty, 4)
                        if abs(qty_delta) > 0:
                            _pg_record_inventory_movement_txn(
                                cur,
                                int(current["product_id"]),
                                "adjustment",
                                qty_delta,
                                reason="in_house_invoice_edit",
                                reference_type="in_house_sale",
                                reference_id=int(sale["id"]),
                            )
                        subtotal = round(qty * unit_price, 2)
                        total_cost = round(qty * unit_cost, 2)
                        profit = round(subtotal - total_cost, 2)
                        cur.execute(
                            f"""
                            UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_sales
                            SET employee_id = %s,
                                employee_name = %s,
                                qty = %s,
                                unit_price = %s,
                                subtotal = %s,
                                total_cost = %s,
                                profit = %s,
                                order_id = %s,
                                order_line_id = %s,
                                updated_at = %s
                            WHERE id = %s
                            """,
                            (int(account["id"]), account["name"], qty, unit_price, subtotal, total_cost, profit, order_id, line_id, now, int(sale["id"])),
                        )
                for line in added_lines:
                    product = _pg_get_product_txn(cur, product_id=line.get("product_id"), barcode=line.get("barcode"), sku=line.get("sku"))
                    if not product:
                        raise ValueError("product not found for one of the new lines")
                    qty = float(line.get("qty") or 0)
                    if qty <= 0:
                        raise ValueError("qty must be greater than 0")
                    unit_cost = float(product.get("cost_price") or 0)
                    unit_price = float(line.get("unit_price") or product.get("retail_price") or product.get("list_price") or unit_cost)
                    line_total = round(qty * unit_price, 2)
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines (
                            order_id, product_id, description, barcode, sku,
                            qty, unit_cost, unit_price, line_total, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            order_id,
                            int(product["id"]),
                            product.get("name"),
                            product.get("barcode"),
                            product.get("sku"),
                            qty,
                            unit_cost,
                            unit_price,
                            line_total,
                            now,
                            now,
                        ),
                    )
                    created = _pg_fetchone_dict(cur)
                    if status == "approved":
                        sale = _pg_create_in_house_sale_txn(
                            cur,
                            employee_id=account.get("id"),
                            product_id=product.get("id"),
                            qty=qty,
                            unit_price=unit_price,
                            notes=f"Invoice #{order_id} line added" if not order.get("notes") else f"{order.get('notes')} | Invoice #{order_id} line added",
                            sold_at=utc_now(),
                            order_id=order_id,
                            order_line_id=created.get("id"),
                        )
                        _pg_record_inventory_movement_txn(
                            cur,
                            int(sale["product_id"]),
                            "sale",
                            -float(sale.get("qty") or 0),
                            reason="in_house_employee_sale",
                            reference_type="in_house_sale",
                            reference_id=int(sale["id"]),
                        )
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders
                    SET employee_id = %s,
                        payment_method = %s,
                        notes = %s,
                        discount_amount = %s,
                        tax_amount = %s,
                        buyer_type = %s,
                        buyer_phone = %s,
                        buyer_email = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        int(account["id"]),
                        (payment_method or order.get("payment_method") or "cash").strip() or "cash",
                        notes if notes is not None else order.get("notes"),
                        float(discount_amount if discount_amount is not None else order.get("discount_amount") or 0),
                        float(tax_amount if tax_amount is not None else order.get("tax_amount") or 0),
                        (buyer_type if buyer_type is not None else order.get("buyer_type") or "").strip() or None,
                        (buyer_phone if buyer_phone is not None else order.get("buyer_phone") or "").strip() or None,
                        (buyer_email if buyer_email is not None else order.get("buyer_email") or "").strip() or None,
                        now,
                        order_id,
                    ),
                )
                _pg_recalc_in_house_order_totals_txn(cur, order_id)
        return get_in_house_order(order_id)
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "update_in_house_order", order_id, {"error": str(exc)})
        raise


def split_in_house_order(order_id, line_ids=None, approved_by=None, line_items=None):
    _require_company_postgres_runtime("in_house")
    order_id = int(order_id or 0)
    selected_ids = sorted({int(line_id) for line_id in (line_ids or []) if int(line_id or 0) > 0})
    requested_items = []
    if isinstance(line_items, list) and line_items:
        for item in line_items:
            line_id = int((item or {}).get("id") or 0)
            qty = float((item or {}).get("qty") or 0)
            if line_id > 0 and qty > 0:
                requested_items.append({"id": line_id, "qty": qty})
        if requested_items:
            selected_ids = sorted({item["id"] for item in requested_items})
    if order_id <= 0:
        raise ValueError("order id required")
    if not selected_ids:
        raise ValueError("at least one line is required to split")
    try:
        with pg_domain_tx("in_house", "split_in_house_order") as (_pg_conn, cur):
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders WHERE id = %s",
                    (order_id,),
                )
                order = _pg_fetchone_dict(cur)
                if not order:
                    raise ValueError("order not found")
                if str(order.get("status") or "") == "cancelled":
                    raise ValueError("cancelled invoices cannot be split")
                cur.execute(
                    f"""
                    SELECT *
                    FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines
                    WHERE order_id = %s
                    ORDER BY id ASC
                    """,
                    (order_id,),
                )
                lines = _pg_fetchall_dict(cur)
                line_map = {int(line["id"]): line for line in lines}
                selected_lines = [line_map[line_id] for line_id in selected_ids if line_id in line_map]
                if len(selected_lines) != len(selected_ids):
                    raise ValueError("one or more selected lines are missing")
                if not requested_items:
                    requested_items = [{"id": int(line["id"]), "qty": float(line.get("qty") or 0)} for line in selected_lines]
                request_map = {int(item["id"]): float(item["qty"]) for item in requested_items}
                full_move = len(selected_lines) == len(lines) and all(
                    round(float(line.get("qty") or 0) - request_map.get(int(line["id"]), 0), 4) == 0
                    for line in selected_lines
                )
                if full_move:
                    raise ValueError("cannot split every line into a new invoice")
                now = utc_now()
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.in_house_orders (
                        employee_id, status, payment_method, notes, submitted_at, approved_at, approved_by,
                        subtotal, discount_amount, tax_amount, total_amount, buyer_type, buyer_phone, buyer_email,
                        invoice_parent_id, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        int(order["employee_id"]),
                        str(order.get("status") or "pending_approval"),
                        order.get("payment_method") or "cash",
                        f"Split from invoice #{order_id}" if not order.get("notes") else f"{order.get('notes')} | Split from invoice #{order_id}",
                        order.get("submitted_at") or now,
                        order.get("approved_at"),
                        approved_by or order.get("approved_by"),
                        order.get("buyer_type"),
                        order.get("buyer_phone"),
                        order.get("buyer_email"),
                        order_id,
                        now,
                        now,
                    ),
                )
                new_order_row = _pg_fetchone_dict(cur) or {}
                new_order_id = int(new_order_row["id"])
                sale_map = _match_pg_in_house_sales_for_order(cur, order, selected_lines) if str(order.get("status") or "") == "approved" else {}
                created_sales = []
                updated_sales = []
                for selected in selected_lines:
                    line_id = int(selected["id"])
                    move_qty = float(request_map.get(line_id) or 0)
                    current_qty = float(selected.get("qty") or 0)
                    if move_qty <= 0 or move_qty > current_qty:
                        raise ValueError("split qty must be greater than 0 and no more than the line qty")
                    remaining_qty = round(current_qty - move_qty, 4)
                    if remaining_qty == 0:
                        cur.execute(
                            f"""
                            UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines
                            SET order_id = %s, updated_at = %s
                            WHERE id = %s
                            """,
                            (new_order_id, now, line_id),
                        )
                        if str(order.get("status") or "") == "approved":
                            sale = sale_map.get(line_id)
                            if sale:
                                cur.execute(
                                    f"""
                                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_sales
                                    SET order_id = %s, updated_at = %s
                                    WHERE id = %s
                                    """,
                                    (new_order_id, now, int(sale["id"])),
                                )
                                updated_sales.append(int(sale["id"]))
                        continue
                    unit_price = float(selected.get("unit_price") or 0)
                    unit_cost = float(selected.get("unit_cost") or 0)
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines
                        SET qty = %s, line_total = %s, updated_at = %s
                        WHERE id = %s
                        """,
                        (remaining_qty, round(remaining_qty * unit_price, 2), now, line_id),
                    )
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines (
                            order_id, product_id, description, barcode, sku,
                            qty, unit_cost, unit_price, line_total, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            new_order_id,
                            int(selected["product_id"]),
                            selected.get("description"),
                            selected.get("barcode"),
                            selected.get("sku"),
                            move_qty,
                            unit_cost,
                            unit_price,
                            round(move_qty * unit_price, 2),
                            now,
                            now,
                        ),
                    )
                    new_line = _pg_fetchone_dict(cur) or {}
                    if str(order.get("status") or "") == "approved":
                        sale = sale_map.get(line_id)
                        if sale:
                            remaining_subtotal = round(remaining_qty * unit_price, 2)
                            remaining_total_cost = round(remaining_qty * unit_cost, 2)
                            remaining_profit = round(remaining_subtotal - remaining_total_cost, 2)
                            cur.execute(
                                f"""
                                UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_sales
                                SET qty = %s, subtotal = %s, total_cost = %s, profit = %s, updated_at = %s
                                WHERE id = %s
                                """,
                                (remaining_qty, remaining_subtotal, remaining_total_cost, remaining_profit, now, int(sale["id"])),
                            )
                            updated_sales.append(int(sale["id"]))
                            new_sale = _pg_create_in_house_sale_txn(
                                cur,
                                employee_id=order.get("employee_id"),
                                product_id=selected.get("product_id"),
                                qty=move_qty,
                                unit_price=unit_price,
                                notes=f"Split from invoice #{order_id}" if not order.get("notes") else f"{order.get('notes')} | Split from invoice #{order_id}",
                                sold_at=order.get("submitted_at") or now,
                                order_id=new_order_id,
                                order_line_id=new_line.get("id"),
                            )
                            created_sales.append(new_sale)
                _pg_recalc_in_house_order_totals_txn(cur, order_id)
                _pg_recalc_in_house_order_totals_txn(cur, new_order_id)
        return {"source_order": get_in_house_order(order_id), "split_order": get_in_house_order(new_order_id)}
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "split_in_house_order", order_id, {"error": str(exc)})
        raise


def list_in_house_buyer_profiles(q=None, limit=200):
    _require_company_postgres_runtime("in_house")
    limit = max(1, min(int(limit or 200), 500))
    try:
        query = f"""
            SELECT
                iho.employee_id,
                COALESCE(MAX(NULLIF(TRIM(iho.buyer_type), '')), 'walk_in') AS buyer_type,
                COALESCE(MAX(NULLIF(TRIM(iho.buyer_phone), '')), '') AS buyer_phone,
                COALESCE(MAX(NULLIF(TRIM(iho.buyer_email), '')), '') AS buyer_email,
                MAX(COALESCE(iho.submitted_at, iho.created_at)) AS last_order_at,
                COUNT(*) AS order_count,
                COALESCE(SUM(iho.total_amount), 0) AS total_spend,
                ea.name AS buyer_name
            FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders iho
            JOIN {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ea ON ea.id = iho.employee_id
            WHERE COALESCE(TRIM(ea.name), '') <> ''
        """
        params = []
        if q:
            query += """
                AND (
                    LOWER(COALESCE(ea.name, '')) LIKE %s
                    OR LOWER(COALESCE(iho.buyer_phone, '')) LIKE %s
                    OR LOWER(COALESCE(iho.buyer_email, '')) LIKE %s
                )
            """
            term = f"%{str(q).strip().lower()}%"
            params.extend([term, term, term])
        query += """
            GROUP BY iho.employee_id, ea.name
            ORDER BY MAX(COALESCE(iho.submitted_at, iho.created_at)) DESC, ea.name ASC
            LIMIT %s
        """
        params.append(limit)
        with _pg_connect() as pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return _pg_fetchall_dict(cur)
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "list_in_house_buyer_profiles", q or "all", {"error": str(exc)})
        raise


def merge_in_house_orders(source_order_id, target_order_id):
    _require_company_postgres_runtime("in_house")
    source_order_id = int(source_order_id or 0)
    target_order_id = int(target_order_id or 0)
    if source_order_id <= 0 or target_order_id <= 0:
        raise ValueError("source and target invoice ids are required")
    if source_order_id == target_order_id:
        raise ValueError("source and target invoice must be different")
    try:
        with pg_domain_tx("in_house", "merge_in_house_orders") as (_pg_conn, cur):
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders WHERE id = %s",
                    (source_order_id,),
                )
                source = _pg_fetchone_dict(cur)
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders WHERE id = %s",
                    (target_order_id,),
                )
                target = _pg_fetchone_dict(cur)
                if not source or not target:
                    raise ValueError("invoice not found")
                source_status = str(source.get("status") or "")
                target_status = str(target.get("status") or "")
                if source_status == "cancelled" or target_status == "cancelled":
                    raise ValueError("cancelled invoices cannot be merged")
                if source_status != target_status:
                    raise ValueError("only invoices with the same status can be merged")
                now = utc_now()
                cur.execute(
                    f"""
                    SELECT *
                    FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines
                    WHERE order_id = %s
                    ORDER BY id ASC
                    """,
                    (source_order_id,),
                )
                source_lines = _pg_fetchall_dict(cur)
                if not source_lines:
                    raise ValueError("source invoice has no lines")
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines
                    SET order_id = %s, updated_at = %s
                    WHERE order_id = %s
                    """,
                    (target_order_id, now, source_order_id),
                )
                if source_status == "approved":
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_sales
                        SET order_id = %s, updated_at = %s
                        WHERE order_id = %s
                        """,
                        (target_order_id, now, source_order_id),
                    )
                _pg_recalc_in_house_order_totals_txn(cur, target_order_id)
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders
                    SET status = 'merged',
                        subtotal = 0,
                        total_amount = 0,
                        invoice_parent_id = %s,
                        notes = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        target_order_id,
                        f"Merged into invoice #{target_order_id}" if not source.get("notes") else f"{source.get('notes')} | Merged into invoice #{target_order_id}",
                        now,
                        source_order_id,
                    ),
                )
        return {"source_order": get_in_house_order(source_order_id), "target_order": get_in_house_order(target_order_id)}
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "merge_in_house_orders", f"{source_order_id}:{target_order_id}", {"error": str(exc)})
        raise


def in_house_orders_summary():
    _require_company_postgres_runtime("in_house")
    try:
        with _pg_connect() as pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        COUNT(*) AS order_count,
                        COALESCE(SUM(CASE WHEN status = 'pending_approval' THEN 1 ELSE 0 END), 0) AS pending_count,
                        COALESCE(SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END), 0) AS approved_count,
                        COALESCE(SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected_count,
                        COALESCE(SUM(CASE WHEN status = 'pending_approval' THEN total_amount ELSE 0 END), 0) AS pending_value,
                        COALESCE(SUM(CASE WHEN status = 'approved' THEN total_amount ELSE 0 END), 0) AS approved_value
                    FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders
                    """
                )
                summary = _pg_fetchone_dict(cur) or {}
        return {
            "order_count": int(summary.get("order_count") or 0),
            "pending_count": int(summary.get("pending_count") or 0),
            "approved_count": int(summary.get("approved_count") or 0),
            "rejected_count": int(summary.get("rejected_count") or 0),
            "pending_value": round(float(summary.get("pending_value") or 0), 2),
            "approved_value": round(float(summary.get("approved_value") or 0), 2),
        }
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "in_house_orders_summary", "all", {"error": str(exc)})
        raise


def approve_in_house_order(order_id, approved_by=None):
    _require_company_postgres_runtime("in_house")
    try:
        with pg_domain_tx("in_house", "approve_in_house_order") as (_pg_conn, cur):
                cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders WHERE id = %s", (int(order_id),))
                order = _pg_fetchone_dict(cur)
                if not order:
                    raise ValueError("order not found")
                if str(order.get("status") or "") == "approved":
                    pass
                elif str(order.get("status") or "") not in {"pending_approval", "rejected", "draft"}:
                    raise ValueError("order cannot be approved in its current state")
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_order_lines WHERE order_id = %s ORDER BY id ASC",
                    (int(order_id),),
                )
                line_rows = [dict(zip((desc[0] for desc in cur.description), row)) for row in cur.fetchall()]
                if not line_rows:
                    raise ValueError("order has no lines")
                created_sales = []
                if str(order.get("status") or "") != "approved":
                    for line in line_rows:
                        sale = _pg_create_in_house_sale_txn(
                            cur,
                            employee_id=order.get("employee_id"),
                            product_id=line.get("product_id"),
                            qty=line.get("qty") or 0,
                            unit_price=line.get("unit_price"),
                            notes=f"Approved from internal POS order #{order_id}" if not order.get("notes") else f"{order.get('notes')} | Approved from internal POS order #{order_id}",
                            sold_at=utc_now(),
                            order_id=order_id,
                            order_line_id=line.get("id"),
                        )
                        _pg_record_inventory_movement_txn(
                            cur,
                            int(sale["product_id"]),
                            "sale",
                            -float(sale.get("qty") or 0),
                            reason="in_house_employee_sale",
                            reference_type="in_house_sale",
                            reference_id=int(sale["id"]),
                        )
                        created_sales.append(sale)
                    now = utc_now()
                    cur.execute(
                        f"""
                        UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders
                        SET status = 'approved',
                            approved_at = %s,
                            approved_by = %s,
                            rejected_at = NULL,
                            rejected_by = NULL,
                            rejection_reason = NULL,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (now, (approved_by or "").strip() or None, now, int(order_id)),
                    )
        return get_in_house_order(order_id)
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "approve_in_house_order", order_id, {"error": str(exc)})
        raise


def reject_in_house_order(order_id, rejected_by=None, rejection_reason=None):
    _require_company_postgres_runtime("in_house")
    try:
        with pg_domain_tx("in_house", "reject_in_house_order") as (_pg_conn, cur):
                cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders WHERE id = %s", (int(order_id),))
                order = _pg_fetchone_dict(cur)
                if not order:
                    raise ValueError("order not found")
                if str(order.get("status") or "") == "approved":
                    raise ValueError("approved orders cannot be rejected")
                now = utc_now()
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders
                    SET status = 'rejected',
                        rejected_at = %s,
                        rejected_by = %s,
                        rejection_reason = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (now, (rejected_by or "").strip() or None, (rejection_reason or "").strip() or None, now, int(order_id)),
                )
        return get_in_house_order(order_id)
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "reject_in_house_order", order_id, {"error": str(exc)})
        raise


def cancel_in_house_order(order_id):
    _require_company_postgres_runtime("in_house")
    try:
        with pg_domain_tx("in_house", "cancel_in_house_order") as (_pg_conn, cur):
                cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_orders WHERE id = %s", (int(order_id),))
                order = _pg_fetchone_dict(cur)
                if not order:
                    raise ValueError("order not found")
                if str(order.get("status") or "") == "approved":
                    raise ValueError("approved orders cannot be cancelled from the draft queue")
                now = utc_now()
                cur.execute(
                    f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.in_house_orders SET status = 'cancelled', updated_at = %s WHERE id = %s",
                    (now, int(order_id)),
                )
        return get_in_house_order(order_id)
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "cancel_in_house_order", order_id, {"error": str(exc)})
        raise


def list_in_house_sales(q=None, limit=500):
    _require_company_postgres_runtime("in_house")
    try:
        query = f"""
            SELECT ihs.*, ea.name AS employee_account_name, p.on_hand_qty, pc.name AS category_name
            FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_sales ihs
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ea ON ea.id = ihs.employee_id
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = ihs.product_id
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
            WHERE 1=1
        """
        params = []
        if q:
            ql = f"%{str(q).lower()}%"
            query += """
                AND (
                    LOWER(COALESCE(ihs.employee_name, '')) LIKE %s
                    OR LOWER(COALESCE(ihs.product_name, '')) LIKE %s
                    OR LOWER(COALESCE(ihs.barcode, '')) LIKE %s
                    OR LOWER(COALESCE(ihs.sku, '')) LIKE %s
                )
            """
            params.extend([ql, ql, ql, ql])
        query += " ORDER BY ihs.sold_at DESC, ihs.id DESC LIMIT %s"
        params.append(int(limit or 500))
        with _pg_connect() as pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return _pg_fetchall_dict(cur)
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "list_in_house_sales", q or "all", {"error": str(exc)})
        raise


def in_house_sales_summary():
    _require_company_postgres_runtime("in_house")
    try:
        with _pg_connect() as pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        COUNT(*) AS sale_count,
                        COUNT(DISTINCT COALESCE(employee_id, 0) || '|' || LOWER(COALESCE(employee_name, ''))) AS employee_count,
                        COALESCE(SUM(qty), 0) AS units_sold,
                        COALESCE(SUM(subtotal), 0) AS revenue,
                        COALESCE(SUM(total_cost), 0) AS cost,
                        COALESCE(SUM(profit), 0) AS profit
                    FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_sales
                    """
                )
                summary = _pg_fetchone_dict(cur) or {}
                cur.execute(
                    f"""
                    SELECT
                        COALESCE(ihs.employee_id, 0) AS employee_id,
                        COALESCE(ea.name, ihs.employee_name) AS employee_name,
                        COUNT(*) AS sale_count,
                        COALESCE(SUM(ihs.qty), 0) AS units_sold,
                        COALESCE(SUM(ihs.subtotal), 0) AS revenue,
                        COALESCE(SUM(ihs.total_cost), 0) AS cost,
                        COALESCE(SUM(ihs.profit), 0) AS profit,
                        MAX(ihs.sold_at) AS last_sold_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_sales ihs
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ea ON ea.id = ihs.employee_id
                    GROUP BY COALESCE(ihs.employee_id, 0), COALESCE(ea.name, ihs.employee_name)
                    ORDER BY revenue DESC, units_sold DESC, employee_name ASC
                    LIMIT 25
                    """
                )
                by_employee = _pg_fetchall_dict(cur)
                cur.execute(
                    f"""
                    SELECT *
                    FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_sales
                    ORDER BY sold_at DESC, id DESC
                    LIMIT 10
                    """
                )
                recent = _pg_fetchall_dict(cur)
        return {
            "summary": {
                "sale_count": int(summary.get("sale_count") or 0),
                "employee_count": int(summary.get("employee_count") or 0),
                "units_sold": float(summary.get("units_sold") or 0),
                "revenue": round(float(summary.get("revenue") or 0), 2),
                "cost": round(float(summary.get("cost") or 0), 2),
                "profit": round(float(summary.get("profit") or 0), 2),
            },
            "by_employee": by_employee,
            "recent": recent,
        }
    except Exception as exc:
        log_cutover_event("in_house", "postgres_primary_failed_closed", "in_house_sales_summary", "all", {"error": str(exc)})
        raise


def list_employee_accounts(q=None, limit=200):
    _require_company_postgres_runtime("employees")
    try:
        query = f"""
            SELECT
                ea.id,
                ea.name,
                ea.name_key,
                ea.active,
                ea.auto_approve_in_house_orders,
                ea.allow_self_service_returns,
                ea.last_sale_at,
                COALESCE(COUNT(ihs.id), 0) AS sale_count,
                COALESCE(SUM(ihs.qty), 0) AS units_sold,
                COALESCE(SUM(ihs.subtotal), 0) AS revenue
            FROM {POSTGRES_SIDECAR_SCHEMA}.employee_accounts ea
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.in_house_sales ihs ON ihs.employee_id = ea.id
            WHERE ea.active = 1
        """
        params = []
        if q:
            query += " AND (LOWER(COALESCE(ea.name, '')) LIKE %s OR LOWER(COALESCE(ea.name_key, '')) LIKE %s)"
            ql = f"%{_employee_name_key(q)}%"
            params.extend([ql, ql])
        query += """
            GROUP BY ea.id, ea.name, ea.name_key, ea.active, ea.auto_approve_in_house_orders, ea.allow_self_service_returns, ea.last_sale_at
            ORDER BY COALESCE(ea.last_sale_at, '') DESC, ea.name ASC
            LIMIT %s
        """
        params.append(int(limit or 200))
        with _pg_connect() as pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return _pg_fetchall_dict(cur)
    except Exception as exc:
        log_cutover_event("employees", "postgres_primary_failed_closed", "list_employee_accounts", q or "all", {"error": str(exc)})
        raise


def update_employee_account_settings(employee_id, active=None, auto_approve_in_house_orders=None, allow_self_service_returns=None):
    _require_company_postgres_runtime("employees")
    employee_id = int(employee_id or 0)
    if employee_id <= 0:
        raise ValueError("employee id required")
    try:
        with pg_domain_tx("employees", "update_employee_account_settings") as (_pg_conn, cur):
            _pg_ensure_employee_account_policy_columns(cur)
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.employee_accounts WHERE id = %s",
                (employee_id,),
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                raise ValueError("employee account not found")
            updates = []
            params = []
            if active is not None:
                updates.append("active = %s")
                params.append(bool(active))
            if auto_approve_in_house_orders is not None:
                updates.append("auto_approve_in_house_orders = %s")
                params.append(bool(auto_approve_in_house_orders))
            if allow_self_service_returns is not None:
                updates.append("allow_self_service_returns = %s")
                params.append(bool(allow_self_service_returns))
            if updates:
                updates.append("updated_at = %s")
                now = utc_now()
                params.append(now)
                params.append(employee_id)
                cur.execute(
                    f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.employee_accounts SET {', '.join(updates)} WHERE id = %s",
                    tuple(params),
                )
                row["updated_at"] = now
            if active is not None:
                row["active"] = bool(active)
            if auto_approve_in_house_orders is not None:
                row["auto_approve_in_house_orders"] = bool(auto_approve_in_house_orders)
            if allow_self_service_returns is not None:
                row["allow_self_service_returns"] = bool(allow_self_service_returns)
        return row
    except Exception as exc:
        log_cutover_event("employees", "postgres_primary_failed_closed", "update_employee_account_settings", employee_id, {"error": str(exc)})
        raise


def get_mega_dashboard_summary():
    _require_company_postgres_runtime("company_results")
    ensure_wave1_postgres_schema()
    canonical_filter_pg = _PG_CANONICAL_AUCTION_RESULT_FILTER
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
            SELECT
                CASE
                    WHEN LOWER(COALESCE(cs.show_id, '')) LIKE 'tiktok:%'
                      OR LOWER(COALESCE(cs.name, '')) LIKE 'tiktok%%'
                    THEN 'tiktok_live'
                    ELSE 'whatnot'
                END AS source,
                COUNT(*) AS result_count,
                COUNT(DISTINCT ar.session_id) AS session_count,
                COALESCE(SUM(ar.products_sold_count), 0) AS units_sold,
                COALESCE(SUM(ar.sale_price), 0) AS revenue,
                COALESCE(SUM(ar.cost_price), 0) AS cost,
                COALESCE(SUM(ar.fees), 0) AS fees,
                COALESCE(SUM(ar.profit), 0) AS profit
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = ar.session_id
            WHERE {canonical_filter_pg}
            GROUP BY source
            """
            )
            auction_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
            SELECT
                LOWER(COALESCE(order_source, 'whatnot')) AS source,
                COUNT(*) AS order_count,
                COALESCE(SUM(total_amount), 0) AS amount,
                SUM(CASE WHEN state = 'sale' THEN 1 ELSE 0 END) AS confirmed_count,
                SUM(CASE WHEN state = 'cancel' THEN 1 ELSE 0 END) AS cancelled_count,
                SUM(CASE WHEN state IN ('draft', 'sent') THEN 1 ELSE 0 END) AS draft_count
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders
            GROUP BY LOWER(COALESCE(order_source, 'whatnot'))
            """
            )
            order_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
            SELECT
                id, name, status, started_at, ended_at, total_revenue,
                total_cost, total_fees, total_profit, total_products_sold, total_lots_sold,
                show_id, stream_id
            FROM {POSTGRES_SIDECAR_SCHEMA}.company_sessions
            ORDER BY COALESCE(started_at, created_at) DESC
            LIMIT 8
            """
            )
            sessions = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
            SELECT
                COALESCE(ar.product_name, 'Unknown') AS product_name,
                COUNT(*) AS times_sold,
                COALESCE(SUM(ar.products_sold_count), 0) AS units_sold,
                COALESCE(SUM(ar.sale_price), 0) AS revenue,
                COALESCE(SUM(ar.profit), 0) AS profit
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
            WHERE {canonical_filter_pg}
            GROUP BY COALESCE(ar.product_name, 'Unknown')
            ORDER BY profit DESC, revenue DESC
            LIMIT 8
            """
            )
            top_products = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
            SELECT
                SUBSTRING(COALESCE(ar.sold_at, '') FROM 1 FOR 10) AS day,
                CASE
                    WHEN LOWER(COALESCE(cs.show_id, '')) LIKE 'tiktok:%'
                      OR LOWER(COALESCE(cs.name, '')) LIKE 'tiktok%%'
                    THEN 'tiktok_live'
                    ELSE 'whatnot'
                END AS source,
                COUNT(*) AS count,
                COALESCE(SUM(ar.products_sold_count), 0) AS units,
                COALESCE(SUM(ar.sale_price), 0) AS revenue,
                COALESCE(SUM(ar.cost_price), 0) AS cost,
                COALESCE(SUM(ar.fees), 0) AS fees,
                COALESCE(SUM(ar.profit), 0) AS profit
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = ar.session_id
            WHERE {canonical_filter_pg}
              AND COALESCE(ar.sold_at, '') <> ''
            GROUP BY day, source
            ORDER BY day DESC
            LIMIT 60
            """
            )
            daily_auction_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
            SELECT
                SUBSTRING(COALESCE(sold_at, created_at, '') FROM 1 FOR 10) AS day,
                'in_house' AS source,
                COUNT(*) AS count,
                COALESCE(SUM(qty), 0) AS units,
                COALESCE(SUM(subtotal), 0) AS revenue,
                COALESCE(SUM(total_cost), 0) AS cost,
                0 AS fees,
                COALESCE(SUM(profit), 0) AS profit
            FROM {POSTGRES_SIDECAR_SCHEMA}.in_house_sales
            WHERE COALESCE(sold_at, created_at, '') <> ''
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
            """
            )
            daily_inhouse_rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
            SELECT
                COALESCE(pwa.status, 'unassigned') AS status,
                COUNT(*) AS count,
                COALESCE(SUM(CASE WHEN COALESCE(pwa.status, '') IN ('payment_review', 'payment_cancelled') THEN 0 ELSE ar.sale_price END), 0) AS live_revenue,
                COALESCE(SUM(CASE WHEN COALESCE(pwa.status, '') IN ('payment_review', 'payment_cancelled') THEN ar.sale_price ELSE 0 END), 0) AS held_revenue
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa ON pwa.auction_result_id = ar.id
            WHERE NOT EXISTS (
                SELECT 1
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa_dupe
                WHERE pwa_dupe.session_id = ar.session_id
                  AND pwa_dupe.status = 'confirmed'
                  AND COALESCE(pwa_dupe.lot_number, '') = COALESCE(ar.lot_number, '')
                  AND COALESCE(pwa_dupe.auction_result_id, 0) <> ar.id
            )
            GROUP BY COALESCE(pwa.status, 'unassigned')
            ORDER BY count DESC
            """
            )
            payment_status = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
            SELECT
                COALESCE(ar.winner_username, c.whatnot_username, 'Unknown') AS customer,
                COUNT(*) AS wins,
                COALESCE(SUM(ar.sale_price), 0) AS revenue,
                COALESCE(SUM(ar.profit), 0) AS profit
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = ar.customer_id
            WHERE {canonical_filter_pg}
            GROUP BY COALESCE(ar.winner_username, c.whatnot_username, 'Unknown')
            ORDER BY revenue DESC
            LIMIT 10
            """
            )
            top_customers = _pg_fetchall_dict(cur)
            cur.execute(f"SELECT COUNT(*) AS count FROM {POSTGRES_SIDECAR_SCHEMA}.customers")
            customer_count = _pg_fetchone_dict(cur) or {"count": 0}
        inventory = inventory_summary()
    inhouse = in_house_sales_summary()

    sources = {
        "whatnot": {"revenue": 0.0, "cost": 0.0, "fees": 0.0, "profit": 0.0, "orders": 0, "results": 0, "sessions": 0, "units": 0},
        "tiktok_live": {"revenue": 0.0, "cost": 0.0, "fees": 0.0, "profit": 0.0, "orders": 0, "results": 0, "sessions": 0, "units": 0},
        "in_house": {
            "revenue": inhouse["summary"]["revenue"],
            "cost": inhouse["summary"]["cost"],
            "fees": 0.0,
            "profit": inhouse["summary"]["profit"],
            "orders": inhouse["summary"]["sale_count"],
            "results": inhouse["summary"]["sale_count"],
            "sessions": 0,
            "units": inhouse["summary"]["units_sold"],
        },
    }
    for row in auction_rows:
        key = row.get("source") or "whatnot"
        bucket = sources[key]
        bucket["revenue"] += float(row.get("revenue") or 0)
        bucket["cost"] += float(row.get("cost") or 0)
        bucket["fees"] += float(row.get("fees") or 0)
        bucket["profit"] += float(row.get("profit") or 0)
        bucket["results"] += int(row.get("result_count") or 0)
        bucket["sessions"] += int(row.get("session_count") or 0)
        bucket["units"] += float(row.get("units_sold") or 0)
    totals = {"revenue": 0.0, "cost": 0.0, "fees": 0.0, "profit": 0.0, "orders": 0, "results": 0, "sessions": len(sessions), "units": 0.0}
    for bucket in sources.values():
        for key in ("revenue", "cost", "fees", "profit", "units"):
            bucket[key] = round(float(bucket.get(key) or 0), 2)
            totals[key] += bucket[key]
        totals["orders"] += int(bucket.get("orders") or 0)
        totals["results"] += int(bucket.get("results") or 0)
    totals = {key: (round(value, 2) if isinstance(value, float) else value) for key, value in totals.items()}
    totals["margin_pct"] = round((totals["profit"] / totals["revenue"]) * 100.0, 1) if totals["revenue"] else 0.0
    daily_map = {}
    for row in list(daily_auction_rows or []) + list(daily_inhouse_rows or []):
        day = row.get("day") or "Unknown"
        source = row.get("source") or "other"
        bucket = daily_map.setdefault(day, {
            "day": day,
            "revenue": 0.0,
            "cost": 0.0,
            "fees": 0.0,
            "profit": 0.0,
            "units": 0.0,
            "count": 0,
            "whatnot": 0.0,
            "tiktok_live": 0.0,
            "in_house": 0.0,
        })
        revenue = float(row.get("revenue") or 0)
        bucket["revenue"] += revenue
        bucket["cost"] += float(row.get("cost") or 0)
        bucket["fees"] += float(row.get("fees") or 0)
        bucket["profit"] += float(row.get("profit") or 0)
        bucket["units"] += float(row.get("units") or 0)
        bucket["count"] += int(row.get("count") or 0)
        bucket[source] = bucket.get(source, 0.0) + revenue
    daily_performance = []
    for bucket in sorted(daily_map.values(), key=lambda item: item["day"])[-30:]:
        for key in ("revenue", "cost", "fees", "profit", "units", "whatnot", "tiktok_live", "in_house"):
            bucket[key] = round(float(bucket.get(key) or 0), 2)
        bucket["margin_pct"] = round((bucket["profit"] / bucket["revenue"]) * 100.0, 1) if bucket["revenue"] else 0.0
        daily_performance.append(bucket)
    return {
        "ok": True,
        "totals": totals,
        "sources": sources,
        "inventory": inventory,
        "customers": {"count": int(customer_count.get("count") or 0)},
        "in_house": inhouse,
        "recent_sessions": sessions,
        "top_products": top_products,
        "top_customers": top_customers,
        "daily_performance": daily_performance,
        "payment_status": payment_status,
    }


def _pg_list_categories():
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, name, name AS complete_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.product_categories
                ORDER BY name ASC
                """
            )
            return _pg_fetchall_dict(cur)


def list_categories():
    _require_company_postgres_runtime("inventory_products")
    return _pg_list_categories()


def ensure_category(name):
    _require_company_postgres_runtime("inventory_products")
    now = utc_now()
    name = (name or "").strip()
    if not name:
        return None
    try:
        with pg_domain_tx("inventory_products", "product_categories") as (_pg_conn, cur):
            cur.execute(
                f"SELECT id, name FROM {POSTGRES_SIDECAR_SCHEMA}.product_categories WHERE LOWER(name)=LOWER(%s)",
                (name,),
            )
            existing = _pg_fetchone_dict(cur)
            if existing:
                category_id = int(existing["id"])
                category_name = existing["name"]
            else:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.product_categories (name, created_at, updated_at)
                    VALUES (%s, %s, %s)
                    RETURNING id, name
                    """,
                    (name, now, now),
                )
                created = _pg_fetchone_dict(cur) or {}
                category_id = int(created["id"])
                category_name = created["name"]
        return {"id": category_id, "name": category_name}
    except Exception as exc:
        log_cutover_event("inventory_products", "postgres_primary_failed_closed", "product_categories", name, {"error": str(exc)})
        raise


def delete_category(category_id):
    _require_company_postgres_runtime("inventory_products")
    try:
        with pg_domain_tx("inventory_products", "delete_category") as (_pg_conn, cur):
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.product_categories WHERE id = %s", (int(category_id),))
        return True
    except Exception as exc:
        log_cutover_event("inventory_products", "postgres_primary_failed_closed", "product_categories", category_id, {"error": str(exc)})
        raise


def delete_product(product_id):
    _require_company_postgres_runtime("inventory_products")
    product_id = int(product_id)
    try:
        with pg_domain_tx("inventory_products", "delete_product") as (_pg_conn, cur):
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_audit_log WHERE product_id = %s", (product_id,))
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements WHERE product_id = %s", (product_id,))
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items WHERE product_id = %s", (product_id,))
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines WHERE product_id = %s", (product_id,))
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.products WHERE id = %s", (product_id,))
        return {"deleted": True, "archived": False}
    except Exception as exc:
        log_cutover_event("inventory_products", "postgres_primary_failed_closed", "products", product_id, {"error": str(exc)})
        raise


def _pg_list_vendors():
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    name,
                    0 AS product_count,
                    0 AS active_count,
                    0 AS stock_value
                FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors
                ORDER BY LOWER(TRIM(name)) ASC
                """
            )
            return _pg_fetchall_dict(cur)


def list_vendors():
    _require_company_postgres_runtime("inventory_products")
    return _pg_list_vendors()


def ensure_purchase_vendor(name, notes=None):
    _require_company_postgres_runtime("inventory_products")
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("vendor_name is required")
    now = utc_now()
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s))",
                (clean_name,),
            )
            existing = _pg_fetchone_dict(cur)
            if existing:
                return existing
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors (name, notes, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (clean_name, str(notes or "").strip() or None, now, now),
            )
            row = _pg_fetchone_dict(cur)
        conn.commit()
    return row


def _purchase_order_status_summary(conn, purchase_order_id):
    return _fetchone_dict(
        conn,
        """
        SELECT
            COUNT(*) AS line_count,
            COALESCE(SUM(qty_ordered), 0) AS total_units_ordered,
            COALESCE(SUM(qty_received), 0) AS total_units_received,
            COALESCE(SUM(line_total), 0) AS subtotal_cost
        FROM purchase_order_lines
        WHERE purchase_order_id = ?
        """,
        (int(purchase_order_id),),
    ) or {"line_count": 0, "total_units_ordered": 0, "total_units_received": 0, "subtotal_cost": 0}


def _pg_purchase_order_status_summary(cur, purchase_order_id):
    cur.execute(
        f"""
        SELECT
            COUNT(*) AS line_count,
            COALESCE(SUM(qty_ordered), 0) AS total_units_ordered,
            COALESCE(SUM(qty_received), 0) AS total_units_received,
            COALESCE(SUM(line_total), 0) AS subtotal_cost
        FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines
        WHERE purchase_order_id = %s
        """,
        (int(purchase_order_id),),
    )
    return _pg_fetchone_dict(cur) or {"line_count": 0, "total_units_ordered": 0, "total_units_received": 0, "subtotal_cost": 0}


def _pg_ensure_id_sequence_txn(cur, table_name):
    sequence_name = f"{table_name}_id_seq"
    cur.execute(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = 'id'
        """,
        (POSTGRES_SIDECAR_SCHEMA, table_name),
    )
    current_default = str((_pg_fetchone_dict(cur) or {}).get("column_default") or "")
    if sequence_name in current_default:
        return
    cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.{sequence_name}")
    cur.execute(f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {POSTGRES_SIDECAR_SCHEMA}.{table_name}")
    max_id = int((_pg_fetchone_dict(cur) or {}).get("max_id") or 0)
    cur.execute(
        "SELECT setval(%s::regclass, %s, %s)",
        (f"{POSTGRES_SIDECAR_SCHEMA}.{sequence_name}", max(max_id, 1), bool(max_id)),
    )
    cur.execute(
        f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.{table_name} "
        f"ALTER COLUMN id SET DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.{sequence_name}'::regclass)"
    )
    cur.execute(
        f"ALTER SEQUENCE {POSTGRES_SIDECAR_SCHEMA}.{sequence_name} "
        f"OWNED BY {POSTGRES_SIDECAR_SCHEMA}.{table_name}.id"
    )


def _pg_ensure_purchase_schema():
    _require_company_postgres_runtime("inventory_products")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            for sequence_name in (
                "purchase_vendors_id_seq",
                "purchase_orders_id_seq",
                "purchase_order_lines_id_seq",
                "purchase_bargain_sessions_id_seq",
                "purchase_bargain_lines_id_seq",
            ):
                cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.{sequence_name}")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors (
                    id BIGINT PRIMARY KEY DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.purchase_vendors_id_seq'::regclass),
                    name TEXT UNIQUE,
                    notes TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.purchase_orders (
                    id BIGINT PRIMARY KEY DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.purchase_orders_id_seq'::regclass),
                    po_number TEXT UNIQUE,
                    vendor_name TEXT,
                    status TEXT,
                    order_date TEXT,
                    expected_date TEXT,
                    notes TEXT,
                    shipping_cost DOUBLE PRECISION DEFAULT 0,
                    tax_cost DOUBLE PRECISION DEFAULT 0,
                    misc_cost DOUBLE PRECISION DEFAULT 0,
                    subtotal_cost DOUBLE PRECISION DEFAULT 0,
                    total_cost DOUBLE PRECISION DEFAULT 0,
                    total_units_ordered DOUBLE PRECISION DEFAULT 0,
                    total_units_received DOUBLE PRECISION DEFAULT 0,
                    created_by TEXT,
                    received_at TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines (
                    id BIGINT PRIMARY KEY DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines_id_seq'::regclass),
                    purchase_order_id BIGINT,
                    product_id BIGINT,
                    product_name_snapshot TEXT,
                    barcode_snapshot TEXT,
                    sku_snapshot TEXT,
                    qty_ordered DOUBLE PRECISION DEFAULT 0,
                    qty_received DOUBLE PRECISION DEFAULT 0,
                    unit_cost DOUBLE PRECISION DEFAULT 0,
                    line_total DOUBLE PRECISION DEFAULT 0,
                    note TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions (
                    id BIGINT PRIMARY KEY DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions_id_seq'::regclass),
                    purchase_order_id BIGINT,
                    token TEXT,
                    expires_at TEXT,
                    status TEXT,
                    vendor_notes TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines (
                    id BIGINT PRIMARY KEY DEFAULT nextval('{POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines_id_seq'::regclass),
                    session_id BIGINT,
                    line_id BIGINT,
                    our_price DOUBLE PRECISION,
                    vendor_price DOUBLE PRECISION,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            for table_name in (
                "purchase_vendors",
                "purchase_orders",
                "purchase_order_lines",
                "purchase_bargain_sessions",
                "purchase_bargain_lines",
            ):
                _pg_ensure_id_sequence_txn(cur, table_name)
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_orders_status ON {POSTGRES_SIDECAR_SCHEMA}.purchase_orders(status)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_orders_vendor_name ON {POSTGRES_SIDECAR_SCHEMA}.purchase_orders(vendor_name)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_orders_created_at ON {POSTGRES_SIDECAR_SCHEMA}.purchase_orders(created_at DESC)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_vendors_name ON {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors(name)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_order_lines_po_id ON {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines(purchase_order_id)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_order_lines_product_id ON {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines(product_id)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_bargain_token ON {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions(token)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_bargain_po_id ON {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions(purchase_order_id)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_purchase_bargain_lines_session ON {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines(session_id)")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines ADD COLUMN IF NOT EXISTS availability_status TEXT")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines ADD COLUMN IF NOT EXISTS available_qty DOUBLE PRECISION")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines ADD COLUMN IF NOT EXISTS case_pack TEXT")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines ADD COLUMN IF NOT EXISTS replacement TEXT")
            cur.execute(f"ALTER TABLE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines ADD COLUMN IF NOT EXISTS bulk_discount TEXT")
        conn.commit()


def _refresh_purchase_order_totals_txn(conn, purchase_order_id):
    purchase_order_id = int(purchase_order_id)
    summary = _purchase_order_status_summary(conn, purchase_order_id)
    order = _fetchone_dict(conn, "SELECT * FROM purchase_orders WHERE id = ?", (purchase_order_id,))
    if not order:
        raise ValueError("purchase order not found")
    subtotal_cost = round(float(summary.get("subtotal_cost") or 0), 2)
    shipping_cost = float(order.get("shipping_cost") or 0)
    tax_cost = float(order.get("tax_cost") or 0)
    misc_cost = float(order.get("misc_cost") or 0)
    total_cost = round(subtotal_cost + shipping_cost + tax_cost + misc_cost, 2)
    ordered_units = float(summary.get("total_units_ordered") or 0)
    received_units = float(summary.get("total_units_received") or 0)
    status = str(order.get("status") or "draft")
    received_at = order.get("received_at")
    if status != "cancelled":
        if ordered_units > 0 and received_units >= ordered_units:
            status = "received"
            received_at = received_at or utc_now()
        elif received_units > 0:
            status = "partially_received"
        elif status not in {"draft", "ordered"}:
            status = "ordered"
            received_at = None
        elif status == "draft":
            received_at = None
    conn.execute(
        """
        UPDATE purchase_orders
        SET subtotal_cost = ?, total_cost = ?, total_units_ordered = ?, total_units_received = ?,
            status = ?, received_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            subtotal_cost,
            total_cost,
            ordered_units,
            received_units,
            status,
            received_at,
            utc_now(),
            purchase_order_id,
        ),
    )


def _pg_refresh_purchase_order_totals_txn(cur, purchase_order_id):
    purchase_order_id = int(purchase_order_id)
    summary = _pg_purchase_order_status_summary(cur, purchase_order_id)
    cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE id = %s", (purchase_order_id,))
    order = _pg_fetchone_dict(cur)
    if not order:
        raise ValueError("purchase order not found")
    subtotal_cost = round(float(summary.get("subtotal_cost") or 0), 2)
    shipping_cost = float(order.get("shipping_cost") or 0)
    tax_cost = float(order.get("tax_cost") or 0)
    misc_cost = float(order.get("misc_cost") or 0)
    total_cost = round(subtotal_cost + shipping_cost + tax_cost + misc_cost, 2)
    ordered_units = float(summary.get("total_units_ordered") or 0)
    received_units = float(summary.get("total_units_received") or 0)
    status = str(order.get("status") or "draft")
    received_at = order.get("received_at")
    if status != "cancelled":
        if ordered_units > 0 and received_units >= ordered_units:
            status = "received"
            received_at = received_at or utc_now()
        elif received_units > 0:
            status = "partially_received"
        elif status not in {"draft", "ordered"}:
            status = "ordered"
            received_at = None
        elif status == "draft":
            received_at = None
    cur.execute(
        f"""
        UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_orders
        SET subtotal_cost = %s, total_cost = %s, total_units_ordered = %s, total_units_received = %s,
            status = %s, received_at = %s, updated_at = %s
        WHERE id = %s
        """,
        (
            subtotal_cost,
            total_cost,
            ordered_units,
            received_units,
            status,
            received_at,
            utc_now(),
            purchase_order_id,
        ),
    )


def _next_purchase_order_number_txn(conn):
    prefix = "PO-YNF"
    for attempt in range(1, 1000):
        po_number = f"{prefix}-{attempt:03d}"
        exists = _fetchone_dict(conn, "SELECT id FROM purchase_orders WHERE po_number = ?", (po_number,))
        if not exists:
            return po_number
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def _pg_next_purchase_order_number_txn(cur):
    prefix = "PO-YNF"
    for attempt in range(1, 1000):
        po_number = f"{prefix}-{attempt:03d}"
        cur.execute(f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE po_number = %s", (po_number,))
        exists = _pg_fetchone_dict(cur)
        if not exists:
            return po_number
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def list_purchase_orders(status=None, q=None, limit=250):
    _require_company_postgres_runtime("inventory_products")
    limit = max(1, min(int(limit or 250), 500))
    params = []
    query = f"""
        SELECT
            po.*,
            COUNT(pol.id) AS line_count,
            SUM(CASE WHEN COALESCE(pol.qty_received, 0) < COALESCE(pol.qty_ordered, 0) THEN 1 ELSE 0 END) AS open_line_count
        FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders po
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines pol ON pol.purchase_order_id = po.id
        WHERE 1=1
    """
    if status and str(status).strip():
        query += " AND po.status = %s"
        params.append(str(status).strip())
    if q and str(q).strip():
        term = f"%{str(q).strip().lower()}%"
        query += """
            AND (
                LOWER(po.po_number) LIKE %s
                OR LOWER(po.vendor_name) LIKE %s
                OR LOWER(COALESCE(po.notes, '')) LIKE %s
            )
        """
        params.extend([term, term, term])
    query += """
        GROUP BY po.id
        ORDER BY po.created_at DESC, po.id DESC
        LIMIT %s
    """
    params.append(limit)
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS order_count,
                    COALESCE(SUM(total_cost), 0) AS total_cost,
                    COALESCE(SUM(total_units_ordered), 0) AS total_units_ordered,
                    COALESCE(SUM(total_units_received), 0) AS total_units_received
                FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders
                WHERE status != 'cancelled'
                """
            )
            summary = _pg_fetchone_dict(cur) or {}
    return {"rows": rows, "summary": summary}


def get_purchase_order_detail(purchase_order_id):
    _require_company_postgres_runtime("inventory_products")
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE id = %s", (int(purchase_order_id),))
            order = _pg_fetchone_dict(cur)
            if not order:
                return None
            cur.execute(
                f"""
                SELECT
                    pol.*,
                    p.name AS current_product_name,
                    p.brand,
                    p.on_hand_qty,
                    p.image_path
                FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines pol
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = pol.product_id
                WHERE pol.purchase_order_id = %s
                ORDER BY pol.id ASC
                """,
                (int(purchase_order_id),),
            )
            lines = _pg_fetchall_dict(cur)
            summary = _pg_purchase_order_status_summary(cur, int(purchase_order_id))
    return {"order": order, "lines": lines, "summary": summary}


def create_purchase_order(
    *,
    vendor_name,
    lines,
    status="draft",
    order_date=None,
    expected_date=None,
    notes=None,
    shipping_cost=0,
    tax_cost=0,
    misc_cost=0,
    created_by=None,
):
    _require_company_postgres_runtime("inventory_products")
    clean_vendor = str(vendor_name or "").strip()
    if not clean_vendor:
        raise ValueError("vendor_name is required")
    if not isinstance(lines, list) or not lines:
        raise ValueError("at least one purchase order line is required")
    clean_status = str(status or "draft").strip().lower()
    if clean_status not in {"draft", "ordered"}:
        clean_status = "draft"
    now = utc_now()
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, name FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s))",
                (clean_vendor,),
            )
            existing_vendor = _pg_fetchone_dict(cur)
            if not existing_vendor:
                cur.execute(
                    f"INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors (name, created_at, updated_at) VALUES (%s, %s, %s)",
                    (clean_vendor, now, now),
                )
            po_number = _pg_next_purchase_order_number_txn(cur)
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.purchase_orders (
                    po_number, vendor_name, status, order_date, expected_date, notes,
                    shipping_cost, tax_cost, misc_cost, created_by, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    po_number, clean_vendor, clean_status, order_date or now[:10], expected_date, notes,
                    float(shipping_cost or 0), float(tax_cost or 0), float(misc_cost or 0),
                    created_by, now, now,
                ),
            )
            purchase_order_id = int(_pg_fetchone_dict(cur)["id"])
            inserted_lines = 0
            for line in lines:
                product_id = int(line.get("product_id") or 0)
                qty_ordered = float(line.get("qty_ordered") or 0)
                if product_id <= 0 or qty_ordered <= 0:
                    continue
                cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.products WHERE id = %s", (product_id,))
                product = _pg_fetchone_dict(cur)
                if not product:
                    continue
                unit_cost = float(line.get("unit_cost") if line.get("unit_cost") not in (None, "") else (product.get("cost_price") or 0))
                line_total = round(qty_ordered * unit_cost, 2)
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines (
                        purchase_order_id, product_id, product_name_snapshot, barcode_snapshot, sku_snapshot,
                        qty_ordered, qty_received, unit_cost, line_total, note, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s)
                    """,
                    (
                        purchase_order_id, product_id, product.get("name"), product.get("barcode"), product.get("sku"),
                        qty_ordered, unit_cost, line_total, str(line.get("note") or "").strip() or None, now, now,
                    ),
                )
                inserted_lines += 1
            if inserted_lines <= 0:
                raise ValueError("at least one valid purchase order line is required")
            _pg_refresh_purchase_order_totals_txn(cur, purchase_order_id)
        conn.commit()
    return get_purchase_order_detail(purchase_order_id)


def update_purchase_order(purchase_order_id, *, vendor_name=None, status=None, order_date=None, expected_date=None, notes=None,
                          shipping_cost=None, tax_cost=None, misc_cost=None, lines=None):
    _require_company_postgres_runtime("inventory_products")
    purchase_order_id = int(purchase_order_id)
    now = utc_now()
    clean_vendor = str(vendor_name or "").strip()
    if not clean_vendor:
        raise ValueError("vendor_name is required")
    clean_status = str(status or "draft").strip().lower()
    if clean_status not in {"draft", "ordered", "partially_received", "received", "cancelled"}:
        clean_status = "draft"
    if not isinstance(lines, list) or not lines:
        raise ValueError("at least one purchase order line is required")

    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE id = %s", (purchase_order_id,))
            order = _pg_fetchone_dict(cur)
            if not order:
                raise ValueError("purchase_order_not_found")
            cur.execute(
                f"SELECT id, name FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s))",
                (clean_vendor,),
            )
            existing_vendor = _pg_fetchone_dict(cur)
            if not existing_vendor:
                cur.execute(
                    f"INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.purchase_vendors (name, created_at, updated_at) VALUES (%s, %s, %s)",
                    (clean_vendor, now, now),
                )
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_orders
                SET vendor_name = %s, status = %s, order_date = %s, expected_date = %s, notes = %s,
                    shipping_cost = %s, tax_cost = %s, misc_cost = %s, updated_at = %s
                WHERE id = %s
                """,
                (
                    clean_vendor, clean_status, order_date or order.get("order_date") or now[:10], expected_date, notes,
                    float(shipping_cost if shipping_cost not in (None, "") else order.get("shipping_cost") or 0),
                    float(tax_cost if tax_cost not in (None, "") else order.get("tax_cost") or 0),
                    float(misc_cost if misc_cost not in (None, "") else order.get("misc_cost") or 0),
                    now, purchase_order_id,
                ),
            )
            keep_line_ids = set()
            for line in lines:
                line_id = int(line.get("id") or 0)
                if line_id > 0:
                    cur.execute(
                        f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines WHERE id = %s AND purchase_order_id = %s",
                        (line_id, purchase_order_id),
                    )
                    existing_line = _pg_fetchone_dict(cur)
                    if not existing_line:
                        continue
                else:
                    product_id = int(line.get("product_id") or 0)
                    qty_ordered = float(line.get("qty_ordered") or 0)
                    if product_id <= 0 or qty_ordered <= 0:
                        continue
                    cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.products WHERE id = %s", (product_id,))
                    product = _pg_fetchone_dict(cur)
                    if not product:
                        continue
                    unit_cost = float(line.get("unit_cost") if line.get("unit_cost") not in (None, "") else (product.get("cost_price") or 0))
                    line_total = round(qty_ordered * unit_cost, 2)
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines (
                            purchase_order_id, product_id, product_name_snapshot, barcode_snapshot, sku_snapshot,
                            qty_ordered, qty_received, unit_cost, line_total, note, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            purchase_order_id, product_id, product.get("name"), product.get("barcode"), product.get("sku"),
                            qty_ordered, unit_cost, line_total, str(line.get("note") or "").strip() or None, now, now,
                        ),
                    )
                    keep_line_ids.add(int(_pg_fetchone_dict(cur)["id"]))
                    continue
                keep_line_ids.add(line_id)
                qty_received = float(existing_line.get("qty_received") or 0)
                qty_ordered = float(line.get("qty_ordered") or 0)
                if qty_ordered < qty_received:
                    raise ValueError(f"line {line_id}: ordered quantity cannot be less than already received quantity")
                unit_cost = float(line.get("unit_cost") if line.get("unit_cost") not in (None, "") else existing_line.get("unit_cost") or 0)
                line_total = round(qty_ordered * unit_cost, 2)
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines
                    SET qty_ordered = %s, unit_cost = %s, line_total = %s, note = %s, updated_at = %s
                    WHERE id = %s AND purchase_order_id = %s
                    """,
                    (qty_ordered, unit_cost, line_total, str(line.get("note") or "").strip() or None, now, line_id, purchase_order_id),
                )
            cur.execute(
                f"SELECT id, qty_received FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines WHERE purchase_order_id = %s",
                (purchase_order_id,),
            )
            existing_lines = _pg_fetchall_dict(cur)
            for existing in existing_lines:
                existing_id = int(existing.get('id') or 0)
                if existing_id in keep_line_ids:
                    continue
                if float(existing.get('qty_received') or 0) > 0:
                    raise ValueError(f"line {existing_id}: cannot remove a line that already has received quantity")
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines WHERE id = %s AND purchase_order_id = %s",
                    (existing_id, purchase_order_id),
                )
            cur.execute(
                f"SELECT COUNT(*) AS line_count FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines WHERE purchase_order_id = %s",
                (purchase_order_id,),
            )
            remaining = _pg_fetchone_dict(cur)
            if int((remaining or {}).get("line_count") or 0) <= 0:
                raise ValueError("at least one valid purchase order line is required")
            _pg_refresh_purchase_order_totals_txn(cur, purchase_order_id)
        conn.commit()
    return get_purchase_order_detail(purchase_order_id)


def delete_purchase_order(purchase_order_id):
    _require_company_postgres_runtime("inventory_products")
    purchase_order_id = int(purchase_order_id)
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE id = %s", (purchase_order_id,))
            order = _pg_fetchone_dict(cur)
            if not order:
                raise ValueError("purchase_order_not_found")
            summary = _pg_purchase_order_status_summary(cur, purchase_order_id)
            if float(summary.get("total_units_received") or 0) > 0:
                raise ValueError("cannot_delete_received_purchase_order")
            cur.execute(
                f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines WHERE session_id IN (SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions WHERE purchase_order_id = %s)",
                (purchase_order_id,),
            )
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions WHERE purchase_order_id = %s", (purchase_order_id,))
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines WHERE purchase_order_id = %s", (purchase_order_id,))
            cur.execute(f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE id = %s", (purchase_order_id,))
        conn.commit()
    return {"deleted": 1, "order_id": purchase_order_id}


def _pg_sync_received_purchase_costs_txn(cur, purchase_order_id, *, po_number=None, actor=None, created_at=None):
    now = created_at or utc_now()
    cur.execute(
        f"""
        SELECT
            pol.id AS line_id,
            pol.product_id,
            pol.unit_cost,
            p.*
        FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines pol
        JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = pol.product_id
        WHERE pol.purchase_order_id = %s
          AND COALESCE(pol.qty_received, 0) > 0
          AND COALESCE(pol.unit_cost, 0) > 0
        ORDER BY pol.id ASC
        """,
        (int(purchase_order_id),),
    )
    rows = _pg_fetchall_dict(cur)
    updated = []
    for row in rows:
        product_id = int(row.get("product_id") or 0)
        unit_cost = float(row.get("unit_cost") or 0)
        if product_id <= 0 or unit_cost <= 0:
            continue
        cost_plus_12 = round(unit_cost * 1.12, 2)
        cost_plus_20 = round(unit_cost * 1.20, 2)
        before_cost = dict(row)
        if (
            not _values_differ(before_cost.get("cost_price"), unit_cost)
            and not _values_differ(before_cost.get("raw_cost"), unit_cost)
            and not _values_differ(before_cost.get("cost_plus_12"), cost_plus_12)
            and not _values_differ(before_cost.get("cost_plus_20"), cost_plus_20)
        ):
            continue
        cur.execute(
            f"""
            UPDATE {POSTGRES_SIDECAR_SCHEMA}.products
            SET cost_price = %s,
                raw_cost = %s,
                cost_plus_12 = %s,
                cost_plus_20 = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (unit_cost, unit_cost, cost_plus_12, cost_plus_20, now, product_id),
        )
        after_cost = _pg_fetchone_dict(cur)
        changed_fields = {}
        if after_cost:
            for key in ("cost_price", "raw_cost", "cost_plus_12", "cost_plus_20", "updated_at"):
                if _values_differ(before_cost.get(key), after_cost.get(key)):
                    changed_fields[key] = {"before": before_cost.get(key), "after": after_cost.get(key)}
        if changed_fields:
            _pg_write_inventory_audit_txn(
                cur,
                product_id,
                event_type="purchase_cost_update",
                source="purchase_order_receive",
                actor=actor,
                changed_fields=changed_fields,
                metadata={
                    "po_number": po_number,
                    "purchase_order_id": int(purchase_order_id),
                    "line_id": int(row.get("line_id") or 0),
                    "unit_cost": unit_cost,
                },
                created_at=now,
            )
            updated.append({
                "line_id": int(row.get("line_id") or 0),
                "product_id": product_id,
                "unit_cost": unit_cost,
            })
    return updated


def receive_purchase_order(purchase_order_id, receipts, received_by=None):
    _require_company_postgres_runtime("inventory_products")
    purchase_order_id = int(purchase_order_id)
    if not isinstance(receipts, list) or not receipts:
        raise ValueError("at least one receipt line is required")
    now = utc_now()
    applied = []
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE id = %s", (purchase_order_id,))
            order = _pg_fetchone_dict(cur)
            if not order:
                raise ValueError("purchase order not found")
            if str(order.get("status") or "").lower() == "cancelled":
                raise ValueError("cancelled purchase orders cannot be received")
            for row in receipts:
                line_id = int(row.get("line_id") or 0)
                qty_received_now = float(row.get("qty_received_now") or 0)
                if line_id <= 0 or qty_received_now <= 0:
                    continue
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines WHERE id = %s AND purchase_order_id = %s",
                    (line_id, purchase_order_id),
                )
                line = _pg_fetchone_dict(cur)
                if not line:
                    continue
                remaining = max(0.0, float(line.get("qty_ordered") or 0) - float(line.get("qty_received") or 0))
                if qty_received_now > remaining + 0.0001:
                    raise ValueError(f"received quantity exceeds remaining quantity for line {line_id}")
                cur.execute(
                    f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines SET qty_received = %s, updated_at = %s WHERE id = %s",
                    (float(line.get("qty_received") or 0) + qty_received_now, now, line_id),
                )
                applied.append({
                    "line_id": line_id,
                    "product_id": int(line["product_id"]),
                    "qty_received_now": qty_received_now,
                    "unit_cost": float(line.get("unit_cost") or 0),
                })
            for item in applied:
                _pg_record_inventory_movement_txn(
                    cur,
                    item["product_id"],
                    "purchase_receive",
                    item["qty_received_now"],
                    reason=f"purchase_order_receive:{order.get('po_number')}",
                    reference_type="purchase_order",
                    reference_id=purchase_order_id,
                )
            if not applied:
                raise ValueError("no valid receipt lines were applied")
            cost_updates = _pg_sync_received_purchase_costs_txn(
                cur,
                purchase_order_id,
                po_number=order.get("po_number"),
                actor=received_by,
                created_at=now,
            )
            _pg_refresh_purchase_order_totals_txn(cur, purchase_order_id)
            if received_by:
                cur.execute(
                    f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_orders SET notes = COALESCE(notes, '') || %s, updated_at = %s WHERE id = %s",
                    (f"\nReceived by {received_by} on {now}", now, purchase_order_id),
                )
        conn.commit()
    return {"order": get_purchase_order_detail(purchase_order_id), "applied": applied, "cost_updates": cost_updates}


# ── Vendor Bargain Sessions ────────────────────────────────────────────────

def create_bargain_session(purchase_order_id: int, ttl_hours: int = 48):
    _require_company_postgres_runtime("inventory_products")
    purchase_order_id = int(purchase_order_id)
    now = utc_now()
    token = str(uuid.uuid4()).replace("-", "")
    expires_at = (
        datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(hours=int(ttl_hours or 48))
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE id = %s", (purchase_order_id,))
            order = _pg_fetchone_dict(cur)
            if not order:
                raise ValueError("purchase order not found")
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines WHERE purchase_order_id = %s ORDER BY id ASC",
                (purchase_order_id,),
            )
            lines = _pg_fetchall_dict(cur)
            if not lines:
                raise ValueError("purchase order has no lines")
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions
                    (purchase_order_id, token, expires_at, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'pending', %s, %s)
                RETURNING id
                """,
                (purchase_order_id, token, expires_at, now, now),
            )
            session_id = int(_pg_fetchone_dict(cur)["id"])
            for line in lines:
                cur.execute(
                    f"""
                    INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines
                        (session_id, line_id, our_price, vendor_price, created_at, updated_at)
                    VALUES (%s, %s, %s, NULL, %s, %s)
                    """,
                    (session_id, int(line["id"]), float(line.get("unit_cost") or 0), now, now),
                )
        conn.commit()
    return {
        "session_id": session_id,
        "token": token,
        "expires_at": expires_at,
        "purchase_order_id": purchase_order_id,
        "po_number": order.get("po_number"),
        "vendor_name": order.get("vendor_name"),
    }


def get_bargain_sessions_for_order(purchase_order_id: int):
    _require_company_postgres_runtime("inventory_products")
    purchase_order_id = int(purchase_order_id)
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions WHERE purchase_order_id = %s ORDER BY created_at DESC",
                (purchase_order_id,),
            )
            sessions = _pg_fetchall_dict(cur)
            for session in sessions:
                cur.execute(
                    f"""
                    SELECT pbl.*, pol.product_name_snapshot, pol.barcode_snapshot,
                           pol.qty_ordered, p.name AS current_product_name
                    FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines pbl
                    JOIN {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines pol ON pol.id = pbl.line_id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = pol.product_id
                    WHERE pbl.session_id = %s
                    ORDER BY pbl.id ASC
                    """,
                    (int(session["id"]),),
                )
                session["lines"] = _pg_fetchall_dict(cur)
    return sessions


def get_bargain_session_by_token(token: str):
    _require_company_postgres_runtime("inventory_products")
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions WHERE token = %s",
                (str(token),),
            )
            session = _pg_fetchone_dict(cur)
            if not session:
                return None
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_orders WHERE id = %s",
                (int(session["purchase_order_id"]),),
            )
            order = _pg_fetchone_dict(cur)
            cur.execute(
                f"""
                SELECT pbl.*, pol.product_name_snapshot, pol.barcode_snapshot, pol.sku_snapshot,
                       pol.qty_ordered, p.name AS current_product_name, p.brand
                FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines pbl
                JOIN {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines pol ON pol.id = pbl.line_id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = pol.product_id
                WHERE pbl.session_id = %s
                ORDER BY pbl.id ASC
                """,
                (int(session["id"]),),
            )
            lines = _pg_fetchall_dict(cur)
    return {"session": session, "order": order, "lines": lines}


def _ensure_purchase_bargain_extra_columns(conn):
    _ensure_column(conn, "purchase_bargain_lines", "availability_status", "availability_status TEXT")
    _ensure_column(conn, "purchase_bargain_lines", "available_qty", "available_qty REAL")
    _ensure_column(conn, "purchase_bargain_lines", "case_pack", "case_pack TEXT")
    _ensure_column(conn, "purchase_bargain_lines", "replacement", "replacement TEXT")
    _ensure_column(conn, "purchase_bargain_lines", "bulk_discount", "bulk_discount TEXT")


def submit_bargain(token: str, vendor_prices: list, vendor_notes: str | None = None):
    _require_company_postgres_runtime("inventory_products")
    now = utc_now()
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions WHERE token = %s",
                (str(token),),
            )
            session = _pg_fetchone_dict(cur)
            if not session:
                raise ValueError("bargain session not found")
            if str(session.get("status") or "") not in ("pending",):
                raise ValueError("bargain session is no longer open for submission")
            expires_at = str(session.get("expires_at") or "")
            if expires_at and expires_at < now:
                raise ValueError("bargain session link has expired")
            quote_rows = []
            for item in (vendor_prices or []):
                try:
                    quote_rows.append({
                        "line_id": int(item["line_id"]),
                        "vendor_price": float(item.get("vendor_price") or 0),
                        "availability_status": str(item.get("availability_status") or "available").strip()[:40],
                        "available_qty": float(item.get("available_qty") or 0) if item.get("available_qty") not in (None, "") else None,
                        "case_pack": str(item.get("case_pack") or "").strip()[:80] or None,
                        "replacement": str(item.get("replacement") or "").strip()[:240] or None,
                        "bulk_discount": str(item.get("bulk_discount") or "").strip()[:240] or None,
                    })
                except (TypeError, ValueError):
                    continue
            for row in quote_rows:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines
                    SET vendor_price = %s, availability_status = %s, available_qty = %s, case_pack = %s,
                        replacement = %s, bulk_discount = %s, updated_at = %s
                    WHERE session_id = %s AND line_id = %s
                    """,
                    (
                        row["vendor_price"], row["availability_status"], row["available_qty"], row["case_pack"],
                        row["replacement"], row["bulk_discount"], now, int(session["id"]), row["line_id"],
                    ),
                )
            if not quote_rows:
                raise ValueError("at least one vendor price is required")
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions SET status = 'submitted', vendor_notes = %s, updated_at = %s WHERE id = %s",
                (vendor_notes, now, int(session["id"])),
            )
        conn.commit()
    return get_bargain_session_by_token(token)


def accept_bargain(session_id: int):
    _require_company_postgres_runtime("inventory_products")
    session_id = int(session_id)
    now = utc_now()
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions WHERE id = %s", (session_id,))
            session = _pg_fetchone_dict(cur)
            if not session:
                raise ValueError("bargain session not found")
            if str(session.get("status") or "") != "submitted":
                raise ValueError("only submitted bargain sessions can be accepted")
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_lines WHERE session_id = %s AND vendor_price IS NOT NULL",
                (session_id,),
            )
            lines = _pg_fetchall_dict(cur)
            if not lines:
                raise ValueError("submitted bargain session has no vendor prices")
            for bl in lines:
                vendor_price = float(bl["vendor_price"])
                line_id = int(bl["line_id"])
                cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines WHERE id = %s", (line_id,))
                line = _pg_fetchone_dict(cur)
                if not line:
                    continue
                new_total = round(float(line.get("qty_ordered") or 0) * vendor_price, 2)
                cur.execute(
                    f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_order_lines SET unit_cost = %s, line_total = %s, updated_at = %s WHERE id = %s",
                    (vendor_price, new_total, now, line_id),
                )
            _pg_refresh_purchase_order_totals_txn(cur, int(session["purchase_order_id"]))
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions SET status = 'accepted', updated_at = %s WHERE id = %s",
                (now, session_id),
            )
        conn.commit()
    return get_purchase_order_detail(int(session["purchase_order_id"]))


def reject_bargain(session_id: int):
    _require_company_postgres_runtime("inventory_products")
    session_id = int(session_id)
    now = utc_now()
    _pg_ensure_purchase_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions WHERE id = %s", (session_id,))
            session = _pg_fetchone_dict(cur)
            if not session:
                raise ValueError("bargain session not found")
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.purchase_bargain_sessions SET status = 'rejected', updated_at = %s WHERE id = %s",
                (now, session_id),
            )
        conn.commit()
    return {"ok": True, "session_id": session_id, "status": "rejected"}


def _pg_get_product(product_id):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        _ensure_fragrance_research_pg_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT p.*, pc.name AS category_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.products p
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
                WHERE p.id = %s
                """,
                (int(product_id),),
            )
            return _pg_attach_fragrance_research(cur, _fetchone_dict_pg(cur))


def get_product(product_id):
    _require_company_postgres_runtime("inventory_products")
    return _pg_get_product(product_id)


def _fragrance_sources_by_product_pg(cur, product_ids):
    if not product_ids:
        return {}
    cur.execute(
        f"""
        SELECT *
        FROM {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_research_sources
        WHERE product_id = ANY(%s)
        ORDER BY product_id ASC, id ASC
        """,
        (list(product_ids),),
    )
    rows = _pg_fetchall_dict(cur)
    grouped = {}
    for row in rows:
        grouped.setdefault(int(row["product_id"]), []).append(row)
    return grouped


def _pg_attach_fragrance_research(cur, row):
    attached = _pg_attach_fragrance_research_many(cur, [row] if row else [])
    return attached[0] if attached else row


def _pg_attach_fragrance_research_many(cur, rows):
    if not rows:
        return rows
    product_ids = [int(row["id"]) for row in rows if row and row.get("id") is not None]
    if not product_ids:
        return rows
    cur.execute(
        f"""
        SELECT *
        FROM {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_profiles
        WHERE product_id = ANY(%s)
        """,
        (list(product_ids),),
    )
    profiles = _pg_fetchall_dict(cur)
    profile_map = {int(row["product_id"]): row for row in profiles}
    source_map = _fragrance_sources_by_product_pg(cur, product_ids)
    for row in rows:
        if not row or row.get("id") is None:
            continue
        product_id = int(row["id"])
        row["fragrance_research"] = profile_map.get(product_id)
        row["fragrance_research_sources"] = source_map.get(product_id, [])
    return rows


def set_product_details(product_id, audit_source="inventory_api", audit_actor=None, audit_context=None, **fields):
    _require_company_postgres_runtime("inventory_products")
    allowed = {
        "name", "sku", "barcode", "category_id", "brand", "supplier_name", "storage_bin", "product_type",
        "gender",
        "image_path", "cost_price", "raw_cost", "cost_plus_12", "cost_plus_20", "retail_price",
        "low_stock_threshold", "active", "notes", "notes_verified", "notes_verified_at", "description",
        "size_oz", "size_ml", "volume_oz", "volume_ml", "note_top", "note_mid", "note_base", "media_url", "script",
        "dupe_inspiration", "dupe_confidence", "dupe_classification", "dupe_notes",
        "similar_to", "image_gallery_urls", "source_fragrantica_url", "source_jomashop_url", "source_parfumo_url", "source_official_url",
        *TIKTOK_PRODUCT_FIELDS,
    }
    desired_on_hand = fields.get("on_hand_qty") if "on_hand_qty" in fields else None
    has_on_hand_override = "on_hand_qty" in fields
    if has_on_hand_override:
        raise ValueError(
            "Direct on_hand_qty overrides are blocked. "
            "Use record_inventory_movement(...) or an explicit inventory adjustment path instead."
        )
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates and not has_on_hand_override:
        return get_product(product_id)
    before_snapshot = get_product(product_id)
    if domain_primary_backend("inventory_products") == "postgres":
        try:
            product_id = int(product_id)
            after = before_snapshot
            if updates:
                updates["updated_at"] = utc_now()
            changed_fields = {}
            audit_row = None
            if updates:
                with pg_domain_tx("inventory_products", "products") as (_pg_conn, cur):
                    cur.execute(f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.products WHERE id = %s", (product_id,))
                    before = _pg_fetchone_dict(cur)
                    if not before:
                        raise ValueError("product not found")
                    assignments = ", ".join(f"{key} = %s" for key in updates)
                    params = list(updates.values()) + [product_id]
                    cur.execute(
                        f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.products SET {assignments} WHERE id = %s RETURNING *",
                        params,
                    )
                    after = _pg_fetchone_dict(cur)
                    if before and after:
                        for key in updates:
                            if key == "updated_at":
                                continue
                            before_value = before.get(key)
                            after_value = after.get(key)
                            if _values_differ(before_value, after_value):
                                changed_fields[key] = {"before": before_value, "after": after_value}
                    if changed_fields and domain_primary_backend("inventory_audit") == "postgres":
                        audit_row = _pg_write_inventory_audit_txn(
                            cur,
                            product_id,
                            event_type="product_update",
                            source=audit_source,
                            actor=audit_actor,
                            changed_fields=changed_fields,
                            metadata=audit_context or {},
                        )
            if has_on_hand_override:
                current_qty = float((after or before_snapshot or {}).get("on_hand_qty") or 0.0)
                desired_qty = float(desired_on_hand or 0.0)
                delta = desired_qty - current_qty
                if abs(delta) > 0.0001:
                    record_inventory_movement(
                        product_id,
                        "adjustment",
                        delta,
                        reason=str(audit_source or "product_adjustment").strip() or "product_adjustment",
                        reference_type="inventory",
                        reference_id=product_id,
                    )
            return get_product(product_id)
        except Exception as exc:
            log_cutover_event("inventory_products", "postgres_primary_failed_closed", "products", product_id, {"error": str(exc)})
            raise
    raise RuntimeError("postgres_runtime_required:inventory_products")


def set_product_fragrance_research(
    product_id,
    *,
    accords=None,
    fragrance_family=None,
    fragrance_dna=None,
    best_for_seasons=None,
    best_for_occasions=None,
    best_for_time_of_day=None,
    longevity=None,
    projection=None,
    sillage=None,
    compliment_factor=None,
    mood_keywords=None,
    similar_signature=None,
    inspired_by_signature=None,
    source_confidence=None,
    source_summary=None,
    verified_sources_count=0,
    needs_manual_review=0,
    last_researched_at=None,
    sources=None,
):
    now = utc_now()
    profile = {
        "accords": accords,
        "fragrance_family": fragrance_family,
        "fragrance_dna": fragrance_dna,
        "best_for_seasons": best_for_seasons,
        "best_for_occasions": best_for_occasions,
        "best_for_time_of_day": best_for_time_of_day,
        "longevity": longevity,
        "projection": projection,
        "sillage": sillage,
        "compliment_factor": compliment_factor,
        "mood_keywords": mood_keywords,
        "similar_signature": similar_signature,
        "inspired_by_signature": inspired_by_signature,
        "source_confidence": source_confidence,
        "source_summary": source_summary,
        "verified_sources_count": int(verified_sources_count or 0),
        "needs_manual_review": 1 if needs_manual_review else 0,
        "last_researched_at": last_researched_at or now,
    }

    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        _ensure_fragrance_research_pg_tables(conn)
        with conn.cursor() as cur:
            columns = ", ".join(profile.keys())
            placeholders = ", ".join(["%s"] * len(profile))
            updates = ", ".join(f"{key} = EXCLUDED.{key}" for key in profile.keys())
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_profiles (
                    product_id, {columns}, created_at, updated_at
                ) VALUES (%s, {placeholders}, %s, %s)
                ON CONFLICT (product_id) DO UPDATE SET
                    {updates},
                    updated_at = EXCLUDED.updated_at
                """,
                [int(product_id), *profile.values(), now, now],
            )
            if sources is not None:
                cur.execute(
                    f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_research_sources WHERE product_id = %s",
                    (int(product_id),),
                )
                for item in sources:
                    cur.execute(
                        f"""
                        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.product_fragrance_research_sources (
                            product_id, source_type, source_label, source_url, evidence_kind, evidence_excerpt, captured_at, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(product_id),
                            item.get("source_type"),
                            item.get("source_label"),
                            item.get("source_url"),
                            item.get("evidence_kind"),
                            item.get("evidence_excerpt"),
                            item.get("captured_at") or now,
                            now,
                            now,
                        ),
                    )
        conn.commit()

    return get_product(int(product_id))


def _pg_list_inventory_audit_logs(product_id=None, limit=50):
    query = f"""
        SELECT ial.*, p.name AS product_name, p.sku, p.barcode
        FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_audit_log ial
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = ial.product_id
        WHERE 1=1
    """
    params = []
    if product_id:
        query += " AND ial.product_id = %s"
        params.append(int(product_id))
    query += " ORDER BY ial.created_at DESC, ial.id DESC LIMIT %s"
    params.append(int(limit))
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = _pg_fetchall_dict(cur)
    for row in rows:
        for field in ("changed_fields", "metadata"):
            try:
                row[field] = json.loads(row.get(field) or "{}")
            except Exception:
                row[field] = {}
    return rows


def list_inventory_audit_logs(product_id=None, limit=50):
    _require_company_postgres_runtime("inventory_audit")
    return _pg_list_inventory_audit_logs(product_id=product_id, limit=limit)


def _pg_list_inventory_movements(product_id=None, limit=50):
    query = f"""
        SELECT im.*, p.name AS product_name
        FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements im
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = im.product_id
        WHERE 1=1
    """
    params = []
    if product_id:
        query += " AND im.product_id = %s"
        params.append(int(product_id))
    query += " ORDER BY im.created_at DESC LIMIT %s"
    params.append(int(limit))
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            return _pg_fetchall_dict(cur)


def list_inventory_movements(product_id=None, limit=50):
    _require_company_postgres_runtime("inventory_movements")
    return _pg_list_inventory_movements(product_id=product_id, limit=limit)


def _pg_inventory_movement_reference_totals(reference_types, reference_ids):
    clean_types = [str(value).strip() for value in (reference_types or []) if str(value or "").strip()]
    clean_ids = sorted({int(value) for value in (reference_ids or []) if value not in (None, "", False)})
    if not clean_types or not clean_ids:
        return []
    query = f"""
        SELECT
            reference_id,
            product_id,
            COALESCE(SUM(qty_delta), 0) AS net_qty
        FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
        WHERE reference_type = ANY(%s)
          AND reference_id = ANY(%s)
        GROUP BY reference_id, product_id
        ORDER BY reference_id ASC, product_id ASC
    """
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (clean_types, clean_ids))
            return _pg_fetchall_dict(cur)


def get_inventory_movement_reference_totals(reference_types, reference_ids):
    _require_company_postgres_runtime("inventory_movements")
    return _pg_inventory_movement_reference_totals(reference_types, reference_ids)


def get_inventory_integrity_audit(limit=100):
    _require_company_postgres_runtime("inventory_products")
    limit = max(1, min(int(limit or 100), 500))
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    p.id,
                    p.name,
                    p.barcode,
                    p.sku,
                    p.on_hand_qty,
                    COUNT(im.id) AS movement_count,
                    COALESCE(SUM(im.qty_delta), 0) AS movement_qty_total,
                    MAX(im.created_at) AS last_movement_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.products p
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.inventory_movements im ON im.product_id = p.id
                WHERE COALESCE(p.on_hand_qty, 0) < 0
                GROUP BY p.id, p.name, p.barcode, p.sku, p.on_hand_qty
                ORDER BY p.on_hand_qty ASC, p.id ASC
                LIMIT %s
                """,
                (limit,),
            )
            negative_products = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT
                    sol.id,
                    sol.sale_order_id,
                    sol.product_id,
                    sol.description,
                    sol.qty,
                    sol.inventory_applied,
                    so.order_number,
                    so.order_source,
                    so.state,
                    so.payment_status,
                    p.name AS product_name,
                    p.barcode
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders so ON so.id = sol.sale_order_id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                WHERE sol.product_id IS NOT NULL
                  AND COALESCE(sol.inventory_applied, 0) = 1
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements im
                      WHERE im.reference_type = 'sale_order'
                        AND im.reference_id = sol.sale_order_id
                        AND im.product_id = sol.product_id
                  )
                ORDER BY sol.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            applied_lines_without_movements = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT
                    sol.id,
                    sol.sale_order_id,
                    sol.product_id,
                    sol.description,
                    sol.qty,
                    sol.inventory_applied,
                    so.order_number,
                    so.order_source,
                    so.state,
                    so.payment_status,
                    p.name AS product_name,
                    p.barcode
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders so ON so.id = sol.sale_order_id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                WHERE sol.product_id IS NOT NULL
                  AND COALESCE(sol.inventory_applied, 0) = 0
                  AND LOWER(COALESCE(so.state, '')) = 'sale'
                  AND LOWER(COALESCE(so.payment_status, '')) = 'paid'
                ORDER BY sol.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            unapplied_confirmed_lines = _pg_fetchall_dict(cur)
            cur.execute(
                f"""
                SELECT
                    cs.id AS session_id,
                    cs.name AS session_name,
                    cs.status AS session_status,
                    cl.lot_number,
                    cli.id AS lot_item_id,
                    cli.product_id,
                    p.name AS product_name,
                    p.barcode,
                    COALESCE(SUM(im.qty_delta), 0) AS net_qty
                FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements im
                JOIN {POSTGRES_SIDECAR_SCHEMA}.company_lot_items cli ON cli.id = im.reference_id
                JOIN {POSTGRES_SIDECAR_SCHEMA}.company_lots cl ON cl.id = cli.lot_id
                JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = cl.session_id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = cli.product_id
                WHERE im.reference_type IN ('tiktok_live_pending_item', 'tiktok_live_pending_item_release')
                GROUP BY cs.id, cs.name, cs.status, cl.lot_number, cli.id, cli.product_id, p.name, p.barcode
                HAVING COALESCE(SUM(im.qty_delta), 0) < 0
                   AND LOWER(COALESCE(cs.status, '')) NOT IN ('live', 'open', 'draft')
                ORDER BY cs.id DESC, cl.lot_number ASC, cli.id ASC
                LIMIT %s
                """,
                (limit,),
            )
            ended_session_pending_reserves = _pg_fetchall_dict(cur)
    zero_movement_negatives = [row for row in negative_products if int(row.get("movement_count") or 0) == 0]

    return {
        "summary": {
            "negative_product_count": len(negative_products),
            "zero_movement_negative_count": len(zero_movement_negatives),
            "applied_line_without_movement_count": len(applied_lines_without_movements),
            "unapplied_confirmed_line_count": len(unapplied_confirmed_lines),
            "ended_session_pending_reserve_count": len(ended_session_pending_reserves),
        },
        "root_causes": [
            "TikTok LIVE pending reserves can drift when reservation sync runs repeatedly or is left attached to ended sessions.",
            "Confirmed sale-order lines can stay unapplied, so paid sales exist without inventory deduction.",
            "Order-line edits used to allow inventory_applied to be flipped manually without moving stock.",
            "Applied order lines used to be deletable without reversing inventory first.",
            "The legacy mirror-cutover still creates drift risk when the same stock event is not finalized in one path.",
        ],
        "negative_products": negative_products,
        "zero_movement_negatives": zero_movement_negatives,
        "applied_lines_without_movements": applied_lines_without_movements,
        "unapplied_confirmed_lines": unapplied_confirmed_lines,
        "ended_session_pending_reserves": ended_session_pending_reserves,
    }


def list_buyer_groups(session_id=None, q=None, limit=None, offset=0):
    _require_company_postgres_runtime("company_orders")
    query = f"""
        SELECT bg.*, c.display_name, c.email, c.phone, cs.name AS session_name
        FROM {POSTGRES_SIDECAR_SCHEMA}.buyer_groups bg
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = bg.customer_id
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = bg.session_id
        WHERE 1=1
    """
    params = []
    if session_id:
        query += " AND bg.session_id = %s"
        params.append(int(session_id))
    if q:
        query += " AND LOWER(bg.buyer_username) LIKE %s"
        params.append(f"%{q.lower()}%")
    query += " ORDER BY bg.total_revenue DESC, bg.id DESC"
    if limit is not None:
        query += " LIMIT %s OFFSET %s"
        params.extend([max(1, int(limit or 100)), max(0, int(offset or 0))])
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            return _pg_fetchall_dict(cur)


def get_buyer_group(group_id):
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT bg.*, c.display_name, c.email, c.phone
                FROM {POSTGRES_SIDECAR_SCHEMA}.buyer_groups bg
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = bg.customer_id
                WHERE bg.id = %s
                """,
                (int(group_id),),
            )
            return _pg_fetchone_dict(cur)


def list_buyer_group_lines(group_id):
    _require_company_postgres_runtime("company_orders")
    group = get_buyer_group(group_id)
    if not group:
        return []
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results
                WHERE session_id = %s
                  AND LOWER(COALESCE(winner_username, '')) = LOWER(COALESCE(%s, ''))
                ORDER BY sold_at DESC
                """,
                (int(group["session_id"]), group.get("buyer_username")),
            )
            rows = _pg_fetchall_dict(cur)
    result = []
    for row in rows:
        revenue = float(row.get("sale_price") or 0)
        cost = float(row.get("cost_price") or 0)
        profit = float(row.get("profit") or 0)
        margin = round((profit / revenue * 100.0), 1) if revenue else 0.0
        result.append({
            "sold_at": row.get("sold_at"),
            "lot_number": row.get("lot_number"),
            "barcode": row.get("barcode"),
            "sku": row.get("sku"),
            "product_name": row.get("product_name"),
            "sale_price": revenue,
            "allocated_revenue": revenue,
            "cost_price": cost,
            "fees": row.get("fees"),
            "profit": profit,
            "margin_pct": margin,
        })
    return result


_PAYMENT_HOLD_AUCTION_RESULT_EXCLUSION = """
    NOT EXISTS (
        SELECT 1
        FROM pending_winner_assignments pwa_cancel
        WHERE pwa_cancel.auction_result_id = ar.id
          AND pwa_cancel.status IN ('payment_review', 'payment_cancelled')
    )
"""

_CANONICAL_AUCTION_RESULT_FILTER = """
    NOT EXISTS (
        SELECT 1
        FROM pending_winner_assignments pwa
        WHERE pwa.session_id = ar.session_id
          AND pwa.status = 'confirmed'
          AND COALESCE(pwa.lot_number, '') = COALESCE(ar.lot_number, '')
          AND COALESCE(pwa.auction_result_id, 0) <> ar.id
    )
    AND NOT EXISTS (
        SELECT 1
        FROM sale_order_lines sol
        JOIN sale_orders so ON so.id = sol.sale_order_id
        WHERE sol.auction_result_id = ar.id
          AND LOWER(COALESCE(so.state, '')) = 'cancel'
    )
    AND """ + _PAYMENT_HOLD_AUCTION_RESULT_EXCLUSION + """
"""

_DEDUPED_AUCTION_RESULT_FILTER = """
    NOT EXISTS (
        SELECT 1
        FROM pending_winner_assignments pwa
        WHERE pwa.session_id = ar.session_id
          AND pwa.status = 'confirmed'
          AND COALESCE(pwa.lot_number, '') = COALESCE(ar.lot_number, '')
          AND COALESCE(pwa.auction_result_id, 0) <> ar.id
    )
"""

_PG_PAYMENT_HOLD_AUCTION_RESULT_EXCLUSION = _PAYMENT_HOLD_AUCTION_RESULT_EXCLUSION.replace(
    "FROM pending_winner_assignments",
    f"FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments",
)

_PG_CANONICAL_AUCTION_RESULT_FILTER = (
    _CANONICAL_AUCTION_RESULT_FILTER
    .replace(
        "FROM pending_winner_assignments",
        f"FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments",
    )
    .replace(
        "FROM sale_order_lines",
        f"FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines",
    )
    .replace(
        "JOIN sale_orders",
        f"JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders",
    )
    .replace(_PAYMENT_HOLD_AUCTION_RESULT_EXCLUSION, _PG_PAYMENT_HOLD_AUCTION_RESULT_EXCLUSION)
)


def _sale_order_metrics_subquery():
    return f"""
        SELECT
            sox.id AS sale_order_id,
            COUNT(DISTINCT ar.id) AS linked_results_count,
            COALESCE(SUM(ar.sale_price), 0) AS linked_revenue,
            COALESCE(SUM(ar.cost_price), 0) AS linked_cost,
            COALESCE(SUM(ar.fees), 0) AS linked_fees,
            COALESCE(SUM(ar.profit), 0) AS linked_profit,
            COALESCE(SUM(ar.products_sold_count), 0) AS linked_products_sold
        FROM sale_orders sox
        LEFT JOIN (
            SELECT DISTINCT sale_order_id, auction_result_id
            FROM sale_order_lines
            WHERE auction_result_id IS NOT NULL
        ) solx ON solx.sale_order_id = sox.id
        LEFT JOIN auction_results ar
          ON ar.id = solx.auction_result_id
         AND {_CANONICAL_AUCTION_RESULT_FILTER}
        GROUP BY sox.id
    """


def _sync_linked_sale_orders_for_assignment(conn, auction_result_id):
    if not auction_result_id:
        return
    order_rows = _fetchall_dict(
        conn,
        """
        SELECT DISTINCT sale_order_id
        FROM sale_order_lines
        WHERE auction_result_id = ?
          AND sale_order_id IS NOT NULL
        """,
        (int(auction_result_id),),
    )
    now = utc_now()
    for row in order_rows:
        order_id = int(row["sale_order_id"])
        summary = _fetchone_dict(
            conn,
            """
            SELECT
                COUNT(DISTINCT sol.auction_result_id) AS linked_result_count,
                COALESCE(SUM(CASE WHEN COALESCE(pwa.status, 'confirmed') = 'payment_cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_count
            FROM sale_order_lines sol
            LEFT JOIN pending_winner_assignments pwa ON pwa.id = (
                SELECT p.id
                FROM pending_winner_assignments p
                WHERE p.auction_result_id = sol.auction_result_id
                ORDER BY p.id DESC
                LIMIT 1
            )
            WHERE sol.sale_order_id = ?
              AND sol.auction_result_id IS NOT NULL
            """,
            (order_id,),
        ) or {}
        linked_result_count = int(summary.get("linked_result_count") or 0)
        cancelled_count = int(summary.get("cancelled_count") or 0)
        if linked_result_count > 0 and linked_result_count == cancelled_count:
            conn.execute(
                """
                UPDATE sale_orders
                SET state = 'cancel',
                    fulfillment_status = 'pending',
                    payment_status = 'unpaid',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, order_id),
            )
        elif linked_result_count > 0:
            conn.execute(
                """
                UPDATE sale_orders
                SET state = CASE WHEN state = 'cancel' THEN 'draft' ELSE state END,
                    fulfillment_status = CASE
                        WHEN fulfillment_status IS NULL OR fulfillment_status = '' THEN 'pending'
                        ELSE fulfillment_status
                    END,
                    payment_status = CASE
                        WHEN state = 'cancel' THEN 'unpaid'
                        ELSE payment_status
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, order_id),
            )
        _recalc_sale_order(conn, order_id)


def _pg_sync_linked_sale_orders_for_assignment_txn(cur, auction_result_id):
    if not auction_result_id:
        return
    cur.execute(
        f"""
        SELECT DISTINCT sale_order_id
        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
        WHERE auction_result_id = %s
          AND sale_order_id IS NOT NULL
        """,
        (int(auction_result_id),),
    )
    order_ids = [int(row[0]) for row in cur.fetchall() if row[0]]
    now = utc_now()
    for order_id in order_ids:
        cur.execute(
            f"""
            SELECT
                COUNT(DISTINCT sol.auction_result_id) AS linked_result_count,
                COALESCE(SUM(CASE WHEN COALESCE(pwa.status, 'confirmed') = 'payment_cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_count
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa ON pwa.id = (
                SELECT p.id
                FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments p
                WHERE p.auction_result_id = sol.auction_result_id
                ORDER BY p.id DESC
                LIMIT 1
            )
            WHERE sol.sale_order_id = %s
              AND sol.auction_result_id IS NOT NULL
            """,
            (order_id,),
        )
        summary = _pg_fetchone_dict(cur) or {}
        linked_result_count = int(summary.get("linked_result_count") or 0)
        cancelled_count = int(summary.get("cancelled_count") or 0)
        if linked_result_count > 0 and linked_result_count == cancelled_count:
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_orders
                SET state = 'cancel',
                    fulfillment_status = 'pending',
                    payment_status = 'unpaid',
                    updated_at = %s
                WHERE id = %s
                """,
                (now, order_id),
            )
        elif linked_result_count > 0:
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_orders
                SET state = CASE WHEN state = 'cancel' THEN 'draft' ELSE state END,
                    fulfillment_status = CASE
                        WHEN fulfillment_status IS NULL OR fulfillment_status = '' THEN 'pending'
                        ELSE fulfillment_status
                    END,
                    payment_status = CASE
                        WHEN state = 'cancel' THEN 'unpaid'
                        ELSE payment_status
                    END,
                    updated_at = %s
                WHERE id = %s
                """,
                (now, order_id),
            )
        _pg_recalc_sale_order_txn(cur, order_id)


def _sale_order_filter_sql(alias="so", session_id=None, q=None, order_source=None, status=None, placeholder="?"):
    clauses = []
    params = []
    if session_id:
        clauses.append(f"{alias}.session_id = {placeholder}")
        params.append(int(session_id))
    if order_source:
        normalized_source = (order_source or "whatnot").strip().lower()
        if normalized_source == "tiktok":
            like_pattern = "tiktok_%%" if placeholder == "%s" else "tiktok_%"
            clauses.append(f"LOWER(COALESCE({alias}.order_source, 'whatnot')) LIKE '{like_pattern}'")
        else:
            clauses.append(f"LOWER(COALESCE({alias}.order_source, 'whatnot')) = {placeholder}")
            params.append(normalized_source)
    if status:
        normalized_status = (status or "").strip().lower()
        if normalized_status == "pending":
            clauses.append(
                f"{alias}.state <> 'cancel' AND NOT ("
                f"LOWER(COALESCE({alias}.fulfillment_status, '')) = 'delivered' "
                f"OR LOWER(COALESCE({alias}.tracking_status, '')) = 'delivered' "
                f"OR COALESCE({alias}.delivered_at, '') <> '')"
            )
        elif normalized_status == "paid":
            clauses.append(f"{alias}.payment_status = 'paid' AND {alias}.state <> 'cancel'")
        elif normalized_status == "shipped":
            clauses.append(f"{alias}.fulfillment_status = 'shipped' AND {alias}.state <> 'cancel'")
        elif normalized_status in ("confirmed", "delivered"):
            clauses.append(
                f"{alias}.state <> 'cancel' AND ("
                f"LOWER(COALESCE({alias}.fulfillment_status, '')) = 'delivered' "
                f"OR LOWER(COALESCE({alias}.tracking_status, '')) = 'delivered' "
                f"OR COALESCE({alias}.delivered_at, '') <> '')"
            )
        elif normalized_status == "cancel":
            clauses.append(f"{alias}.state = 'cancel'")
        elif normalized_status in ("sale", "draft", "sent"):
            clauses.append(f"{alias}.state = {placeholder}")
            params.append(normalized_status)
    if q:
        ql = f"%{q.lower()}%"
        clauses.append(
            f"(LOWER({alias}.order_number) LIKE {placeholder} "
            f"OR LOWER(COALESCE({alias}.external_order_ref, '')) LIKE {placeholder} "
            f"OR LOWER(COALESCE({alias}.tracking_number, '')) LIKE {placeholder} "
            f"OR LOWER(COALESCE(c.display_name, '')) LIKE {placeholder} "
            f"OR LOWER(COALESCE({alias}.whatnot_buyer_username, '')) LIKE {placeholder} "
            f"OR LOWER(COALESCE({alias}.notes, '')) LIKE {placeholder})"
        )
        params.extend([ql, ql, ql, ql, ql, ql])
    return clauses, params


def _sale_order_summary_cache_key(session_id=None, q=None, order_source=None, status=None):
    return "sale_orders:summary:" + json.dumps({
        "session_id": int(session_id) if session_id else None,
        "q": str(q or "").strip().lower(),
        "order_source": str(order_source or "").strip().lower(),
        "status": str(status or "").strip().lower(),
    }, sort_keys=True, separators=(",", ":"))


def _cached_sale_order_summary_get(session_id=None, q=None, order_source=None, status=None):
    try:
        from .redis_sidecar import get_redis_sidecar
        return get_redis_sidecar().get_json(_sale_order_summary_cache_key(session_id, q, order_source, status))
    except Exception:
        return None


def _cached_sale_order_summary_set(value, session_id=None, q=None, order_source=None, status=None, ttl_sec=20):
    try:
        from .redis_sidecar import get_redis_sidecar
        get_redis_sidecar().set_json(
            _sale_order_summary_cache_key(session_id, q, order_source, status),
            value,
            ttl_sec=ttl_sec,
        )
    except Exception:
        pass


def list_sale_orders_fast(session_id=None, q=None, order_source=None, status=None, limit=250, offset=0):
    _require_company_postgres_runtime("company_orders")
    limit = max(1, min(int(limit or 250), 5000))
    offset = max(0, int(offset or 0))
    placeholder = "%s"
    clauses, params = _sale_order_filter_sql("so", session_id=session_id, q=q, order_source=order_source, status=status, placeholder=placeholder)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    query = f"""
        WITH page AS (
            SELECT so.id
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = so.customer_id
            {where_sql}
            ORDER BY COALESCE(so.ordered_at, so.created_at) DESC, so.id DESC
            LIMIT {placeholder} OFFSET {placeholder}
        ),
        line_metrics AS (
            SELECT
                sol.sale_order_id,
                COUNT(*) AS line_count,
                COALESCE(SUM(COALESCE(sol.qty, 0)), 0) AS line_qty,
                COALESCE(SUM(COALESCE(sol.subtotal, COALESCE(sol.qty, 0) * COALESCE(sol.unit_price, 0))), 0) AS line_revenue,
                COALESCE(SUM(COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0)), 0) AS line_cost,
                CASE
                    WHEN LOWER(COALESCE(so_lm.order_source, 'whatnot')) LIKE 'tiktok_%%'
                         AND MAX(tfr.sale_order_id) IS NOT NULL
                        THEN ABS(COALESCE(MAX(tfr.fee_amount), 0))
                    WHEN LOWER(COALESCE(so_lm.order_source, 'whatnot')) LIKE 'tiktok_%%'
                        THEN COALESCE(SUM(COALESCE(sol.subtotal, COALESCE(sol.qty, 0) * COALESCE(sol.unit_price, 0))), 0) * 0.06
                    ELSE 0
                END AS line_fees,
                COALESCE(SUM(COALESCE(sol.subtotal, COALESCE(sol.qty, 0) * COALESCE(sol.unit_price, 0))), 0)
                    - COALESCE(SUM(COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0)), 0)
                    - CASE
                        WHEN LOWER(COALESCE(so_lm.order_source, 'whatnot')) LIKE 'tiktok_%%'
                             AND MAX(tfr.sale_order_id) IS NOT NULL
                            THEN ABS(COALESCE(MAX(tfr.fee_amount), 0))
                        WHEN LOWER(COALESCE(so_lm.order_source, 'whatnot')) LIKE 'tiktok_%%'
                            THEN COALESCE(SUM(COALESCE(sol.subtotal, COALESCE(sol.qty, 0) * COALESCE(sol.unit_price, 0))), 0) * 0.06
                        ELSE 0
                    END AS line_profit,
                ABS(COALESCE(MAX(tfr.fee_amount), 0)) AS finance_fee_amount,
                CASE
                    WHEN MAX(tfr.sale_order_id) IS NOT NULL THEN 'settled'
                    WHEN LOWER(COALESCE(so_lm.order_source, 'whatnot')) LIKE 'tiktok_%%' THEN 'estimated_6pct'
                    ELSE ''
                END AS fee_source
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
            JOIN page ON page.id = sol.sale_order_id
            JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders so_lm ON so_lm.id = sol.sale_order_id
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.tiktok_finance_order_records tfr
              ON tfr.sale_order_id = sol.sale_order_id
             AND ABS(COALESCE(tfr.fee_amount, 0)) > 0
            GROUP BY sol.sale_order_id, so_lm.order_source
        ),
        linked_metrics AS (
            SELECT
                solx.sale_order_id,
                COUNT(DISTINCT ar.id) AS linked_results_count,
                COALESCE(SUM(ar.sale_price), 0) AS linked_revenue,
                COALESCE(SUM(ar.cost_price), 0) AS linked_cost,
                COALESCE(SUM(ar.fees), 0) AS linked_fees,
                COALESCE(SUM(ar.profit), 0) AS linked_profit,
                COALESCE(SUM(ar.products_sold_count), 0) AS linked_products_sold
            FROM (
                SELECT DISTINCT sol.sale_order_id, sol.auction_result_id
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                JOIN page ON page.id = sol.sale_order_id
                WHERE sol.auction_result_id IS NOT NULL
            ) solx
            JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
              ON ar.id = solx.auction_result_id
             AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
            GROUP BY solx.sale_order_id
        )
        SELECT
            so.id,
            so.order_number,
            so.session_id,
            so.customer_id,
            so.buyer_group_id,
            so.whatnot_buyer_username,
            so.order_source,
            so.external_order_ref,
            so.state,
            so.fulfillment_status,
            so.payment_status,
            so.tracking_number,
            so.packed_at,
            so.shipped_at,
            so.subtotal,
            so.total_amount,
            so.ordered_at,
            so.created_at,
            so.updated_at,
            cs.name AS session_name,
            c.display_name,
            c.whatnot_username,
            c.email AS customer_email,
            c.phone AS customer_phone,
            c.address AS customer_address,
            COALESCE(line_metrics.line_count, 0) AS line_count,
            COALESCE(line_metrics.line_qty, 0) AS line_qty,
            COALESCE(line_metrics.line_revenue, 0) AS line_revenue,
            COALESCE(line_metrics.line_cost, 0) AS line_cost,
            COALESCE(line_metrics.line_fees, 0) AS line_fees,
            COALESCE(line_metrics.line_profit, 0) AS line_profit,
            COALESCE(line_metrics.finance_fee_amount, 0) AS finance_fee_amount,
            COALESCE(line_metrics.fee_source, '') AS fee_source,
            COALESCE(linked_metrics.linked_results_count, 0) AS linked_results_count,
            CASE
                WHEN COALESCE(linked_metrics.linked_results_count, 0) > 0 THEN COALESCE(linked_metrics.linked_revenue, 0)
                ELSE COALESCE(line_metrics.line_revenue, 0)
            END AS linked_revenue,
            CASE
                WHEN COALESCE(linked_metrics.linked_results_count, 0) > 0 THEN COALESCE(linked_metrics.linked_cost, 0)
                ELSE COALESCE(line_metrics.line_cost, 0)
            END AS linked_cost,
            CASE
                WHEN COALESCE(linked_metrics.linked_results_count, 0) > 0 THEN COALESCE(linked_metrics.linked_fees, 0)
                ELSE COALESCE(line_metrics.line_fees, 0)
            END AS linked_fees,
            CASE
                WHEN COALESCE(linked_metrics.linked_results_count, 0) > 0 THEN COALESCE(linked_metrics.linked_fees, 0)
                ELSE COALESCE(line_metrics.line_fees, 0)
            END AS order_fees,
            CASE
                WHEN COALESCE(linked_metrics.linked_results_count, 0) > 0 THEN COALESCE(linked_metrics.linked_profit, 0)
                ELSE COALESCE(line_metrics.line_profit, 0)
            END AS linked_profit,
            COALESCE(linked_metrics.linked_products_sold, 0) AS linked_products_sold
        FROM page
        JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders so ON so.id = page.id
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = so.session_id
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = so.customer_id
        LEFT JOIN line_metrics ON line_metrics.sale_order_id = so.id
        LEFT JOIN linked_metrics ON linked_metrics.sale_order_id = so.id
        ORDER BY COALESCE(so.ordered_at, so.created_at) DESC, so.id DESC
    """
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params + [limit, offset]))
            return _pg_fetchall_dict(cur)


def sale_order_list_summary(session_id=None, q=None, order_source=None, status=None):
    _require_company_postgres_runtime("company_orders")
    cached = _cached_sale_order_summary_get(session_id=session_id, q=q, order_source=order_source, status=status)
    if isinstance(cached, dict):
        return cached

    def _summary_from_row(row):
        row = row or {}
        return {
            "total_count": int(row.get("total_count") or 0),
            "total_amount": round(float(row.get("total_amount") or 0), 2),
            "confirmed_count": int(row.get("confirmed_count") or 0),
            "draft_count": int(row.get("draft_count") or 0),
            "cancel_count": int(row.get("cancel_count") or 0),
            "pending_count": int(row.get("pending_count") or 0),
            "packed_count": int(row.get("packed_count") or 0),
            "shipped_count": int(row.get("shipped_count") or 0),
            "paid_count": int(row.get("paid_count") or 0),
            "confirmed_amount": round(float(row.get("confirmed_amount") or 0), 2),
            "draft_amount": round(float(row.get("draft_amount") or 0), 2),
            "cancel_amount": round(float(row.get("cancel_amount") or 0), 2),
        }
    placeholder = "%s"
    clauses, params = _sale_order_filter_sql("so", session_id=session_id, q=q, order_source=order_source, status=status, placeholder=placeholder)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    query = f"""
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(COALESCE(so.total_amount, 0)), 0) AS total_amount,
            SUM(CASE WHEN so.state <> 'cancel' AND (LOWER(COALESCE(so.fulfillment_status, '')) = 'delivered' OR LOWER(COALESCE(so.tracking_status, '')) = 'delivered' OR COALESCE(so.delivered_at, '') <> '') THEN 1 ELSE 0 END) AS confirmed_count,
            SUM(CASE WHEN so.state IN ('draft', 'sent') THEN 1 ELSE 0 END) AS draft_count,
            SUM(CASE WHEN so.state = 'cancel' THEN 1 ELSE 0 END) AS cancel_count,
            SUM(CASE WHEN so.state <> 'cancel' AND NOT (LOWER(COALESCE(so.fulfillment_status, '')) = 'delivered' OR LOWER(COALESCE(so.tracking_status, '')) = 'delivered' OR COALESCE(so.delivered_at, '') <> '') THEN 1 ELSE 0 END) AS pending_count,
            SUM(CASE WHEN so.fulfillment_status = 'packed' THEN 1 ELSE 0 END) AS packed_count,
            SUM(CASE WHEN so.fulfillment_status = 'shipped' THEN 1 ELSE 0 END) AS shipped_count,
            SUM(CASE WHEN so.payment_status = 'paid' THEN 1 ELSE 0 END) AS paid_count,
            COALESCE(SUM(CASE WHEN so.state <> 'cancel' AND (LOWER(COALESCE(so.fulfillment_status, '')) = 'delivered' OR LOWER(COALESCE(so.tracking_status, '')) = 'delivered' OR COALESCE(so.delivered_at, '') <> '') THEN COALESCE(so.total_amount, 0) ELSE 0 END), 0) AS confirmed_amount,
            COALESCE(SUM(CASE WHEN so.state IN ('draft', 'sent') THEN COALESCE(so.total_amount, 0) ELSE 0 END), 0) AS draft_amount,
            COALESCE(SUM(CASE WHEN so.state = 'cancel' THEN COALESCE(so.total_amount, 0) ELSE 0 END), 0) AS cancel_amount
        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = so.customer_id
        {where_sql}
    """
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = _pg_fetchall_dict(cur)
            result = _summary_from_row(rows[0] if rows else None)
    _cached_sale_order_summary_set(result, session_id=session_id, q=q, order_source=order_source, status=status)
    return result


def list_sale_orders(session_id=None, q=None, order_source=None):
    _require_company_postgres_runtime("company_orders")
    query = """
        SELECT so.*, cs.name AS session_name, c.display_name, c.whatnot_username
             , c.email AS customer_email, c.phone AS customer_phone, c.address AS customer_address
             , COALESCE(metrics.linked_results_count, 0) AS linked_results_count
             , COALESCE(metrics.linked_revenue, 0) AS linked_revenue
             , COALESCE(metrics.linked_cost, 0) AS linked_cost
             , COALESCE(metrics.linked_fees, 0) AS linked_fees
             , COALESCE(metrics.linked_profit, 0) AS linked_profit
             , COALESCE(metrics.linked_products_sold, 0) AS linked_products_sold
             , (
                SELECT COUNT(*)
                FROM sale_order_lines sol
                WHERE sol.sale_order_id = so.id
               ) AS line_count
             , (
                SELECT COALESCE(SUM(COALESCE(sol.qty, 0)), 0)
                FROM sale_order_lines sol
                WHERE sol.sale_order_id = so.id
               ) AS line_qty
             , (
                SELECT COALESCE(SUM(
                    COALESCE(sol.subtotal, COALESCE(sol.qty, 0) * COALESCE(sol.unit_price, 0))
                    - (COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0))
                ), 0)
                FROM sale_order_lines sol
                LEFT JOIN products p ON p.id = sol.product_id
                WHERE sol.sale_order_id = so.id
               ) AS line_profit
             , CASE
                WHEN COALESCE(metrics.linked_revenue, 0) > 0
                    THEN ROUND(CAST((COALESCE(metrics.linked_profit, 0) / metrics.linked_revenue) * 100.0 AS NUMERIC), 1)
                ELSE 0
               END AS linked_margin_pct
                 , (
                    SELECT COALESCE(sol.description, p.name)
                    FROM sale_order_lines sol
                    LEFT JOIN products p ON p.id = sol.product_id
                    WHERE sol.sale_order_id = so.id
                    ORDER BY sol.id ASC
                    LIMIT 1
                   ) AS first_product_name
                 , (
                    SELECT GROUP_CONCAT(lot_value, ', ')
                    FROM (
                        SELECT DISTINCT
                            COALESCE(
                                NULLIF(TRIM(ar.lot_number), ''),
                                CASE
                                    WHEN sol.lot_id IS NOT NULL THEN CAST(sol.lot_id AS TEXT)
                                    ELSE NULL
                                END
                            ) AS lot_value
                        FROM sale_order_lines sol
                        LEFT JOIN auction_results ar ON ar.id = sol.auction_result_id
                        WHERE sol.sale_order_id = so.id
                          AND COALESCE(
                                NULLIF(TRIM(ar.lot_number), ''),
                                CASE
                                    WHEN sol.lot_id IS NOT NULL THEN CAST(sol.lot_id AS TEXT)
                                    ELSE NULL
                                END
                              ) IS NOT NULL
                        ORDER BY
                            CAST(
                                COALESCE(
                                    NULLIF(TRIM(ar.lot_number), ''),
                                    CASE
                                        WHEN sol.lot_id IS NOT NULL THEN CAST(sol.lot_id AS TEXT)
                                        ELSE NULL
                                    END
                                ) AS INTEGER
                            ),
                            COALESCE(
                                NULLIF(TRIM(ar.lot_number), ''),
                                CASE
                                    WHEN sol.lot_id IS NOT NULL THEN CAST(sol.lot_id AS TEXT)
                                    ELSE NULL
                                END
                            )
                    )
                   ) AS linked_lot_numbers
        FROM sale_orders so
        LEFT JOIN company_sessions cs ON cs.id = so.session_id
        LEFT JOIN customers c ON c.id = so.customer_id
        LEFT JOIN (
            """ + _sale_order_metrics_subquery() + """
        ) metrics ON metrics.sale_order_id = so.id
        WHERE 1=1
    """
    params = []
    pg_query = f"""
            SELECT so.*, cs.name AS session_name, c.display_name, c.whatnot_username
                 , c.email AS customer_email, c.phone AS customer_phone, c.address AS customer_address
                 , COALESCE(metrics.linked_results_count, 0) AS linked_results_count
                 , COALESCE(metrics.linked_revenue, 0) AS linked_revenue
                 , COALESCE(metrics.linked_cost, 0) AS linked_cost
                 , COALESCE(metrics.linked_fees, 0) AS linked_fees
                 , COALESCE(metrics.linked_profit, 0) AS linked_profit
                 , COALESCE(metrics.linked_products_sold, 0) AS linked_products_sold
                 , (
                    SELECT COUNT(*)
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                    WHERE sol.sale_order_id = so.id
                   ) AS line_count
                 , (
                    SELECT COALESCE(SUM(COALESCE(sol.qty, 0)), 0)
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                    WHERE sol.sale_order_id = so.id
                   ) AS line_qty
                 , COALESCE(ABS(tfr.fee_amount), 0) AS finance_fee_amount
                 , CASE
                    WHEN tfr.sale_order_id IS NOT NULL THEN 'settled'
                    WHEN LOWER(COALESCE(so.order_source, 'whatnot')) LIKE 'tiktok_%%' THEN 'estimated_6pct'
                    ELSE ''
                   END AS fee_source
                 , (
                    SELECT COALESCE(SUM(
                        COALESCE(sol.subtotal, COALESCE(sol.qty, 0) * COALESCE(sol.unit_price, 0))
                        - (COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0))
                    ), 0)
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                    WHERE sol.sale_order_id = so.id
                   ) - CASE
                    WHEN LOWER(COALESCE(so.order_source, 'whatnot')) LIKE 'tiktok_%%'
                         AND tfr.sale_order_id IS NOT NULL
                        THEN COALESCE(ABS(tfr.fee_amount), 0)
                    WHEN LOWER(COALESCE(so.order_source, 'whatnot')) LIKE 'tiktok_%%'
                        THEN (
                            SELECT COALESCE(SUM(COALESCE(sol_fee.subtotal, COALESCE(sol_fee.qty, 0) * COALESCE(sol_fee.unit_price, 0))), 0) * 0.06
                            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol_fee
                            WHERE sol_fee.sale_order_id = so.id
                        )
                    ELSE 0
                   END AS line_profit
                 , CASE
                    WHEN COALESCE(metrics.linked_revenue, 0) > 0
                        THEN ROUND(CAST((COALESCE(metrics.linked_profit, 0) / metrics.linked_revenue) * 100.0 AS NUMERIC), 1)
                    ELSE 0
                   END AS linked_margin_pct
                 , (
                    SELECT COALESCE(sol.description, p.name)
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                    WHERE sol.sale_order_id = so.id
                    ORDER BY sol.id ASC
                    LIMIT 1
                   ) AS first_product_name
                 , (
                    SELECT STRING_AGG(lot_value, ', ')
                    FROM (
                        SELECT DISTINCT
                            COALESCE(
                                NULLIF(TRIM(ar.lot_number), ''),
                                CASE
                                    WHEN sol.lot_id IS NOT NULL THEN CAST(sol.lot_id AS TEXT)
                                    ELSE NULL
                                END
                            ) AS lot_value
                        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar ON ar.id = sol.auction_result_id
                        WHERE sol.sale_order_id = so.id
                          AND COALESCE(
                                NULLIF(TRIM(ar.lot_number), ''),
                                CASE
                                    WHEN sol.lot_id IS NOT NULL THEN CAST(sol.lot_id AS TEXT)
                                    ELSE NULL
                                END
                              ) IS NOT NULL
                    ) lots
                   ) AS linked_lot_numbers
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = so.session_id
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = so.customer_id
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.tiktok_finance_order_records tfr
              ON tfr.sale_order_id = so.id
             AND ABS(COALESCE(tfr.fee_amount, 0)) > 0
            LEFT JOIN (
                SELECT
                    sox.id AS sale_order_id,
                    COUNT(DISTINCT ar.id) AS linked_results_count,
                    COALESCE(SUM(ar.sale_price), 0) AS linked_revenue,
                    COALESCE(SUM(ar.cost_price), 0) AS linked_cost,
                    COALESCE(SUM(ar.fees), 0) AS linked_fees,
                    COALESCE(SUM(ar.profit), 0) AS linked_profit,
                    COALESCE(SUM(ar.products_sold_count), 0) AS linked_products_sold
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders sox
                LEFT JOIN (
                    SELECT DISTINCT sale_order_id, auction_result_id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                    WHERE auction_result_id IS NOT NULL
                ) solx ON solx.sale_order_id = sox.id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
                  ON ar.id = solx.auction_result_id
                 AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
                GROUP BY sox.id
            ) metrics ON metrics.sale_order_id = so.id
            WHERE 1=1
        """
    if session_id:
        pg_query += " AND so.session_id = %s"
        params.append(int(session_id))
    if order_source:
        normalized_source = (order_source or "whatnot").strip().lower()
        if normalized_source == "tiktok":
            pg_query += " AND LOWER(COALESCE(so.order_source, 'whatnot')) LIKE 'tiktok_%%'"
        else:
            pg_query += " AND LOWER(COALESCE(so.order_source, 'whatnot')) = %s"
            params.append(normalized_source)
    if q:
        ql = f"%{q.lower()}%"
        pg_query += " AND (LOWER(so.order_number) LIKE %s OR LOWER(COALESCE(so.external_order_ref, '')) LIKE %s OR LOWER(COALESCE(c.display_name, '')) LIKE %s OR LOWER(COALESCE(so.whatnot_buyer_username, '')) LIKE %s OR LOWER(COALESCE(so.notes, '')) LIKE %s)"
        params.extend([ql, ql, ql, ql, ql])
    pg_query += " ORDER BY COALESCE(so.ordered_at, so.created_at) DESC, so.id DESC"
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(pg_query, tuple(params))
            return _pg_fetchall_dict(cur)


def get_sale_order(order_id):
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT so.*, cs.name AS session_name, c.display_name, c.whatnot_username
                     , c.email AS customer_email, c.phone AS customer_phone, c.address AS customer_address
                     , COALESCE(metrics.linked_results_count, 0) AS linked_results_count
                     , COALESCE(metrics.linked_revenue, 0) AS linked_revenue
                     , COALESCE(metrics.linked_cost, 0) AS linked_cost
                     , COALESCE(metrics.linked_fees, 0) AS linked_fees
                     , COALESCE(metrics.linked_profit, 0) AS linked_profit
                     , COALESCE(metrics.linked_products_sold, 0) AS linked_products_sold
                     , CASE
                        WHEN COALESCE(metrics.linked_revenue, 0) > 0
                            THEN ROUND(CAST((COALESCE(metrics.linked_profit, 0) / metrics.linked_revenue) * 100.0 AS NUMERIC), 1)
                        ELSE 0
                       END AS linked_margin_pct
                     , (
                        SELECT COALESCE(sol.description, p.name)
                        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                        WHERE sol.sale_order_id = so.id
                        ORDER BY sol.id ASC
                        LIMIT 1
                       ) AS first_product_name
                     , (
                        SELECT STRING_AGG(lot_value, ', ')
                        FROM (
                            SELECT DISTINCT
                                COALESCE(
                                    NULLIF(TRIM(ar.lot_number), ''),
                                    CASE
                                        WHEN sol.lot_id IS NOT NULL THEN CAST(sol.lot_id AS TEXT)
                                        ELSE NULL
                                    END
                                ) AS lot_value
                            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar ON ar.id = sol.auction_result_id
                            WHERE sol.sale_order_id = so.id
                              AND COALESCE(
                                    NULLIF(TRIM(ar.lot_number), ''),
                                    CASE
                                        WHEN sol.lot_id IS NOT NULL THEN CAST(sol.lot_id AS TEXT)
                                        ELSE NULL
                                    END
                                  ) IS NOT NULL
                        ) lots
                       ) AS linked_lot_numbers
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = so.session_id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = so.customer_id
                LEFT JOIN (
                    SELECT
                        sox.id AS sale_order_id,
                        COUNT(DISTINCT ar.id) AS linked_results_count,
                        COALESCE(SUM(ar.sale_price), 0) AS linked_revenue,
                        COALESCE(SUM(ar.cost_price), 0) AS linked_cost,
                        COALESCE(SUM(ar.fees), 0) AS linked_fees,
                        COALESCE(SUM(ar.profit), 0) AS linked_profit,
                        COALESCE(SUM(ar.products_sold_count), 0) AS linked_products_sold
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders sox
                    LEFT JOIN (
                        SELECT DISTINCT sale_order_id, auction_result_id
                        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                        WHERE auction_result_id IS NOT NULL
                    ) solx ON solx.sale_order_id = sox.id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
                      ON ar.id = solx.auction_result_id
                     AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
                    GROUP BY sox.id
                ) metrics ON metrics.sale_order_id = so.id
                WHERE so.id = %s
                """,
                (int(order_id),),
            )
            return _pg_fetchone_dict(cur)


def list_sale_order_lines(order_id):
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    sol.*,
                    p.name AS product_name,
                    p.barcode AS barcode,
                    p.sku AS sku,
                    p.cost_price AS unit_cost,
                    p.retail_price AS retail_price,
                    p.on_hand_qty,
                    ar.lot_number,
                    ar.sold_at,
                    ar.winner_username AS buyer_username,
                    ar.product_name AS buyer_line_product_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar ON ar.id = sol.auction_result_id
                WHERE sol.sale_order_id = %s
                ORDER BY sol.id ASC
                """,
                (int(order_id),),
            )
            return _pg_fetchall_dict(cur)


def list_sale_order_lines_bulk(order_ids):
    _require_company_postgres_runtime("company_orders")
    normalized_ids = sorted({int(value) for value in (order_ids or []) if value is not None})
    if not normalized_ids:
        return []
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    sol.*,
                    p.name AS product_name,
                    p.brand AS brand,
                    p.barcode AS barcode,
                    p.sku AS sku,
                    p.cost_price AS unit_cost,
                    p.retail_price AS retail_price,
                    p.on_hand_qty,
                    ar.lot_number,
                    ar.sold_at,
                    ar.winner_username AS buyer_username,
                    ar.product_name AS buyer_line_product_name
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar ON ar.id = sol.auction_result_id
                WHERE sol.sale_order_id = ANY(%s)
                ORDER BY sol.sale_order_id ASC, sol.id ASC
                """,
                (list(normalized_ids),),
            )
            return _pg_fetchall_dict(cur)


def get_sale_order_line(line_id):
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                WHERE id = %s
                """,
                (int(line_id),),
            )
            return _pg_fetchone_dict(cur)


def update_sale_order(order_id, **fields):
    _require_company_postgres_runtime("company_orders")
    allowed = {
        "customer_id", "whatnot_buyer_username", "state", "notes", "ordered_at",
        "order_source", "external_order_ref", "session_id",
        "fulfillment_status", "payment_status", "tracking_number", "tracking_carrier",
        "tracking_status", "tracking_status_detail", "tracking_last_checked_at",
        "packed_at", "shipped_at", "delivered_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_sale_order(order_id)
    if "tracking_carrier" in updates and not updates["tracking_carrier"]:
        updates["tracking_carrier"] = "usps"
    updates["updated_at"] = utc_now()
    try:
        with pg_domain_tx("company_orders", "sale_orders_update") as (_pg_conn, cur):
            cur.execute(
                f"SELECT session_id, buyer_group_id FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders WHERE id = %s",
                (int(order_id),),
            )
            current = _pg_fetchone_dict(cur)
            if not current:
                return None
            assignments = ", ".join(f"{key} = %s" for key in updates)
            params = list(updates.values()) + [int(order_id)]
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_orders SET {assignments} WHERE id = %s RETURNING *",
                params,
            )
            updated = _pg_fetchone_dict(cur)
            old_session_id = int(current["session_id"]) if current.get("session_id") else None
            new_session_id = int(updated["session_id"]) if updated and updated.get("session_id") else None
        _sync_sale_order_inventory_state(int(order_id))
        for session_id in {old_session_id, new_session_id}:
            if session_id:
                _recalc_session_totals(session_id)
        return get_sale_order(order_id)
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "sale_orders", order_id, {"error": str(exc)})
        raise


def bulk_update_sale_orders(order_ids, **fields):
    _require_company_postgres_runtime("company_orders")
    allowed = {
        "state", "fulfillment_status", "payment_status", "tracking_number",
        "tracking_carrier", "tracking_status", "tracking_status_detail",
        "tracking_last_checked_at", "packed_at", "shipped_at", "delivered_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    ids = [int(order_id) for order_id in (order_ids or [])]
    if not ids or not updates:
        return []
    if "tracking_carrier" in updates and not updates["tracking_carrier"]:
        updates["tracking_carrier"] = "usps"
    updates["updated_at"] = utc_now()
    try:
        with pg_domain_tx("company_orders", "sale_orders_bulk_update") as (_pg_conn, cur):
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"""
                SELECT DISTINCT session_id
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders
                WHERE id IN ({placeholders}) AND session_id IS NOT NULL
                """,
                tuple(ids),
            )
            session_rows = [int(row[0]) for row in cur.fetchall() if row and row[0] is not None]
            assignments = ", ".join(f"{key} = %s" for key in updates)
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_orders SET {assignments} WHERE id IN ({placeholders})",
                tuple(list(updates.values()) + ids),
            )
        for order_id in ids:
            _sync_sale_order_inventory_state(order_id)
        for session_id in session_rows:
            _recalc_session_totals(session_id)
        refreshed = [get_sale_order(order_id) for order_id in ids]
        refreshed = [row for row in refreshed if row]
        refreshed.sort(key=lambda row: ((row.get("ordered_at") or row.get("created_at") or ""), row.get("id") or 0), reverse=True)
        return refreshed
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "sale_orders_bulk", ids, {"error": str(exc)})
        raise


def update_sale_order_line(line_id, **fields):
    _require_company_postgres_runtime("company_orders")
    allowed = {"product_id", "description", "qty", "unit_price", "inventory_applied"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    existing = get_sale_order_line(line_id)
    if not existing:
        return None
    if "qty" in updates:
        updates["qty"] = float(updates["qty"] or 0)
    if "unit_price" in updates:
        updates["unit_price"] = float(updates["unit_price"] or 0)
    if "inventory_applied" in updates:
        requested_inventory_applied = 1 if updates["inventory_applied"] else 0
        if requested_inventory_applied != int(existing.get("inventory_applied") or 0):
            raise ValueError("Direct inventory_applied edits are blocked. Use the order apply/cancel flow instead.")
        updates["inventory_applied"] = requested_inventory_applied
    if "product_id" in updates:
        old_product_id = int(existing.get("product_id") or 0)
        new_product_id = int(updates.get("product_id") or 0)
        if old_product_id and old_product_id != new_product_id and int(existing.get("inventory_applied") or 0):
            raise ValueError("Applied inventory line product changes must use the lot replacement flow.")
    if "qty" in updates or "unit_price" in updates:
        qty = updates.get("qty")
        unit_price = updates.get("unit_price")
        qty = existing["qty"] if qty is None else qty
        unit_price = existing["unit_price"] if unit_price is None else unit_price
        updates["subtotal"] = float(qty or 0) * float(unit_price or 0)
    if not updates:
        return get_sale_order_line(line_id)
    updates["updated_at"] = utc_now()
    try:
        with pg_domain_tx("company_orders", "sale_order_lines_update") as (_pg_conn, cur):
            cur.execute(
                f"SELECT sale_order_id FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines WHERE id = %s",
                (int(line_id),),
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                return None
            assignments = ", ".join(f"{key} = %s" for key in updates)
            params = list(updates.values()) + [int(line_id)]
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines SET {assignments} WHERE id = %s RETURNING *",
                params,
            )
            _pg_fetchone_dict(cur)
            sale_order_id = int(row["sale_order_id"])
            _pg_recalc_sale_order_txn(cur, sale_order_id)
        return get_sale_order_line(line_id)
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "sale_order_lines_update", line_id, {"error": str(exc)})
        raise


def delete_sale_order_line(line_id):
    _require_company_postgres_runtime("company_orders")
    existing = get_sale_order_line(line_id)
    if existing and int(existing.get("inventory_applied") or 0):
        raise ValueError("Cannot delete a line with applied inventory. Reverse the order inventory first.")
    try:
        with pg_domain_tx("company_orders", "sale_order_lines_delete") as (_pg_conn, cur):
            cur.execute(
                f"SELECT sale_order_id FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines WHERE id = %s",
                (int(line_id),),
            )
            row = _pg_fetchone_dict(cur)
            if not row:
                return False
            sale_order_id = int(row["sale_order_id"])
            cur.execute(
                f"DELETE FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines WHERE id = %s",
                (int(line_id),),
            )
            _pg_recalc_sale_order_txn(cur, sale_order_id)
        return True
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "sale_order_lines_delete", line_id, {"error": str(exc)})
        raise


def list_customers(q=None, has_orders_only=False, platform=None, limit=None, offset=0):
    _require_company_postgres_runtime("company_customers")
    pg_query = """
        SELECT
            c.*,
            (SELECT ci.username FROM {schema}.customer_identities ci WHERE ci.customer_id = c.id AND LOWER(COALESCE(ci.platform, '')) = 'whatnot' ORDER BY ci.id ASC LIMIT 1) AS whatnot_identity,
            (SELECT ci.username FROM {schema}.customer_identities ci WHERE ci.customer_id = c.id AND LOWER(COALESCE(ci.platform, '')) = 'tiktok_live' ORDER BY ci.id ASC LIMIT 1) AS tiktok_live_identity,
            (SELECT ci.username FROM {schema}.customer_identities ci WHERE ci.customer_id = c.id AND LOWER(COALESCE(ci.platform, '')) = 'tiktok_shop' ORDER BY ci.id ASC LIMIT 1) AS tiktok_shop_identity,
            (SELECT COUNT(*) FROM {schema}.customer_identities ci WHERE ci.customer_id = c.id) AS identity_count,
            (SELECT STRING_AGG(DISTINCT ci.platform, ', ') FROM {schema}.customer_identities ci WHERE ci.customer_id = c.id) AS platforms,
            (SELECT COUNT(*) FROM {schema}.sale_orders so WHERE so.customer_id = c.id) AS sale_order_count,
            (SELECT COUNT(DISTINCT so.session_id) FROM {schema}.sale_orders so WHERE so.customer_id = c.id) AS session_count,
            (SELECT COALESCE(SUM(so.total_amount), 0) FROM {schema}.sale_orders so WHERE so.customer_id = c.id) AS total_spent,
            (SELECT COALESCE(SUM(ar.profit), 0) FROM {schema}.auction_results ar WHERE ar.customer_id = c.id AND {canon}) AS total_profit,
            (SELECT COALESCE(SUM(ar.sale_price), 0) FROM {schema}.auction_results ar WHERE ar.customer_id = c.id AND {canon}) AS total_revenue,
            (SELECT COUNT(*) FROM {schema}.auction_results ar WHERE ar.customer_id = c.id AND {canon}) AS purchase_count,
            0 AS review_count,
            0 AS avg_review_rating,
            (
              SELECT MAX(ts)
              FROM (
                SELECT COALESCE(so.ordered_at, so.created_at) AS ts FROM {schema}.sale_orders so WHERE so.customer_id = c.id
                UNION ALL
                SELECT ar.sold_at AS ts FROM {schema}.auction_results ar WHERE ar.customer_id = c.id AND {canon}
              ) recent
            ) AS last_purchase_at
        FROM {schema}.customers c
        WHERE 1=1
    """.format(schema=POSTGRES_SIDECAR_SCHEMA, canon=_PG_CANONICAL_AUCTION_RESULT_FILTER)
    pg_params = []
    if has_orders_only:
        pg_query += """
            AND (
                EXISTS (SELECT 1 FROM {schema}.sale_orders so WHERE so.customer_id = c.id)
                OR EXISTS (
                    SELECT 1
                    FROM {schema}.auction_results ar
                    WHERE ar.customer_id = c.id
                      AND {canon}
                )
            )
        """.format(schema=POSTGRES_SIDECAR_SCHEMA, canon=_PG_CANONICAL_AUCTION_RESULT_FILTER)
    if q:
        ql = f"%{q.lower()}%"
        pg_query += """
            AND (
                LOWER(COALESCE(c.display_name, '')) LIKE %s
                OR LOWER(COALESCE(c.whatnot_username, '')) LIKE %s
                OR LOWER(COALESCE(c.email, '')) LIKE %s
                OR LOWER(COALESCE(c.phone, '')) LIKE %s
                OR LOWER(COALESCE(c.address, '')) LIKE %s
                OR EXISTS (
                    SELECT 1
                    FROM {schema}.customer_identities ci
                    WHERE ci.customer_id = c.id
                      AND (
                        LOWER(COALESCE(ci.username, '')) LIKE %s
                        OR LOWER(COALESCE(ci.platform_user_id, '')) LIKE %s
                        OR LOWER(COALESCE(ci.email, '')) LIKE %s
                        OR LOWER(COALESCE(ci.phone, '')) LIKE %s
                      )
                )
            )
        """.format(schema=POSTGRES_SIDECAR_SCHEMA)
        pg_params.extend([ql, ql, ql, ql, ql, ql, ql, ql, ql])
    if platform and str(platform).strip().lower() != "all":
        pg_query += """
            AND EXISTS (
                SELECT 1
                FROM {schema}.customer_identities ci
                WHERE ci.customer_id = c.id
                  AND LOWER(COALESCE(ci.platform, '')) = %s
            )
        """.format(schema=POSTGRES_SIDECAR_SCHEMA)
        pg_params.append(str(platform).strip().lower())
    pg_query += " ORDER BY COALESCE(c.display_name, c.whatnot_username) ASC"
    if limit is not None:
        pg_query += " LIMIT %s OFFSET %s"
        pg_params.extend([max(1, int(limit or 100)), max(0, int(offset or 0))])
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(pg_query, tuple(pg_params))
            return _pg_fetchall_dict(cur)


def get_customer(customer_id):
    _require_company_postgres_runtime("company_customers")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    c.*,
                    (SELECT ci.username FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities ci WHERE ci.customer_id = c.id AND LOWER(COALESCE(ci.platform, '')) = 'whatnot' ORDER BY ci.id ASC LIMIT 1) AS whatnot_identity,
                    (SELECT ci.username FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities ci WHERE ci.customer_id = c.id AND LOWER(COALESCE(ci.platform, '')) = 'tiktok_live' ORDER BY ci.id ASC LIMIT 1) AS tiktok_live_identity,
                    (SELECT ci.username FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities ci WHERE ci.customer_id = c.id AND LOWER(COALESCE(ci.platform, '')) = 'tiktok_shop' ORDER BY ci.id ASC LIMIT 1) AS tiktok_shop_identity,
                    (SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities ci WHERE ci.customer_id = c.id) AS identity_count,
                    (SELECT STRING_AGG(DISTINCT ci.platform, ', ') FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities ci WHERE ci.customer_id = c.id) AS platforms,
                    (SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so WHERE so.customer_id = c.id) AS sale_order_count,
                    (SELECT COUNT(DISTINCT so.session_id) FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so WHERE so.customer_id = c.id) AS session_count,
                    (SELECT COALESCE(SUM(so.total_amount), 0) FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so WHERE so.customer_id = c.id) AS total_spent,
                    (SELECT COALESCE(SUM(ar.profit), 0) FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar WHERE ar.customer_id = c.id AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}) AS total_profit,
                    (SELECT COALESCE(SUM(ar.sale_price), 0) FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar WHERE ar.customer_id = c.id AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}) AS total_revenue,
                    (SELECT COUNT(*) FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar WHERE ar.customer_id = c.id AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}) AS purchase_count,
                    0 AS review_count,
                    0 AS avg_review_rating,
                    (
                      SELECT MAX(ts)
                      FROM (
                        SELECT COALESCE(so.ordered_at, so.created_at) AS ts FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so WHERE so.customer_id = c.id
                        UNION ALL
                        SELECT ar.sold_at AS ts FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar WHERE ar.customer_id = c.id AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
                      ) recent
                    ) AS last_purchase_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.customers c
                WHERE c.id = %s
                """,
                (int(customer_id),),
            )
            return _pg_fetchone_dict(cur)


def get_customer_by_username(username):
    _require_company_postgres_runtime("company_customers")
    uname = str(username or "").strip().lstrip("@").lower()
    if not uname:
        return None
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities
                WHERE LOWER(COALESCE(username, '')) = %s
                   OR LOWER(COALESCE(platform_user_id, '')) = %s
                ORDER BY
                    CASE LOWER(COALESCE(platform, ''))
                        WHEN 'whatnot' THEN 1
                        WHEN 'tiktok_live' THEN 2
                        WHEN 'tiktok_shop' THEN 3
                        ELSE 9
                    END,
                    id ASC
                LIMIT 1
                """,
                (uname, uname),
            )
            identity = _pg_fetchone_dict(cur)
    if identity and identity.get("customer_id"):
        return get_customer(int(identity["customer_id"]))
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id
                FROM {POSTGRES_SIDECAR_SCHEMA}.customers
                WHERE LOWER(COALESCE(whatnot_username, '')) = %s
                LIMIT 1
                """,
                (uname,),
            )
            row = _pg_fetchone_dict(cur)
            return get_customer(int(row["id"])) if row and row.get("id") else None


def update_customer(customer_id, **fields):
    _require_company_postgres_runtime("company_customers")
    allowed = {"display_name", "email", "phone", "address", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_customer(customer_id)
    updates["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    params = list(updates.values()) + [int(customer_id)]
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.customers SET {assignments.replace('?', '%s')} WHERE id = %s",
                params,
            )
        conn.commit()
    return get_customer(customer_id)


def list_customer_orders(customer_id):
    _require_company_postgres_runtime("company_customers")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    so.*,
                    cs.name AS session_name,
                    COALESCE(lines.line_count, 0) AS line_count,
                    lines.product_names,
                    COALESCE(order_results.order_profit, line_results.order_profit, 0) AS order_profit,
                    COALESCE(order_results.order_revenue, line_results.order_revenue, 0) AS order_revenue
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
                LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = so.session_id
                LEFT JOIN (
                    SELECT
                        sol.sale_order_id,
                        COUNT(DISTINCT sol.id) AS line_count,
                        STRING_AGG(DISTINCT COALESCE(sol.description, p.name), ', ') AS product_names
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                    GROUP BY sol.sale_order_id
                ) AS lines ON lines.sale_order_id = so.id
                LEFT JOIN (
                    SELECT
                        refs.sale_order_id,
                        COALESCE(SUM(ar.profit), 0) AS order_profit,
                        COALESCE(SUM(ar.sale_price), 0) AS order_revenue
                    FROM (
                        SELECT DISTINCT sale_order_id, auction_result_id
                        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                        WHERE auction_result_id IS NOT NULL
                    ) AS refs
                        JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar ON ar.id = refs.auction_result_id AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
                    GROUP BY refs.sale_order_id
                ) AS order_results ON order_results.sale_order_id = so.id
                LEFT JOIN (
                    SELECT
                        sol.sale_order_id,
                        COALESCE(SUM(sol.subtotal), 0) AS order_revenue,
                        COALESCE(SUM(sol.subtotal - (COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0))), 0) AS order_profit
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                    GROUP BY sol.sale_order_id
                ) AS line_results ON line_results.sale_order_id = so.id
                WHERE so.customer_id = %s
                ORDER BY COALESCE(so.ordered_at, so.created_at) DESC
                """,
                (int(customer_id),),
            )
            return _pg_fetchall_dict(cur)


def get_customer_analytics(customer_id):
    _require_company_postgres_runtime("company_customers")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT platform, platform_user_id, username, display_name, email, phone, created_at, updated_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.customer_identities
                    WHERE customer_id = %s
                    ORDER BY
                        CASE LOWER(COALESCE(platform, ''))
                            WHEN 'whatnot' THEN 1
                            WHEN 'tiktok_live' THEN 2
                            WHEN 'tiktok_shop' THEN 3
                            ELSE 9
                        END,
                        LOWER(COALESCE(username, platform_user_id, ''))
                    """,
                    (int(customer_id),),
                )
                identities = _pg_fetchall_dict(cur)
                cur.execute(
                    f"""
                    SELECT
                        cs.id,
                        cs.name AS session_name,
                        COUNT(DISTINCT ar.id) AS purchase_count,
                        COALESCE(SUM(ar.sale_price), 0) AS total_revenue,
                        COALESCE(SUM(ar.profit), 0) AS total_profit,
                        MAX(ar.sold_at) AS last_sold_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = ar.session_id
                    WHERE ar.customer_id = %s
                      AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
                    GROUP BY cs.id, cs.name
                    ORDER BY COALESCE(MAX(ar.sold_at), MAX(cs.started_at)) DESC
                    """,
                    (int(customer_id),),
                )
                sessions = _pg_fetchall_dict(cur)
                cur.execute(
                    f"""
                    SELECT
                        NULL AS id,
                        'TikTok Shop' AS session_name,
                        COUNT(*) AS purchase_count,
                        COALESCE(SUM(so.total_amount), 0) AS total_revenue,
                        COALESCE(SUM(sol.subtotal - (COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0))), 0) AS total_profit,
                        MAX(COALESCE(so.ordered_at, so.created_at)) AS last_sold_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
                    JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol ON sol.sale_order_id = so.id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                    WHERE so.customer_id = %s
                      AND LOWER(COALESCE(so.state, '')) != 'cancel'
                      AND LOWER(COALESCE(so.order_source, '')) = 'tiktok_shop'
                    """,
                    (int(customer_id),),
                )
                tiktok_shop_row = _pg_fetchone_dict(cur)
                if tiktok_shop_row and int(tiktok_shop_row.get("purchase_count") or 0) > 0:
                    sessions.append(tiktok_shop_row)
                cur.execute(
                    f"""
                    SELECT
                        NULL AS id,
                        'TikTok LIVE' AS session_name,
                        COUNT(*) AS purchase_count,
                        COALESCE(SUM(so.total_amount), 0) AS total_revenue,
                        COALESCE(SUM(sol.subtotal - (COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0))), 0) AS total_profit,
                        MAX(COALESCE(so.ordered_at, so.created_at)) AS last_sold_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
                    JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol ON sol.sale_order_id = so.id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                    WHERE so.customer_id = %s
                      AND LOWER(COALESCE(so.state, '')) != 'cancel'
                      AND LOWER(COALESCE(so.order_source, '')) = 'tiktok_live'
                    """,
                    (int(customer_id),),
                )
                tiktok_live_row = _pg_fetchone_dict(cur)
                if tiktok_live_row and int(tiktok_live_row.get("purchase_count") or 0) > 0:
                    sessions.append(tiktok_live_row)
                cur.execute(
                    f"""
                    SELECT
                        product_name,
                        sku,
                        barcode,
                        SUM(purchase_count) AS purchase_count,
                        COALESCE(SUM(total_revenue), 0) AS total_revenue,
                        COALESCE(SUM(total_profit), 0) AS total_profit,
                        AVG(avg_sale_price) AS avg_sale_price,
                        MAX(last_sold_at) AS last_sold_at
                    FROM (
                        SELECT
                            COALESCE(ar.product_name, 'Unknown') AS product_name,
                            ar.sku,
                            ar.barcode,
                            COUNT(*) AS purchase_count,
                            COALESCE(SUM(ar.sale_price), 0) AS total_revenue,
                            COALESCE(SUM(ar.profit), 0) AS total_profit,
                            AVG(ar.sale_price) AS avg_sale_price,
                            MAX(ar.sold_at) AS last_sold_at
                        FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
                        WHERE ar.customer_id = %s
                          AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
                        GROUP BY COALESCE(ar.product_name, 'Unknown'), ar.sku, ar.barcode

                        UNION ALL

                        SELECT
                            COALESCE(sol.description, p.name, 'Unknown') AS product_name,
                            p.sku,
                            p.barcode,
                            COUNT(*) AS purchase_count,
                            COALESCE(SUM(sol.subtotal), 0) AS total_revenue,
                            COALESCE(SUM(sol.subtotal - (COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0))), 0) AS total_profit,
                            AVG(sol.unit_price) AS avg_sale_price,
                            MAX(COALESCE(so.ordered_at, so.created_at)) AS last_sold_at
                        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
                        JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol ON sol.sale_order_id = so.id
                        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                        WHERE so.customer_id = %s
                          AND LOWER(COALESCE(so.state, '')) != 'cancel'
                          AND LOWER(COALESCE(so.order_source, '')) IN ('tiktok_shop', 'tiktok_live')
                        GROUP BY COALESCE(sol.description, p.name, 'Unknown'), p.sku, p.barcode
                    ) grouped_products
                    GROUP BY product_name, sku, barcode
                    ORDER BY total_revenue DESC, purchase_count DESC
                    LIMIT 50
                    """,
                    (int(customer_id), int(customer_id)),
                )
                products = _pg_fetchall_dict(cur)
                cur.execute(
                    f"""
                    SELECT
                        COALESCE(auction.purchase_count, 0) + COALESCE(shop.purchase_count, 0) AS purchase_count,
                        COALESCE(auction.session_count, 0) AS session_count,
                        COALESCE(auction.unique_products, 0) + COALESCE(shop.unique_products, 0) AS unique_products,
                        COALESCE(auction.total_revenue, 0) + COALESCE(shop.total_revenue, 0) AS total_revenue,
                        COALESCE(auction.total_profit, 0) + COALESCE(shop.total_profit, 0) AS total_profit
                    FROM (
                        SELECT
                            COUNT(DISTINCT ar.id) AS purchase_count,
                            COUNT(DISTINCT ar.session_id) AS session_count,
                            COUNT(DISTINCT COALESCE(ar.product_name, 'Unknown')) AS unique_products,
                            COALESCE(SUM(ar.sale_price), 0) AS total_revenue,
                            COALESCE(SUM(ar.profit), 0) AS total_profit
                        FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
                        WHERE ar.customer_id = %s
                          AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
                    ) AS auction
                    CROSS JOIN (
                        SELECT
                            COUNT(*) AS purchase_count,
                            COUNT(DISTINCT COALESCE(sol.description, p.name, 'Unknown')) AS unique_products,
                            COALESCE(SUM(sol.subtotal), 0) AS total_revenue,
                            COALESCE(SUM(sol.subtotal - (COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0))), 0) AS total_profit
                        FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders so
                        JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol ON sol.sale_order_id = so.id
                        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                        WHERE so.customer_id = %s
                          AND LOWER(COALESCE(so.state, '')) != 'cancel'
                          AND LOWER(COALESCE(so.order_source, '')) IN ('tiktok_shop', 'tiktok_live')
                    ) AS shop
                    """,
                    (int(customer_id), int(customer_id)),
                )
                summary = _pg_fetchone_dict(cur) or {}
    return {
        "identities": identities,
        "sessions": sessions,
        "products": products,
        "summary": summary,
        "reviews": [],
        "review_summary": {},
    }


def get_product_profit_rows(session_id=None, q=None):
    _require_company_postgres_runtime("inventory_products")
    query = f"""
        SELECT
            MIN(ar.id) AS id,
            ar.product_name,
            ar.sku,
            ar.barcode,
            ar.session_id,
            cs.name AS session_name,
            COUNT(*) AS times_sold,
            AVG(ar.sale_price) AS avg_winning_price,
            SUM(ar.sale_price) AS total_revenue,
            SUM(ar.cost_price) AS total_cost,
            SUM(ar.profit) AS total_profit
        FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = ar.session_id
        WHERE 1=1
          AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
    """
    params = []
    if session_id:
        query += " AND ar.session_id = %s"
        params.append(int(session_id))
    if q:
        ql = f"%{q.lower()}%"
        query += " AND (LOWER(COALESCE(ar.product_name, '')) LIKE %s OR LOWER(COALESCE(ar.sku, '')) LIKE %s OR LOWER(COALESCE(ar.barcode, '')) LIKE %s)"
        params.extend([ql, ql, ql])
    query += """
        GROUP BY ar.session_id, ar.product_name, ar.sku, ar.barcode, cs.name
        ORDER BY total_profit DESC, total_revenue DESC
    """
    rows = []
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            raw_rows = _pg_fetchall_dict(cur)
        for row in raw_rows:
            revenue = float(row["total_revenue"] or 0)
            profit = float(row["total_profit"] or 0)
            row["avg_margin"] = round((profit / revenue * 100.0), 1) if revenue else 0.0
            rows.append(row)
    return rows


def _pg_product_detail_sales(product, product_id):
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM (
                    SELECT
                        ('auction:' || ar.id::text) AS id,
                        ar.winner_username AS buyer_username,
                        ar.lot_number,
                        ar.sold_at,
                        ar.product_name,
                        ar.sale_price AS allocated_revenue,
                        ar.sale_price,
                        ar.fees,
                        ar.profit,
                        ar.session_id,
                        cs.name AS session_name,
                        'auction_result' AS source,
                        ar.id AS auction_result_id,
                        NULL::text AS external_order_ref
                    FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = ar.session_id
                    WHERE (
                            ar.product_name = %s
                         OR (ar.sku IS NOT NULL AND ar.sku = %s)
                         OR (ar.barcode IS NOT NULL AND ar.barcode = %s)
                    )
                       AND NOT EXISTS (
                            SELECT 1
                            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines existing_sol
                            JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders existing_so ON existing_so.id = existing_sol.sale_order_id
                            WHERE existing_sol.auction_result_id = ar.id
                              AND LOWER(COALESCE(existing_so.state, '')) IN ('sale', 'done')
                       )

                    UNION ALL

                    SELECT
                        ('sale:' || sol.id::text) AS id,
                        COALESCE(NULLIF(so.whatnot_buyer_username, ''), NULLIF(ci.username, ''), NULLIF(c.display_name, ''), NULLIF(c.whatnot_username, '')) AS buyer_username,
                        cl.lot_number AS lot_number,
                        COALESCE(so.ordered_at, so.created_at) AS sold_at,
                        COALESCE(sol.description, p.name) AS product_name,
                        sol.subtotal AS allocated_revenue,
                        sol.unit_price AS sale_price,
                        0 AS fees,
                        (sol.subtotal - (COALESCE(p.cost_price, 0) * COALESCE(sol.qty, 0))) AS profit,
                        so.session_id,
                        COALESCE(cs.name, CASE WHEN LOWER(COALESCE(so.order_source, '')) = 'tiktok_shop' THEN 'TikTok Shop' ELSE so.order_source END) AS session_name,
                        so.order_source AS source,
                        sol.auction_result_id,
                        so.external_order_ref
                    FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                    JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders so ON so.id = sol.sale_order_id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.products p ON p.id = sol.product_id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_sessions cs ON cs.id = so.session_id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.company_lots cl ON cl.id = sol.lot_id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customers c ON c.id = so.customer_id
                    LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.customer_identities ci ON ci.customer_id = so.customer_id
                        AND ci.platform = CASE WHEN LOWER(COALESCE(so.order_source, '')) LIKE 'tiktok%%' THEN 'tiktok' ELSE LOWER(COALESCE(so.order_source, '')) END
                    WHERE sol.product_id = %s
                      AND LOWER(COALESCE(so.state, '')) IN ('sale', 'done')
                ) sales
                ORDER BY sold_at DESC
                LIMIT 50
                """,
                (product["name"], product.get("sku"), product.get("barcode"), int(product_id)),
            )
            return _normalize_product_detail_sales(_pg_fetchall_dict(cur))


def _normalize_product_detail_sales(rows):
    normalized = []
    for row in rows:
        row = dict(row)
        if not row.get("lot_number"):
            ref = str(row.get("external_order_ref") or "")
            if ref.lower().startswith("tiktok_live:") and ":" in ref:
                maybe_lot = ref.rsplit(":", 1)[-1].strip()
                if maybe_lot:
                    row["lot_number"] = maybe_lot
        if row.get("buyer_username"):
            row["buyer_username"] = str(row["buyer_username"]).replace("tiktok_live:", "").strip()
        normalized.append(row)
    return normalized


def get_product_detail(product_id):
    _require_company_postgres_runtime("inventory_products")
    product = get_product(product_id)
    if not product:
        return None
    movements = list_inventory_movements(product_id=product_id, limit=12)
    sales = _pg_product_detail_sales(product, product_id)
    total_revenue = round(sum(float(row.get("allocated_revenue") or 0) for row in sales), 2)
    total_profit = round(sum(float(row.get("profit") or 0) for row in sales), 2)
    return {
        "product": product,
        "movements": movements,
        "sales": sales,
        "sales_summary": {
            "times_sold": len(sales),
            "total_revenue": total_revenue,
            "total_profit": total_profit,
        },
    }


def get_inventory_prep_overview():
    _require_company_postgres_runtime("inventory_products")
    products = list_products(active_only=True, low_stock_only=False)
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT product_name, sku, barcode, sale_price, profit, products_sold_count
                FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results
                ORDER BY sold_at DESC
                """
            )
            sales = _pg_fetchall_dict(cur)

    sales_by_key = {}
    for sale in sales:
        keys = {
            ("name", (sale.get("product_name") or "").strip().lower()),
            ("sku", (sale.get("sku") or "").strip().lower()),
            ("barcode", (sale.get("barcode") or "").strip().lower()),
        }
        for key in keys:
            if not key[1]:
                continue
            bucket = sales_by_key.setdefault(key, {"times_sold": 0, "units_sold": 0, "revenue": 0.0, "profit": 0.0})
            bucket["times_sold"] += 1
            bucket["units_sold"] += int(sale.get("products_sold_count") or 1)
            bucket["revenue"] += float(sale.get("sale_price") or 0)
            bucket["profit"] += float(sale.get("profit") or 0)

    category_rollup = {}
    priority_rows = []
    for product in products:
        stats = {"times_sold": 0, "units_sold": 0, "revenue": 0.0, "profit": 0.0}
        for key in (
            ("barcode", (product.get("barcode") or "").strip().lower()),
            ("sku", (product.get("sku") or "").strip().lower()),
            ("name", (product.get("name") or "").strip().lower()),
        ):
            matched = sales_by_key.get(key)
            if matched:
                stats = matched
                break

        qty = float(product.get("on_hand_qty") or 0)
        threshold = float(product.get("low_stock_threshold") or 0)
        revenue = round(stats["revenue"], 2)
        profit = round(stats["profit"], 2)
        units_sold = int(stats["units_sold"] or 0)
        category = product.get("category_name") or "Uncategorized"

        if units_sold > 0 and qty <= threshold:
            recommendation = "restock_now"
            reason = "selling but below threshold"
        elif units_sold > 0 and qty > threshold:
            recommendation = "push_next_show"
            reason = "selling with stock available"
        elif units_sold == 0 and qty > max(threshold * 2, 5):
            recommendation = "slow_moving"
            reason = "stock on hand with no sales yet"
        else:
            recommendation = "watch"
            reason = "monitor before next show"

        priority_rows.append({
            "id": product["id"],
            "name": product.get("name"),
            "sku": product.get("sku"),
            "barcode": product.get("barcode"),
            "category_name": category,
            "on_hand_qty": qty,
            "low_stock_threshold": threshold,
            "cost_price": float(product.get("cost_price") or 0),
            "retail_price": float(product.get("retail_price") or 0),
            "times_sold": int(stats["times_sold"] or 0),
            "units_sold": units_sold,
            "total_revenue": revenue,
            "total_profit": profit,
            "recommendation": recommendation,
            "reason": reason,
            "stock_value": round(qty * float(product.get("cost_price") or 0), 2),
        })

        bucket = category_rollup.setdefault(category, {
            "category_name": category,
            "product_count": 0,
            "on_hand_qty": 0.0,
            "stock_value": 0.0,
            "units_sold": 0,
            "total_revenue": 0.0,
            "total_profit": 0.0,
        })
        bucket["product_count"] += 1
        bucket["on_hand_qty"] += qty
        bucket["stock_value"] += qty * float(product.get("cost_price") or 0)
        bucket["units_sold"] += units_sold
        bucket["total_revenue"] += revenue
        bucket["total_profit"] += profit

    priority_rank = {"restock_now": 0, "push_next_show": 1, "slow_moving": 2, "watch": 3}
    priority_rows.sort(key=lambda row: (priority_rank.get(row["recommendation"], 9), -row["units_sold"], row["on_hand_qty"], row["name"] or ""))

    category_rows = list(category_rollup.values())
    for row in category_rows:
        row["stock_value"] = round(row["stock_value"], 2)
        row["total_revenue"] = round(row["total_revenue"], 2)
        row["total_profit"] = round(row["total_profit"], 2)
        revenue = row["total_revenue"]
        row["margin_pct"] = round((row["total_profit"] / revenue * 100.0), 1) if revenue else 0.0
    category_rows.sort(key=lambda row: (-row["total_revenue"], row["category_name"]))

    return {
        "priority_rows": priority_rows[:20],
        "category_rows": category_rows,
        "summary": {
            "restock_now": len([row for row in priority_rows if row["recommendation"] == "restock_now"]),
            "push_next_show": len([row for row in priority_rows if row["recommendation"] == "push_next_show"]),
            "slow_moving": len([row for row in priority_rows if row["recommendation"] == "slow_moving"]),
            "watch": len([row for row in priority_rows if row["recommendation"] == "watch"]),
        },
    }


def _recalc_lot_totals(lot_id):
    _require_company_postgres_runtime("company_lots")
    ensure_wave1_postgres_schema()
    with pg_domain_tx("company_lots", "lot_totals_recalc") as (_pg_conn, cur):
        cur.execute(
            f"""
            SELECT
                COALESCE(SUM(qty_snapshot), 0) AS total_products,
                COALESCE(SUM(CASE WHEN status = 'sold' THEN qty_snapshot ELSE 0 END), 0) AS sold_products,
                COALESCE(SUM(CASE WHEN status = 'dropped' THEN qty_snapshot ELSE 0 END), 0) AS dropped_products,
                COALESCE(SUM(unit_cost * qty_snapshot), 0) AS total_cost
            FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items
            WHERE lot_id = %s
            """,
            (int(lot_id),),
        )
        row = _pg_fetchone_dict(cur) or {}
        cur.execute(
            f"""
            SELECT
                COALESCE(SUM(fees), 0) AS total_fees,
                COALESCE(SUM(profit), 0) AS total_profit,
                COALESCE(SUM(sale_price), 0) AS winning_price
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results
            WHERE lot_id = %s
            """,
            (int(lot_id),),
        )
        ar_row = _pg_fetchone_dict(cur) or {}
        cur.execute(
            f"""
            UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lots
            SET total_products = %s,
                sold_products = %s,
                dropped_products = %s,
                winning_price = COALESCE(%s, 0),
                total_cost = COALESCE(%s, 0),
                fees = COALESCE(%s, 0),
                total_profit = COALESCE(%s, 0)
            WHERE id = %s
            """,
            (
                row.get("total_products") or 0,
                row.get("sold_products") or 0,
                row.get("dropped_products") or 0,
                ar_row.get("winning_price") or 0,
                row.get("total_cost") or 0,
                ar_row.get("total_fees") or 0,
                ar_row.get("total_profit") or 0,
                int(lot_id),
            ),
        )


def _recalc_buyer_group(session_id, buyer_username):
    _require_company_postgres_runtime("company_orders")
    try:
        with pg_domain_tx("company_orders", "buyer_groups_recalc") as (_pg_conn, cur):
            cur.execute(
                f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.buyer_groups WHERE session_id = %s AND buyer_username = %s",
                (int(session_id), buyer_username),
            )
            row = _pg_fetchone_dict(cur)
            if row:
                _pg_recalc_buyer_group_txn(cur, session_id, buyer_username)
        return
    except Exception as exc:
        log_cutover_event("company_orders", "postgres_primary_failed_closed", "buyer_groups_recalc", f"{session_id}:{buyer_username}", {"error": str(exc)})
        raise


def _recalc_sale_order(conn, sale_order_id):
    row = conn.execute(
        """
        SELECT COALESCE(SUM(subtotal), 0) AS subtotal
        FROM sale_order_lines
        WHERE sale_order_id = ?
        """,
        (int(sale_order_id),),
    ).fetchone()
    conn.execute(
        """
        UPDATE sale_orders
        SET subtotal = ?, total_amount = ?, updated_at = ?
        WHERE id = ?
        """,
        (row["subtotal"] or 0, row["subtotal"] or 0, utc_now(), int(sale_order_id)),
    )


def _recalc_session_totals(session_id):
    _require_company_postgres_runtime("company_sessions")
    _require_company_postgres_runtime("company_results")
    _auto_cancel_overdue_payment_reviews(session_id=session_id)
    ensure_wave1_postgres_schema()
    try:
        with pg_domain_tx("company_sessions", "session_totals_recalc") as (_pg_conn, cur):
            cur.execute(
            f"""
            SELECT
                COALESCE(SUM(ar.sale_price), 0) AS total_revenue,
                COALESCE(SUM(ar.cost_price), 0) AS total_cost,
                COALESCE(SUM(ar.fees), 0) AS total_fees,
                COALESCE(SUM(ar.profit), 0) AS total_profit,
                COALESCE(SUM(ar.products_sold_count), 0) AS total_products_sold,
                COUNT(*) AS total_lots_sold
            FROM {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
            WHERE ar.session_id = %s
              AND {_PG_CANONICAL_AUCTION_RESULT_FILTER}
            """,
            (int(session_id),),
            )
            session_row = _pg_fetchone_dict(cur) or {}
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_sessions
                SET total_revenue = %s,
                    total_cost = %s,
                    total_fees = %s,
                    total_profit = %s,
                    total_products_sold = %s,
                    total_lots_sold = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    session_row.get("total_revenue") or 0,
                    session_row.get("total_cost") or 0,
                    session_row.get("total_fees") or 0,
                    session_row.get("total_profit") or 0,
                    session_row.get("total_products_sold") or 0,
                    session_row.get("total_lots_sold") or 0,
                    utc_now(),
                    int(session_id),
                ),
            )
    except Exception as exc:
        log_cutover_event("company_sessions", "postgres_primary_failed_closed", "session_totals_recalc", str(session_id), {"error": str(exc)})
        raise


def _auto_cancel_overdue_payment_reviews(session_id=None):
    _require_company_postgres_runtime("company_pending")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    ensure_wave1_postgres_schema()
    params = [cutoff]
    session_sql = ""
    if session_id is not None:
        session_sql = " AND pwa.session_id = %s"
        params.append(int(session_id))
    with pg_domain_tx("company_pending", "payment_review_auto_cancel") as (_pg_conn, cur):
        cur.execute(
            f"""
            SELECT pwa.id
            FROM {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments pwa
            JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar ON ar.id = pwa.auction_result_id
            WHERE pwa.status = 'payment_review'
              AND COALESCE(ar.sold_at, pwa.detected_at, pwa.created_at, '') <> ''
              AND COALESCE(ar.sold_at, pwa.detected_at, pwa.created_at) <= %s
              {session_sql}
            """,
            tuple(params),
        )
        rows = cur.fetchall()
        if not rows:
            return 0
        now = utc_now()
        cur.executemany(
            f"""
            UPDATE {POSTGRES_SIDECAR_SCHEMA}.pending_winner_assignments
            SET status = 'payment_cancelled',
                updated_at = %s
            WHERE id = %s
            """,
            [(now, int(row[0])) for row in rows],
        )
        return len(rows)


# ---------------------------------------------------------------------------
# Pick list helpers
# ---------------------------------------------------------------------------

def create_pick_list(session_id, filename=None, total_shipments=0, total_lots=0,
                     matched_lots=0, unmatched_lots=0, total_revenue=0,
                     customers_synced=0, orders_synced=0, inventory_deducted=0):
    _require_company_postgres_runtime("company_orders")
    now = utc_now()
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.pick_lists (
                    session_id, filename, total_shipments, total_lots,
                    matched_lots, unmatched_lots, total_revenue,
                    customers_synced, orders_synced, inventory_deducted, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    session_id, filename, total_shipments, total_lots,
                    matched_lots, unmatched_lots, total_revenue,
                    customers_synced, orders_synced, inventory_deducted, now,
                ),
            )
            row = _pg_fetchone_dict(cur)
        conn.commit()
    return row


def add_pick_list_item(pick_list_id, shipment_index=0, username=None, buyer_name=None,
                       address=None, tracking_number=None, shipping_method=None,
                       ship_date=None, weight=None, lot_number=None, product_name=None,
                       barcode=None, sku=None, sale_price=0, order_id=None,
                       matched=0, sale_order_id=None, customer_id=None):
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.pick_list_items (
                    pick_list_id, shipment_index, username, buyer_name, address,
                    tracking_number, shipping_method, ship_date, weight,
                    lot_number, product_name, barcode, sku, sale_price,
                    order_id, matched, sale_order_id, customer_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    int(pick_list_id), shipment_index, username, buyer_name, address,
                    tracking_number, shipping_method, ship_date, weight,
                    lot_number, product_name, barcode, sku, float(sale_price or 0),
                    order_id, int(matched), sale_order_id, customer_id,
                ),
            )
        conn.commit()
    return


def list_pick_lists(session_id=None):
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            if session_id:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.pick_lists WHERE session_id = %s ORDER BY created_at DESC",
                    (int(session_id),),
                )
            else:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.pick_lists ORDER BY created_at DESC"
                )
            return _pg_fetchall_dict(cur)


def get_pick_list(pick_list_id):
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.pick_lists WHERE id = %s",
                (int(pick_list_id),),
            )
            return _pg_fetchone_dict(cur)


def list_pick_list_items(pick_list_id):
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.pick_list_items WHERE pick_list_id = %s ORDER BY shipment_index, id",
                (int(pick_list_id),),
            )
            return _pg_fetchall_dict(cur)


def find_existing_sale_order(session_id, username):
    """Find an existing non-cancelled sale order for a buyer in a session."""
    _require_company_postgres_runtime("company_orders")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.sale_orders
                WHERE session_id = %s AND whatnot_buyer_username = %s AND state != 'cancel'
                ORDER BY created_at ASC LIMIT 1
                """,
                (int(session_id), username),
            )
            return _pg_fetchone_dict(cur)


def _pg_find_product_for_lot_replacement_txn(cur, product_id=None, query=None):
    if product_id:
        cur.execute(
            f"""
            SELECT p.*, pc.name AS category_name
            FROM {POSTGRES_SIDECAR_SCHEMA}.products p
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
            WHERE p.id = %s
            LIMIT 1
            """,
            (int(product_id),),
        )
        return _pg_fetchone_dict(cur)

    raw = str(query or "").strip()
    if not raw:
        return None

    cur.execute(
        f"""
        SELECT p.*, pc.name AS category_name
        FROM {POSTGRES_SIDECAR_SCHEMA}.products p
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
        WHERE p.barcode = %s OR p.sku = %s
        ORDER BY p.active DESC, p.id ASC
        LIMIT 1
        """,
        (raw, raw),
    )
    product = _pg_fetchone_dict(cur)
    if product:
        return product

    cur.execute(
        f"""
        SELECT p.*, pc.name AS category_name
        FROM {POSTGRES_SIDECAR_SCHEMA}.products p
        LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
        WHERE LOWER(p.name) = LOWER(%s)
           OR p.name ILIKE %s
        ORDER BY
            CASE WHEN LOWER(p.name) = LOWER(%s) THEN 0 ELSE 1 END,
            p.active DESC,
            p.id ASC
        LIMIT 1
        """,
        (raw, f"%{raw}%", raw),
    )
    return _pg_fetchone_dict(cur)


def replace_tiktok_live_lot_product(session_id, lot_number, product_id=None, query=None, actor=None):
    """Correct the product tied to a TikTok live lot after the session has ended.

    If the previous product was already deducted, this records a balancing
    movement back into stock for the previous product and deducts the
    replacement product exactly once for the sale-order line.
    """
    _require_company_postgres_runtime("company_lots")
    _require_company_postgres_runtime("company_orders")
    _require_company_postgres_runtime("inventory_movements")
    ensure_wave1_postgres_schema()
    session_id = int(session_id)
    normalized_lot = str(lot_number or "").strip()
    if not session_id or not normalized_lot:
        raise ValueError("session_id and lot_number are required")

    now = utc_now()
    result = None

    with pg_domain_tx("company_orders", "tiktok_live_lot_product_replace") as (_pg_conn, cur):
        product = _pg_find_product_for_lot_replacement_txn(cur, product_id=product_id, query=query)
        if not product:
            raise ValueError("replacement product not found")
        new_product_id = int(product["id"])

        cur.execute(
            f"""
            SELECT *
            FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots
            WHERE session_id = %s AND lot_number = %s
            ORDER BY id ASC
            LIMIT 1
            """,
            (session_id, normalized_lot),
        )
        lot = _pg_fetchone_dict(cur)
        if not lot:
            raise ValueError(f"lot {normalized_lot} not found in session {session_id}")
        lot_id = int(lot["id"])

        cur.execute(
            f"""
            SELECT *
            FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items
            WHERE lot_id = %s
            ORDER BY id ASC
            LIMIT 1
            """,
            (lot_id,),
        )
        lot_item = _pg_fetchone_dict(cur)

        cur.execute(
            f"""
            SELECT sol.*, so.order_number, so.session_id, so.order_source, so.state, so.payment_status,
                   so.fulfillment_status, so.tracking_status, so.delivered_at,
                   so.external_order_ref, so.whatnot_buyer_username,
                   ar.id AS result_id, ar.sale_price AS result_sale_price, ar.fees AS result_fees
            FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
            JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders so ON so.id = sol.sale_order_id
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.auction_results ar
              ON ar.id = sol.auction_result_id
              OR (ar.session_id = so.session_id AND ar.lot_number = %s)
            WHERE so.session_id = %s
              AND so.order_source = 'tiktok_live'
              AND COALESCE(so.state, '') != 'cancel'
              AND (
                    sol.lot_id = %s
                 OR ar.lot_number = %s
                 OR so.external_order_ref ILIKE %s
              )
            ORDER BY sol.id ASC
            LIMIT 1
            """,
            (normalized_lot, session_id, lot_id, normalized_lot, f"%:{normalized_lot}"),
        )
        line = _pg_fetchone_dict(cur)

        old_product_id = int((line or {}).get("product_id") or (lot_item or {}).get("product_id") or 0)
        qty = float((line or {}).get("qty") or (lot_item or {}).get("qty_snapshot") or 1)
        new_cost = float(product.get("cost_price") or 0) * qty
        barcode = str(product.get("barcode") or "").strip() or None
        sku = str(product.get("sku") or product.get("default_code") or "").strip() or None
        name = str(product.get("name") or "").strip()

        if lot_item:
            cur.execute(
                f"""
                UPDATE {POSTGRES_SIDECAR_SCHEMA}.company_lot_items
                SET product_id = %s,
                    barcode = %s,
                    sku = %s,
                    product_name = %s,
                    unit_cost = %s,
                    qty_snapshot = %s
                WHERE id = %s
                """,
                (new_product_id, barcode, sku, name, float(product.get("cost_price") or 0), qty, int(lot_item["id"])),
            )
        else:
            cur.execute(
                f"""
                INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.company_lot_items (
                    lot_id, product_id, barcode, sku, product_name, unit_cost,
                    qty_snapshot, scanned_at, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open')
                """,
                (lot_id, new_product_id, barcode, sku, name, float(product.get("cost_price") or 0), qty, now),
            )

        inventory_adjusted = False
        if line:
            line_id = int(line["id"])
            order_id = int(line["sale_order_id"])
            was_applied = int(line.get("inventory_applied") or 0) == 1
            if old_product_id != new_product_id:
                if was_applied and old_product_id:
                    cur.execute(
                        f"""
                        SELECT id
                        FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
                        WHERE reference_type = 'sale_order_line_swap_in'
                          AND reference_id = %s
                          AND product_id = %s
                        LIMIT 1
                        """,
                        (line_id, old_product_id),
                    )
                    if not _pg_fetchone_dict(cur):
                        _pg_record_inventory_movement_txn(
                            cur,
                            old_product_id,
                            "in",
                            qty,
                            reason=f"TikTok Live lot {normalized_lot} product correction: return previous product",
                            reference_type="sale_order_line_swap_in",
                            reference_id=line_id,
                        )
                        inventory_adjusted = True
                    cur.execute(
                        f"""
                        SELECT id
                        FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
                        WHERE reference_type = 'sale_order_line_swap_out'
                          AND reference_id = %s
                          AND product_id = %s
                        LIMIT 1
                        """,
                        (line_id, new_product_id),
                    )
                    if not _pg_fetchone_dict(cur):
                        _pg_record_inventory_movement_txn(
                            cur,
                            new_product_id,
                            "out",
                            -qty,
                            reason=f"TikTok Live lot {normalized_lot} product correction: deduct replacement product",
                            reference_type="sale_order_line_swap_out",
                            reference_id=line_id,
                        )
                        inventory_adjusted = True

                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                    SET product_id = %s,
                        description = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (new_product_id, name, now, line_id),
                )

            if not was_applied and _sale_order_inventory_should_be_applied(line):
                cur.execute(
                    f"""
                    SELECT id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
                    WHERE product_id = %s
                      AND (
                            (reference_type = 'sale_order_line' AND reference_id = %s)
                         OR (reference_type = 'sale_order' AND reference_id = %s)
                      )
                    LIMIT 1
                    """,
                    (new_product_id, line_id, order_id),
                )
                if not _pg_fetchone_dict(cur):
                    _pg_record_inventory_movement_txn(
                        cur,
                        new_product_id,
                        "out",
                        -qty,
                        reason=f"TikTok Live lot {normalized_lot} sale correction",
                        reference_type="sale_order_line",
                        reference_id=line_id,
                    )
                    inventory_adjusted = True
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines
                    SET inventory_applied = 1, updated_at = %s
                    WHERE id = %s
                    """,
                    (now, line_id),
                )

            sale_price = float(line.get("result_sale_price") or line.get("subtotal") or 0)
            fees = float(line.get("result_fees") or 0)
            profit = sale_price - fees - new_cost
            margin_pct = (profit / sale_price * 100.0) if sale_price else 0.0
            result_id = line.get("result_id")
            if result_id:
                cur.execute(
                    f"""
                    UPDATE {POSTGRES_SIDECAR_SCHEMA}.auction_results
                    SET product_name = %s,
                        barcode = %s,
                        sku = %s,
                        cost_price = %s,
                        profit = %s,
                        margin_pct = %s,
                        products_sold_count = %s
                    WHERE id = %s
                    """,
                    (name, barcode, sku, new_cost, profit, margin_pct, int(qty or 1), int(result_id)),
                )
            _pg_recalc_sale_order_txn(cur, order_id)

        result = {
            "ok": True,
            "session_id": session_id,
            "lot_number": normalized_lot,
            "old_product_id": old_product_id or None,
            "new_product_id": new_product_id,
            "inventory_adjusted": inventory_adjusted,
            "line_id": int(line["id"]) if line else None,
            "product": {
                "id": new_product_id,
                "name": name,
                "barcode": barcode,
                "sku": sku,
                "cost_price": product.get("cost_price"),
                "retail_price": product.get("retail_price"),
            },
        }

    _recalc_lot_totals(lot_id)
    _recalc_session_totals(session_id)
    return result


def apply_tiktok_live_session_inventory(session_id):
    """
    For a TikTok live session: link products to sale order lines by barcode
    and deduct inventory for all confirmed orders not yet applied.
    Returns a summary dict with counts of linked, applied, already_applied, and errors.
    """
    _require_company_postgres_runtime("company_orders")
    session_id = int(session_id)
    now = utc_now()

    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.company_lots WHERE session_id = %s",
                (session_id,),
            )
            lots = _pg_fetchall_dict(cur)
            lot_item_by_id = {}
            lot_item_by_number = {}
            for lot in lots:
                cur.execute(
                    f"SELECT * FROM {POSTGRES_SIDECAR_SCHEMA}.company_lot_items WHERE lot_id = %s ORDER BY id ASC LIMIT 1",
                    (int(lot['id']),),
                )
                items = _pg_fetchall_dict(cur)
                if items:
                    lot_item_by_id[int(lot["id"])] = items[0]
                    lot_num = str(lot.get("lot_number") or "").strip()
                    if lot_num:
                        lot_item_by_number[lot_num] = items[0]
            cur.execute(
                f"""
                SELECT sol.id AS line_id, sol.sale_order_id, sol.product_id AS line_product_id,
                       sol.lot_id AS line_lot_id, sol.qty, sol.inventory_applied,
                       so.order_number, so.whatnot_buyer_username, so.external_order_ref
                FROM {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines sol
                JOIN {POSTGRES_SIDECAR_SCHEMA}.sale_orders so ON so.id = sol.sale_order_id
                WHERE so.session_id = %s
                  AND so.state != 'cancel'
                  AND so.payment_status = 'paid'
                  AND LOWER(COALESCE(so.external_order_ref, '')) LIKE 'tiktok_live:%%'
                ORDER BY so.id, sol.id
                """,
                (session_id,),
            )
            lines = _pg_fetchall_dict(cur)

    linked = 0
    applied = 0
    already_applied = 0
    errors = []

    with _pg_connect() as conn:
        with conn.cursor() as cur:
            for line in lines:
                line_id = int(line["line_id"])
                order_id = int(line["sale_order_id"])
                product_id = line["line_product_id"]

                if not product_id:
                    barcode = None
                    lot_id = line.get("line_lot_id")
                    if lot_id and int(lot_id) in lot_item_by_id:
                        item = lot_item_by_id[int(lot_id)]
                        product_id = item.get("product_id")
                        barcode = item.get("barcode")
                    if not product_id:
                        ext_ref = str(line.get("external_order_ref") or "")
                        m = re.match(r"^tiktok_(?:live|shop):[^:]+:([^:]+)$", ext_ref, re.I)
                        if m:
                            lot_num = m.group(1).strip()
                            item = lot_item_by_number.get(lot_num)
                            if item:
                                product_id = item.get("product_id")
                                barcode = item.get("barcode")
                    if not product_id and barcode:
                        product = find_product_by_code(barcode)
                        if product:
                            product_id = int(product["id"])
                    if product_id:
                        cur.execute(
                            f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines SET product_id = %s, updated_at = %s WHERE id = %s",
                            (int(product_id), now, line_id),
                        )
                        linked += 1
                    else:
                        errors.append(f"No product for line {line_id} (order {line.get('order_number')})")
                        continue

                qty = float(line.get("qty") or 1)
                buyer = str(line.get("whatnot_buyer_username") or "unknown")
                cur.execute(
                    f"""
                    SELECT id
                    FROM {POSTGRES_SIDECAR_SCHEMA}.inventory_movements
                    WHERE product_id = %s
                      AND (
                            (reference_type = 'sale_order_line' AND reference_id = %s)
                         OR (reference_type = 'sale_order' AND reference_id = %s)
                      )
                    LIMIT 1
                    """,
                    (int(product_id), line_id, order_id),
                )
                existing_movement = _pg_fetchone_dict(cur)
                if existing_movement and line.get("inventory_applied"):
                    already_applied += 1
                else:
                    if not existing_movement:
                        _pg_record_inventory_movement_txn(
                            cur,
                            int(product_id),
                            "out",
                            -qty,
                            reason=f"TikTok Live sale to {buyer}: {line.get('order_number') or order_id}",
                            reference_type="sale_order_line",
                            reference_id=line_id,
                        )
                        applied += 1
                    else:
                        already_applied += 1
                cur.execute(
                    f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.sale_order_lines SET inventory_applied = 1, updated_at = %s WHERE id = %s",
                    (now, line_id),
                )
        conn.commit()

    return {
        "ok": True,
        "session_id": session_id,
        "linked": linked,
        "applied": applied,
        "already_applied": already_applied,
        "errors": errors,
    }
