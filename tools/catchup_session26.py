#!/usr/bin/env python3
"""
catchup_session26.py  — Go Live Session 26 catch-up script
============================================================
Problem:
  Odoo went offline while TikTok live was running.
  Session 26 (DB id=73) has lots up to #314, but TikTok orders
  piled up for lots 314-424 in ynf_operator_tiktok_pending.
  The 110 lots (315-424) were never created in ynf_operator_lot.

What this script does:
  1. Reads all pending records for session 26 that exceed the
     current max lot number.
  2. Creates the missing lot records (with review_later=True so
     the backfill operator can fill in product/scan data later).
  3. Applies each pending TikTok order to its lot via Odoo RPC.
  4. Calls a full TikTok API sync to pick up any orders that
     arrived after the pending queue was saved.
  5. Ensures a fresh blank lot is buffered for the live operator.

Run from the repo root:
  python3 tools/catchup_session26.py

Requires: odoo is running on localhost:8069
"""
import xmlrpc.client
import json
import sys

ODOO_URL   = "http://localhost:8069"
DB         = "YNFDEALS"
USERNAME   = "admin"
PASSWORD   = "admin"   # change if different
SESSION_ID = 73        # ynf.operator.session id for Go Live #26


def rpc_connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USERNAME, PASSWORD, {})
    if not uid:
        print("ERROR: Odoo authentication failed. Check USERNAME/PASSWORD.")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


def call(models, uid, model, method, args, kwargs=None):
    """Wrap execute_kw: args is the positional list, kwargs is the options dict."""
    return models.execute_kw(DB, uid, PASSWORD, model, method, args, kwargs or {})


