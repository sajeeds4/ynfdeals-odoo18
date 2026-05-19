from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from server.api import OUR_WHATNOT_ACCOUNT, _annotate_whatnot_packing_slip_pdf, _build_sale_order_picklist_payload, _current_company_session, _resolve_company_session
from server.company_db import (
    add_pick_list_item,
    add_sale_order_line_for_item,
    approve_in_house_order,
    approve_payments_from_picklist_lots,
    cancel_in_house_order,
    create_employee_pos_token,
    create_in_house_order,
    create_in_house_sale,
    create_pick_list,
    create_sale_order,
    find_existing_sale_order,
    find_product_by_code,
    get_company_session,
    get_employee_pos_token,
    get_inventory_prep_overview,
    in_house_orders_summary,
    in_house_sales_summary,
    list_employee_pos_tokens,
    list_in_house_buyer_profiles,
    list_in_house_orders,
    list_internal_pos_products,
    list_auction_results,
    list_buyer_groups,
    list_company_sessions,
    list_sale_order_lines,
    list_sale_orders,
    record_inventory_movement,
    reject_in_house_order,
    revoke_employee_pos_token,
    reverse_sale_order_inventory,
    rotate_employee_pos_token,
    split_in_house_order,
    get_in_house_order,
    merge_in_house_orders,
    update_in_house_order,
    update_sale_order,
    upsert_customer,
)
from server.auth import audit_auth_event, _qr_code_data_url
from server.packing_slip import match_lots_to_products, parse_packing_slip_pdf


def _with_status(payload: dict[str, Any], status: int | None = None):
    if status is not None:
        payload["_status"] = status
    return payload


def _safe_pos_token_context(row):
    if not row:
        return row
    clean = dict(row)
    clean.pop("token", None)
    clean.pop("token_hash", None)
    return clean


