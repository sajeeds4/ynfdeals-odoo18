from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request

from server.auth import get_session, session_cookie_name
from server.company_db import (
    delete_product,
    ensure_category,
    get_product,
    record_inventory_movement,
    set_product_details,
    TIKTOK_PRODUCT_FIELDS,
    upsert_product,
)


def _with_status(payload: dict, status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def _product_image_url(row):
    if row.get("image_path"):
        return f"data:image/png;base64,{row['image_path']}"
    if row.get("media_url"):
        return row["media_url"]
    return None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _audit_actor(request: Request):
    session_id = request.cookies.get(session_cookie_name())
    if not session_id:
        return None
    session = get_session(
        session_id,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent") or "",
    )
    if not session:
        return None
    return session.get("email") or session.get("display_name")


def mutate_inventory_product_delete(payload: dict):
    product_id = payload.get("product_id") or payload.get("id")
    if not product_id:
        return _with_status({"ok": False, "error": "product_id required"}, 400)
    try:
        result = delete_product(int(product_id))
        return {"ok": True, **(result or {})}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_inventory_product_update(request: Request, payload: dict):
    product_id = payload.get("product_id") or payload.get("id")
    try:
        name = (payload.get("name") or "").strip()
        if not product_id and not name:
            return _with_status({"ok": False, "error": "name required"}, 400)
        category_id = int(payload["categ_id"]) if payload.get("categ_id") else None
        if not category_id and payload.get("category_name"):
            cat = ensure_category(payload.get("category_name"))
            category_id = cat.get("id") if cat else None

        if product_id:
            existing_product = get_product(int(product_id))
            if not existing_product:
                return _with_status({"ok": False, "error": "product not found"}, 404)
            audit_actor = _audit_actor(request)

            def _payload_or_existing(payload_key, existing_key=None, default=None):
                if payload_key in payload:
                    val = payload.get(payload_key)
                    if val is not None and val != "":
                        return val
                    if val is None:
                        return None
                lookup_key = existing_key or payload_key
                if existing_product.get(lookup_key) is not None:
                    return existing_product.get(lookup_key)
                return default

            if "category_name" in payload and payload.get("category_name"):
                effective_category_id = category_id
            elif "categ_id" in payload:
                effective_category_id = category_id
            else:
                effective_category_id = existing_product.get("category_id")

            notes_verified = 1 if _payload_or_existing("notes_verified", "notes_verified", 0) else 0
            if "notes_verified" in payload:
                if notes_verified:
                    notes_verified_at = existing_product.get("notes_verified_at") or datetime.now(timezone.utc).isoformat()
                else:
                    notes_verified_at = None
            else:
                notes_verified_at = existing_product.get("notes_verified_at")

            update_fields = dict(
                name=name or existing_product.get("name"),
                sku=_payload_or_existing("default_code", "sku"),
                barcode=_payload_or_existing("barcode"),
                category_id=effective_category_id,
                brand=_payload_or_existing("brand"),
                gender=_payload_or_existing("gender"),
                supplier_name=_payload_or_existing("supplier_name"),
                storage_bin=_payload_or_existing("storage_bin"),
                product_type=_payload_or_existing("type", "product_type", "product"),
                cost_price=float(_payload_or_existing("standard_price", "cost_price", 0.0) or 0.0),
                retail_price=float(_payload_or_existing("list_price", "retail_price", 0.0) or 0.0),
                low_stock_threshold=float(_payload_or_existing("low_stock_threshold", "low_stock_threshold", 3.0) or 3.0),
                active=1 if _payload_or_existing("active", "active", True) else 0,
                notes=_payload_or_existing("notes"),
                notes_verified=notes_verified,
                notes_verified_at=notes_verified_at,
                description=_payload_or_existing("description"),
                script=_payload_or_existing("script"),
                note_top=_payload_or_existing("note_top"),
                note_mid=_payload_or_existing("note_mid"),
                note_base=_payload_or_existing("note_base"),
                media_url=_payload_or_existing("media_url"),
                dupe_inspiration=_payload_or_existing("dupe_inspiration"),
                dupe_confidence=_payload_or_existing("dupe_confidence"),
                dupe_classification=_payload_or_existing("dupe_classification"),
                dupe_notes=_payload_or_existing("dupe_notes"),
            )
            for field_name in TIKTOK_PRODUCT_FIELDS:
                update_fields[field_name] = _payload_or_existing(field_name)
            if payload.get("image_128"):
                update_fields["image_path"] = payload["image_128"]
            row = set_product_details(
                int(product_id),
                audit_source="inventory_api",
                audit_actor=str(audit_actor) if audit_actor is not None else None,
                audit_context={
                    "path": str(request.url.path),
                    "product_id": int(product_id),
                    "client_ip": _client_ip(request),
                },
                **update_fields,
            )
        else:
            row = upsert_product(
                name=name,
                sku=payload.get("default_code"),
                barcode=payload.get("barcode"),
                category_id=category_id,
                brand=payload.get("brand"),
                gender=payload.get("gender"),
                supplier_name=payload.get("supplier_name"),
                storage_bin=payload.get("storage_bin"),
                product_type=payload.get("type") or "product",
                cost_price=float(payload.get("standard_price") or 0.0),
                retail_price=float(payload.get("list_price") or 0.0),
                notes=payload.get("notes"),
                notes_verified=1 if payload.get("notes_verified") else 0,
                notes_verified_at=datetime.now(timezone.utc).isoformat() if payload.get("notes_verified") else None,
                description=payload.get("description"),
                script=payload.get("script"),
                note_top=payload.get("note_top"),
                note_mid=payload.get("note_mid"),
                note_base=payload.get("note_base"),
                media_url=payload.get("media_url"),
                dupe_inspiration=payload.get("dupe_inspiration"),
                dupe_confidence=payload.get("dupe_confidence"),
                dupe_classification=payload.get("dupe_classification"),
                dupe_notes=payload.get("dupe_notes"),
            )
            if payload.get("image_128"):
                row = set_product_details(int(row["id"]), image_path=payload.get("image_128"))
            tiktok_fields = {field_name: payload.get(field_name) for field_name in TIKTOK_PRODUCT_FIELDS if field_name in payload}
            if tiktok_fields:
                row = set_product_details(int(row["id"]), **tiktok_fields)

        stock_adjusted = False
        if row and "qty_available" in payload:
            current_qty = float(row.get("on_hand_qty") or 0.0)
            desired_qty = float(payload.get("qty_available") or 0.0)
            delta = desired_qty - current_qty
            if abs(delta) > 0.0001:
                adjustment_reason = str(payload.get("adjustment_reason") or "").strip() or "manual_adjustment"
                record_inventory_movement(
                    int(row["id"]),
                    "adjustment",
                    delta,
                    reason=adjustment_reason,
                    reference_type="inventory",
                    reference_id=int(row["id"]),
                )
                stock_adjusted = True
                row = get_product(int(row["id"]))

        row = row or {}
        row["default_code"] = row.get("sku")
        row["standard_price"] = row.get("cost_price")
        row["list_price"] = row.get("retail_price")
        row["qty_available"] = row.get("on_hand_qty")
        row["type"] = row.get("product_type")
        row["categ_name"] = row.get("category_name")
        row["image_url"] = _product_image_url(row)
        return {"ok": True, "stock_adjusted": stock_adjusted, "product": row}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