def main():
    print("=== Go Live Session 26 – Catch-up Script ===\n")

    uid, models = rpc_connect()
    print(f"Authenticated as uid={uid}\n")

    # ── 1. Read the session record ──────────────────────────────────────────
    # execute_kw args: [[ids], kwargs]  — ids wrapped in list = 1 positional arg
    sessions = call(models, uid,
        "ynf.operator.session", "read",
        [[SESSION_ID]],
        {"fields": ["name", "sequence", "state", "lot_ids", "current_lot_id"]}
    )
    if not sessions:
        print(f"ERROR: Session id={SESSION_ID} not found.")
        sys.exit(1)
    session = sessions[0]
    print(f"Session: {session['name']}  state={session['state']}")

    if session["state"] == "ended":
        print("Session is ENDED — cannot create new lots. Aborting.")
        sys.exit(1)

    # ── 2. Get existing lot numbers ─────────────────────────────────────────
    lots = call(models, uid,
        "ynf.operator.lot", "search_read",
        [[("session_id", "=", SESSION_ID)]],
        {"fields": ["id", "lot_number", "state", "tiktok_order_id",
                    "buyer_username", "scan_ids", "review_later"],
         "limit": 0}
    )
    existing_lot_numbers = {l["lot_number"]: l for l in lots}
    max_lot = max(existing_lot_numbers.keys()) if existing_lot_numbers else 0
    print(f"Current max lot in DB: {max_lot}  ({len(lots)} total lots)\n")

    # ── 3. Read all pending records ─────────────────────────────────────────
    pendings = call(models, uid,
        "ynf.operator.tiktok.pending", "search_read",
        [[("session_id", "=", SESSION_ID)]],
        {"fields": ["id", "lot_number", "order_id", "seller_sku",
                    "buyer_username", "buyer_nickname", "listing_title",
                    "product_name", "payload_json"],
         "order": "lot_number asc",
         "limit": 0}
    )
    print(f"Pending TikTok orders: {len(pendings)}")
    if not pendings:
        print("No pending orders found — nothing to catch up.\n")
    else:
        pending_range = f"{pendings[0]['lot_number']} \u2013 {pendings[-1]['lot_number']}"
        print(f"Pending lot range: {pending_range}\n")

    # ── 4. Create missing lot records ───────────────────────────────────────
    missing_lot_numbers = sorted(
        set(p["lot_number"] for p in pendings) - set(existing_lot_numbers.keys())
    )
    print(f"Missing lots to create: {len(missing_lot_numbers)}")

    created = []
    for lot_num in missing_lot_numbers:
        matching_pending = next(
            (p for p in pendings if p["lot_number"] == lot_num), None
        )
        # create() takes [vals_dict] as the single positional arg
        new_lot_id = call(models, uid,
            "ynf.operator.lot", "create",
            [{
                "session_id":   SESSION_ID,
                "lot_number":   lot_num,
                "state":        "open",
                "review_later": True,
            }]
        )
        created.append((lot_num, new_lot_id))
        buyer_hint = ""
        if matching_pending:
            buyer_hint = f" [{matching_pending['buyer_username'] or matching_pending['buyer_nickname']}]"
        print(f"  Created lot #{lot_num} (id={new_lot_id}){buyer_hint}")

    if created:
        print(f"\n\u2713 Created {len(created)} missing lots.\n")

    # ── 5. Apply pending TikTok orders to each lot ──────────────────────────
    print("Applying pending TikTok orders to lots \u2026")
    applied = skipped = errors = 0

    for pending in pendings:
        lot_num = pending["lot_number"]
        try:
            # Custom method: execute_kw args = [[session_id], lot_number]
            result = call(models, uid,
                "ynf.operator.session",
                "action_apply_pending_tiktok_order_for_lot",
                [[SESSION_ID], lot_num]
            )
            if isinstance(result, dict):
                if result.get("applied"):
                    applied += 1
                    buyer = pending.get("buyer_username") or pending.get("buyer_nickname") or "?"
                    print(f"  Lot #{lot_num}: applied  buyer={buyer}")
                else:
                    skipped += 1
                    print(f"  Lot #{lot_num}: skipped (lot not ready yet)")
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            print(f"  Lot #{lot_num}: ERROR \u2013 {e}")

    print(f"\n\u2713 Applied={applied}  Skipped={skipped}  Errors={errors}\n")

    # ── 6. Full TikTok API sync to pick up any orders since last pull ────────
    print("Running full TikTok order sync via API \u2026")
    try:
        sync_result = call(models, uid,
            "ynf.operator.session", "action_sync_tiktok_orders",
            [[SESSION_ID]]
        )
        if isinstance(sync_result, dict):
            params = sync_result.get("params", {})
            print(f"  Sync result: {params.get('message', sync_result)}")
    except Exception as e:
        print(f"  Sync WARNING: {e}")

    # ── 7. Apply any newly queued pending orders after API sync ─────────────
    pendings_after = call(models, uid,
        "ynf.operator.tiktok.pending", "search_read",
        [[("session_id", "=", SESSION_ID)]],
        {"fields": ["id", "lot_number", "buyer_username", "buyer_nickname"],
         "order": "lot_number asc",
         "limit": 0}
    )
    if pendings_after:
        print(f"\nStill {len(pendings_after)} pending after sync \u2014 applying \u2026")
        for pending in pendings_after:
            lot_num = pending["lot_number"]
            try:
                result = call(models, uid,
                    "ynf.operator.session",
                    "action_apply_pending_tiktok_order_for_lot",
                    [[SESSION_ID], lot_num]
                )
                if isinstance(result, dict) and result.get("applied"):
                    applied += 1
                    buyer = pending.get("buyer_username") or pending.get("buyer_nickname") or "?"
                    print(f"  Lot #{lot_num}: applied  buyer={buyer}")
            except Exception as e:
                print(f"  Lot #{lot_num}: ERROR \u2013 {e}")

    # ── 8. Final summary ─────────────────────────────────────────────────────
    final_lots = call(models, uid,
        "ynf.operator.lot", "search_read",
        [[("session_id", "=", SESSION_ID)]],
        {"fields": ["lot_number", "state", "tiktok_order_id",
                    "buyer_username", "buyer_nickname", "sale_price",
                    "tiktok_status", "review_later"],
         "limit": 0}
    )
    final_pendings = call(models, uid,
        "ynf.operator.tiktok.pending", "search_read",
        [[("session_id", "=", SESSION_ID)]],
        {"fields": ["lot_number"],
         "limit": 0}
    )

    won    = sum(1 for l in final_lots if l["state"] == "won")
    open_  = sum(1 for l in final_lots if l["state"] == "open")
    review = sum(1 for l in final_lots if l["review_later"])
    total  = len(final_lots)
    max_n  = max((l["lot_number"] for l in final_lots), default=0)
    revenue= sum(l["sale_price"] or 0 for l in final_lots
                 if l.get("tiktok_status") != "cancelled" and l["state"] != "void")

    print("\n=== SUMMARY ===")
    print(f"Total lots in DB : {total}  (max lot# {max_n})")
    print(f"Won (to_ship)    : {won}")
    print(f"Open (active)    : {open_}")
    print(f"Review Later     : {review}  ← backfill these")
    print(f"Still pending    : {len(final_pendings)}")
    print(f"Revenue total    : ${revenue:,.2f}")
    print()

    if final_pendings:
        pending_nums = sorted(p["lot_number"] for p in final_pendings)
        print(f"WARNING: {len(final_pendings)} orders still pending (not applied).")
        print(f"  Lots: {pending_nums[:20]}{'...' if len(pending_nums) > 20 else ''}")
        print("  → These lots may not have scans yet. Mark them review_later")
        print("    and run action_apply_pending_tiktok_order_for_lot again after scan.")
    else:
        print("✓ All pending TikTok orders have been applied.")

    print("\nDone. The live operator can continue scanning.")


if __name__ == "__main__":
    main()