def _normalize_public_identity(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _normalize_public_phone(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _guest_in_house_order_access_allowed(order, buyer_name=None, buyer_phone=None, buyer_email=None):
    if not order:
        return False
    target_name = _normalize_public_identity(buyer_name)
    target_phone = _normalize_public_phone(buyer_phone)
    target_email = _normalize_public_identity(buyer_email)
    row_name = _normalize_public_identity(order.get("employee_name"))
    row_phone = _normalize_public_phone(order.get("buyer_phone"))
    row_email = _normalize_public_identity(order.get("buyer_email"))
    if target_phone and row_phone and target_phone == row_phone:
        return True
    if target_email and row_email and target_email == row_email:
        return True
    if target_name and row_name and target_name == row_name:
        return True
    return False


def get_legacy_qr_code(value: str | None = None):
    clean = str(value or "").strip()
    if not clean:
        return _with_status({"ok": False, "error": "value required"}, 400)
    try:
        return {"ok": True, "value": clean, "qr_code_data_url": _qr_code_data_url(clean)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def _cancel_missing_picklist_orders(effective_sid: int | None, shipments: list[dict[str, Any]]):
    if not effective_sid:
        return 0
    pdf_usernames = {(s.get("username") or "").strip().lower() for s in shipments if s.get("username")}
    pdf_lots = {
        str(item.get("lot_number") or "").strip()
        for ship in shipments
        for item in (ship.get("items") or [])
        if str(item.get("lot_number") or "").strip()
    }
    orders_cancelled = 0
    all_session_orders = list_sale_orders(session_id=effective_sid)
    for so in all_session_orders:
        if so.get("state") == "cancel":
            continue
        order_lines = list_sale_order_lines(int(so["id"])) or []
        order_lots = {
            str(line.get("lot_number") or "").strip()
            for line in order_lines
            if str(line.get("lot_number") or "").strip()
        }
        buyer = (so.get("whatnot_buyer_username") or "").strip().lower()
        should_cancel = False
        if order_lots:
            should_cancel = order_lots.isdisjoint(pdf_lots)
        elif buyer:
            should_cancel = buyer not in pdf_usernames
        if should_cancel:
            update_sale_order(int(so["id"]), state="cancel", fulfillment_status="pending", payment_status="unpaid")
            reverse_sale_order_inventory(int(so["id"]))
            orders_cancelled += 1
    return orders_cancelled


def get_legacy_company_prep():
    try:
        data = get_inventory_prep_overview()
        return {"ok": True, **data}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_users_follow(username: str | None):
    return _with_status({"ok": False, "error": "whatnot_follow_retired"}, 410)


def mutate_legacy_picklist_upload(raw: bytes, session_id: int | None = None, filename: str | None = None):
    if not raw:
        return _with_status({"ok": False, "error": "empty_body"}, 400)
    if len(raw) > 30 * 1024 * 1024:
        return _with_status({"ok": False, "error": "file_too_large"}, 400)
    if not raw[:5].startswith(b"%PDF"):
        return _with_status({"ok": False, "error": "not_a_pdf"}, 400)
    try:
        shipments = parse_packing_slip_pdf(raw)
    except Exception as exc:
        return _with_status({"ok": False, "error": f"pdf_parse_error: {exc}"}, 400)
    if not shipments:
        return _with_status({"ok": False, "error": "no_packing_slips_found"}, 400)

    sid = int(session_id) if session_id else None
    auction_rows = list_auction_results(session_id=sid, limit=9999)
    shipments = match_lots_to_products(shipments, auction_rows)

    effective_sid = sid
    if not effective_sid:
        sessions = list_company_sessions()
        ended = [s for s in sessions if s.get("status") == "ended"]
        if ended:
            effective_sid = ended[0]["id"]

    customers_synced = 0
    orders_synced = 0
    inventory_deducted = 0
    payment_approvals = {"approved_lots": 0, "approved_orders": 0, "assignment_ids": []}

    if effective_sid:
        label_lots = [
            item.get("lot_number")
            for ship in shipments
            for item in (ship.get("items") or [])
            if item.get("lot_number")
        ]
        payment_approvals = approve_payments_from_picklist_lots(effective_sid, label_lots)

    for si, ship in enumerate(shipments):
        username = (ship.get("username") or "").strip()
        if not username:
            continue
        cust = upsert_customer(
            whatnot_username=username,
            display_name=ship.get("buyer_name") or None,
            address=ship.get("address") or None,
        )
        ship["customer_id"] = cust["id"]
        customers_synced += 1

        if effective_sid:
            so = find_existing_sale_order(effective_sid, username)
            if not so:
                so = create_sale_order(
                    session_id=effective_sid,
                    customer_id=cust["id"],
                    whatnot_buyer_username=username,
                    state="sale",
                )
            ship["sale_order_id"] = so["id"]
            ship["order_number"] = so.get("order_number")
            tracking = ship.get("tracking_number")
            update_fields = {
                "state": "sale",
                "fulfillment_status": "shipped",
                "payment_status": "paid",
                "customer_id": cust["id"],
                "shipped_at": datetime.now(timezone.utc).isoformat(),
            }
            if tracking:
                update_fields["tracking_number"] = tracking
                update_fields["tracking_status"] = "shipped"
                update_fields["tracking_last_checked_at"] = datetime.now(timezone.utc).isoformat()
            if ship.get("shipping_method"):
                update_fields["tracking_carrier"] = (ship.get("shipping_method") or "").strip().lower()
            update_sale_order(so["id"], **update_fields)
            orders_synced += 1

            existing_lines = list_sale_order_lines(so["id"])
            existing_lot_keys = set()
            for ln in existing_lines:
                desc = (ln.get("description") or "").strip()
                existing_lot_keys.add(desc)

            for item in ship["items"]:
                if not item.get("matched"):
                    continue
                desc = item.get("product_name") or f"Lot #{item['lot_number']}"
                if desc.strip() in existing_lot_keys:
                    continue
                existing_lot_keys.add(desc.strip())
                product_id = None
                if item.get("barcode"):
                    prod = find_product_by_code(item["barcode"])
                    if prod:
                        product_id = prod["id"]
                elif item.get("sku"):
                    prod = find_product_by_code(item["sku"])
                    if prod:
                        product_id = prod["id"]
                add_sale_order_line_for_item(
                    so["id"],
                    product_id=product_id,
                    description=desc,
                    qty=1,
                    unit_price=item.get("price", 0),
                    lot_id=item.get("lot_id"),
                    auction_result_id=item.get("auction_result_id"),
                )
                if product_id:
                    try:
                        record_inventory_movement(
                            product_id,
                            "out",
                            -1,
                            reason=f"Packing slip: Lot #{item['lot_number']} -> @{username}",
                            reference_type="sale_order",
                            reference_id=so["id"],
                        )
                        inventory_deducted += 1
                    except Exception:
                        pass

    orders_cancelled = _cancel_missing_picklist_orders(effective_sid, shipments)

    total_lots = sum(len(s.get("items") or []) for s in shipments)
    matched = sum(1 for s in shipments for i in (s.get("items") or []) if i.get("matched"))
    unmatched = total_lots - matched

    pick_list = create_pick_list(
        session_id=effective_sid,
        filename=filename,
        total_shipments=len(shipments),
        total_lots=total_lots,
        matched_lots=matched,
        unmatched_lots=unmatched,
        total_revenue=sum(s.get("total_price") or 0 for s in shipments),
        customers_synced=customers_synced,
        orders_synced=orders_synced,
        inventory_deducted=inventory_deducted,
    )

    for si, ship in enumerate(shipments):
        for item in ship.get("items") or []:
            add_pick_list_item(
                pick_list_id=pick_list["id"],
                shipment_index=si,
                username=ship.get("username"),
                buyer_name=ship.get("buyer_name"),
                address=ship.get("address"),
                tracking_number=ship.get("tracking_number"),
                shipping_method=ship.get("shipping_method"),
                ship_date=ship.get("ship_date"),
                weight=ship.get("weight"),
                lot_number=item.get("lot_number"),
                product_name=item.get("product_name"),
                barcode=item.get("barcode"),
                sku=item.get("sku"),
                sale_price=item.get("price", 0),
                order_id=item.get("order_id"),
                matched=1 if item.get("matched") else 0,
                sale_order_id=ship.get("sale_order_id"),
                customer_id=ship.get("customer_id"),
            )

    return {
        "ok": True,
        "pick_list_id": pick_list["id"],
        "shipments": shipments,
        "summary": {
            "total_shipments": len(shipments),
            "total_lots": total_lots,
            "matched": matched,
            "unmatched": unmatched,
            "total_revenue": sum(s.get("total_price") or 0 for s in shipments),
            "customers_synced": customers_synced,
            "orders_synced": orders_synced,
            "inventory_deducted": inventory_deducted,
            "orders_cancelled": orders_cancelled,
            "payments_approved": payment_approvals.get("approved_lots", 0),
            "payment_approval_orders": payment_approvals.get("approved_orders", 0),
            "session_id": effective_sid,
            "pick_list_id": pick_list["id"],
        },
    }


def render_legacy_picklist_enriched_pdf(raw: bytes, session_id: int | None = None, filename: str | None = None):
    if not raw:
        return _with_status({"ok": False, "error": "empty_body"}, 400)
    if len(raw) > 60 * 1024 * 1024:
        return _with_status({"ok": False, "error": "file_too_large"}, 400)
    if not raw[:5].startswith(b"%PDF"):
        return _with_status({"ok": False, "error": "not_a_pdf"}, 400)
    try:
        output, annotated_pages, total_pages = _annotate_whatnot_packing_slip_pdf(raw, session_id=session_id)
    except Exception as exc:
        return _with_status({"ok": False, "error": f"pdf_label_enrich_error: {exc}"}, 400)
    if annotated_pages <= 0:
        return _with_status({
            "ok": False,
            "error": "No Whatnot packing slip pages were found in this PDF, or no matched product names were available for overlay.",
        }, 400)
    safe_name = (filename or "whatnot-packing-slip.pdf").strip() or "whatnot-packing-slip.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    if "with-product" not in safe_name.lower():
        safe_name = safe_name[:-4] + "-with-products.pdf"
    return {
        "ok": True,
        "content": output,
        "filename": safe_name,
        "annotated_pages": annotated_pages,
        "total_pages": total_pages,
    }


def mutate_legacy_in_house_sale(payload: dict[str, Any]):
    try:
        sale = create_in_house_sale(
            employee_name=payload.get("employee_name"),
            employee_id=payload.get("employee_id"),
            product_id=payload.get("product_id"),
            barcode=payload.get("barcode"),
            sku=payload.get("sku"),
            qty=payload.get("qty") or 1,
            unit_price=payload.get("unit_price"),
            notes=payload.get("notes"),
            sold_at=payload.get("sold_at") or datetime.now(timezone.utc).isoformat(),
        )
        return {"ok": True, "sale": sale, **in_house_sales_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_create_pos_token(payload: dict[str, Any]):
    try:
        token_row = create_employee_pos_token(
            employee_id=payload.get("employee_id"),
            employee_name=payload.get("employee_name"),
            device_label=payload.get("device_label"),
            expires_at=payload.get("expires_at"),
        )
        audit_auth_event(
            "pos_token_created",
            token_id=token_row.get("id"),
            employee_id=token_row.get("employee_id"),
            employee_name=token_row.get("employee_name"),
            expires_at=token_row.get("expires_at"),
        )
        return {"ok": True, "token": token_row}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_employee_pos_tokens(employee_id=None, employee_name=None):
    try:
        rows = list_employee_pos_tokens(employee_id=employee_id, employee_name=employee_name)
        return {"ok": True, "rows": rows}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_revoke_pos_token(payload: dict[str, Any]):
    try:
        row = revoke_employee_pos_token(payload.get("id"), revoked_by=payload.get("revoked_by"))
        audit_auth_event(
            "pos_token_revoked",
            token_id=row.get("id"),
            employee_id=row.get("employee_id"),
            employee_name=row.get("employee_name"),
            actor_email=payload.get("revoked_by"),
        )
        return {"ok": True, "token": row}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_rotate_pos_token(payload: dict[str, Any]):
    try:
        token_row = rotate_employee_pos_token(
            payload.get("id"),
            revoked_by=payload.get("rotated_by"),
            device_label=payload.get("device_label"),
            expires_at=payload.get("expires_at"),
        )
        audit_auth_event(
            "pos_token_rotated",
            old_token_id=payload.get("id"),
            token_id=token_row.get("id"),
            employee_id=token_row.get("employee_id"),
            employee_name=token_row.get("employee_name"),
            actor_email=payload.get("rotated_by"),
            expires_at=token_row.get("expires_at"),
        )
        return {"ok": True, "token": token_row}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_internal_pos_me(token: str | None):
    clean = str(token or "").strip()
    if not clean:
        return {"ok": True, "guest": True, "employee": {"employee_name": "Guest Self Checkout", "role": "guest"}}
    try:
        employee = get_employee_pos_token(clean)
        if not employee:
            audit_auth_event("pos_token_invalid", path="/api/internal_pos/me")
            return _with_status({"ok": False, "error": "invalid employee POS token"}, 404)
        audit_auth_event("pos_token_used", path="/api/internal_pos/me", token_id=employee.get("id"), employee_id=employee.get("employee_id"), employee_name=employee.get("employee_name"))
        return {"ok": True, "employee": _safe_pos_token_context(employee)}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_internal_pos_products(token: str | None, q: str | None = None, code: str | None = None):
    clean = str(token or "").strip()
    if not clean:
        return _with_status({"ok": False, "error": "token required"}, 400)
    try:
        token_row = get_employee_pos_token(clean)
        if not token_row:
            audit_auth_event("pos_token_invalid", path="/api/internal_pos/products")
            return _with_status({"ok": False, "error": "invalid employee POS token"}, 404)
        audit_auth_event("pos_token_used", path="/api/internal_pos/products", token_id=token_row.get("id"), employee_id=token_row.get("employee_id"), employee_name=token_row.get("employee_name"))
        rows = list_internal_pos_products(q=q or None, code=code or None, limit=80)
        return {"ok": True, "rows": rows}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_internal_pos_buyers(q: str | None = None):
    try:
        rows = list_in_house_buyer_profiles(q=q or None, limit=50)
        return {"ok": True, "rows": rows}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_internal_pos_orders_mine(token: str | None):
    clean = str(token or "").strip()
    if not clean:
        return _with_status({"ok": False, "error": "token required"}, 400)
    try:
        token_row = get_employee_pos_token(clean)
        if not token_row:
            audit_auth_event("pos_token_invalid", path="/api/internal_pos/orders/mine")
            return _with_status({"ok": False, "error": "invalid employee POS token"}, 404)
        audit_auth_event("pos_token_used", path="/api/internal_pos/orders/mine", token_id=token_row.get("id"), employee_id=token_row.get("employee_id"), employee_name=token_row.get("employee_name"))
        rows = list_in_house_orders(token=clean, limit=100)
        return {"ok": True, "rows": rows, "summary": in_house_orders_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_internal_pos_orders_history(employee_id: int | None = None, buyer_name: str | None = None, buyer_phone: str | None = None, buyer_email: str | None = None):
    try:
        rows = list_in_house_orders(
            employee_id=employee_id if employee_id else None,
            buyer_name=buyer_name or None,
            limit=100,
        )
        if buyer_name:
            rows = [
                row for row in rows
                if _guest_in_house_order_access_allowed(row, buyer_name=buyer_name, buyer_phone=buyer_phone, buyer_email=buyer_email)
            ]
        return {"ok": True, "rows": rows, "summary": in_house_orders_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def get_legacy_internal_pos_order_detail(order_id: int | None, buyer_name: str | None = None, buyer_phone: str | None = None, buyer_email: str | None = None):
    if not order_id or not str(buyer_name or "").strip():
        return _with_status({"ok": False, "error": "id and buyer_name required"}, 400)
    try:
        order = get_in_house_order(int(order_id))
        if not order or not _guest_in_house_order_access_allowed(order, buyer_name=buyer_name, buyer_phone=buyer_phone, buyer_email=buyer_email):
            return _with_status({"ok": False, "error": "order not found"}, 404)
        return {"ok": True, "order": order}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_internal_pos_orders(payload: dict[str, Any]):
    token = str(payload.get("token") or "").strip()
    if not token:
        return _with_status({"ok": False, "error": "token required"}, 400)
    try:
        order = create_in_house_order(
            token=token,
            employee_name=payload.get("employee_name"),
            lines=payload.get("lines") or [],
            payment_method=payload.get("payment_method") or ("payroll" if token else "cash"),
            notes=payload.get("notes"),
            discount_amount=payload.get("discount_amount") or 0,
            buyer_type=payload.get("buyer_type"),
            buyer_phone=payload.get("buyer_phone"),
            buyer_email=payload.get("buyer_email"),
            tax_amount=payload.get("tax_amount") or 0,
        )
        audit_auth_event(
            "pos_order_submitted",
            order_id=order.get("id") if isinstance(order, dict) else None,
            employee_id=order.get("employee_id") if isinstance(order, dict) else None,
            employee_name=order.get("employee_name") if isinstance(order, dict) else None,
            line_count=len(payload.get("lines") or []),
        )
        return {"ok": True, "order": order, "summary": in_house_orders_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_internal_pos_orders_update(payload: dict[str, Any]):
    try:
        order = get_in_house_order(int(payload.get("id") or 0))
        if not order or not _guest_in_house_order_access_allowed(
            order,
            buyer_name=payload.get("buyer_name"),
            buyer_phone=payload.get("buyer_phone"),
            buyer_email=payload.get("buyer_email"),
        ):
            return _with_status({"ok": False, "error": "order not found"}, 404)
        if str(order.get("status") or "") not in {"pending_approval", "draft"}:
            return _with_status({"ok": False, "error": "only draft or pending invoices can be edited"}, 400)
        updated = update_in_house_order(
            int(payload.get("id")),
            lines=payload.get("lines") or [],
            payment_method=payload.get("payment_method"),
            notes=payload.get("notes"),
            discount_amount=payload.get("discount_amount") or 0,
            buyer_type=payload.get("buyer_type"),
            buyer_phone=payload.get("buyer_phone"),
            buyer_email=payload.get("buyer_email"),
            tax_amount=payload.get("tax_amount") or 0,
        )
        return {"ok": True, "order": updated, "summary": in_house_orders_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_internal_pos_orders_split(payload: dict[str, Any]):
    try:
        order = get_in_house_order(int(payload.get("id") or 0))
        if not order or not _guest_in_house_order_access_allowed(
            order,
            buyer_name=payload.get("buyer_name"),
            buyer_phone=payload.get("buyer_phone"),
            buyer_email=payload.get("buyer_email"),
        ):
            return _with_status({"ok": False, "error": "order not found"}, 404)
        if str(order.get("status") or "") not in {"pending_approval", "draft"}:
            return _with_status({"ok": False, "error": "only draft or pending invoices can be split"}, 400)
        result = split_in_house_order(int(payload.get("id")), payload.get("line_items") or payload.get("line_ids") or [])
        return {"ok": True, **result, "summary": in_house_orders_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_internal_pos_orders_merge(payload: dict[str, Any]):
    try:
        source = get_in_house_order(int(payload.get("source_id") or 0))
        target = get_in_house_order(int(payload.get("target_id") or 0))
        if (
            not source
            or not target
            or not _guest_in_house_order_access_allowed(source, buyer_name=payload.get("buyer_name"), buyer_phone=payload.get("buyer_phone"), buyer_email=payload.get("buyer_email"))
            or not _guest_in_house_order_access_allowed(target, buyer_name=payload.get("buyer_name"), buyer_phone=payload.get("buyer_phone"), buyer_email=payload.get("buyer_email"))
        ):
            return _with_status({"ok": False, "error": "source or target not found"}, 404)
        if str(source.get("status") or "") not in {"pending_approval", "draft"} or str(target.get("status") or "") not in {"pending_approval", "draft"}:
            return _with_status({"ok": False, "error": "only draft or pending invoices can be merged"}, 400)
        result = merge_in_house_orders(int(payload.get("source_id")), int(payload.get("target_id")))
        return {"ok": True, **result, "summary": in_house_orders_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_in_house_order_approve(payload: dict[str, Any]):
    try:
        order = approve_in_house_order(payload.get("id"), approved_by=payload.get("approved_by"))
        return {"ok": True, "order": order, "summary": in_house_orders_summary(), "sales": in_house_sales_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_in_house_order_reject(payload: dict[str, Any]):
    try:
        order = reject_in_house_order(
            payload.get("id"),
            rejected_by=payload.get("rejected_by"),
            rejection_reason=payload.get("rejection_reason"),
        )
        return {"ok": True, "order": order, "summary": in_house_orders_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_in_house_order_cancel(payload: dict[str, Any]):
    try:
        order = cancel_in_house_order(payload.get("id"))
        return {"ok": True, "order": order, "summary": in_house_orders_summary()}
    except ValueError as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_ensure_sale_order(payload: dict[str, Any]):
    group_id = payload.get("group_id")
    if not group_id:
        return _with_status({"ok": False, "error": "group_id required"}, 400)
    try:
        group = next((g for g in list_buyer_groups() if int(g["id"]) == int(group_id)), None)
        if not group:
            return _with_status({"ok": False, "error": "group_not_found"}, 404)
        if group.get("sale_order_id"):
            so_id = int(group["sale_order_id"])
            so = next((o for o in list_sale_orders() if int(o["id"]) == so_id), None)
            return {"ok": True, "sale_order_id": so_id, "sale_order_name": so.get("order_number") if so else str(so_id)}
        order = create_sale_order(
            session_id=group.get("session_id"),
            customer_id=group.get("customer_id"),
            buyer_group_id=group.get("id"),
            whatnot_buyer_username=group.get("buyer_username"),
            state="draft",
            ordered_at=datetime.now(timezone.utc).isoformat(),
        )
        return {"ok": True, "sale_order_id": order.get("id"), "sale_order_name": order.get("order_number")}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
