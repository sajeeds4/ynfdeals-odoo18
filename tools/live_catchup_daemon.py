#!/usr/bin/env python3
"""
live_catchup_daemon.py  — continuous lot catch-up for Go Live Session 26
=========================================================================
Runs in a tight loop: every POLL_SECONDS it checks ynf_operator_tiktok_pending
for session 26, creates any missing lot records, and applies the TikTok order
data.  Also triggers a full TikTok API re-sync every SYNC_EVERY_N_POLLS cycles.

Run:
  python3 tools/live_catchup_daemon.py

Stop with Ctrl+C.
"""
import time
import xmlrpc.client
import sys

ODOO_URL       = "http://localhost:8069"
DB             = "YNFDEALS"
USERNAME       = "admin"
PASSWORD       = "admin"
SESSION_ID     = 73           # Go Live #26

POLL_SECONDS   = 2            # how often to check for new pending orders
SYNC_EVERY_N   = 15           # run full TikTok API sync every N polls (~60s)

# ── RPC helpers ─────────────────────────────────────────────────────────────

def rpc_connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USERNAME, PASSWORD, {})
    if not uid:
        print("ERROR: Odoo authentication failed.")
        sys.exit(1)
    mdl = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, mdl


def call(mdl, uid, model, method, args, kwargs=None):
    return mdl.execute_kw(DB, uid, PASSWORD, model, method, args, kwargs or {})


# ── Core catch-up logic (one cycle) ─────────────────────────────────────────

def ensure_fresh_buffer_lot(mdl, uid):
    """
    Guarantee exactly one blank (no scan, no TikTok data, no review_later) lot
    exists at the TOP of the lot stack so the operator always has somewhere to
    scan the next product.

    Strategy:
      • Any blank lot whose lot_number is NOT the maximum lot_number gets marked
        review_later=True (it's stale — a missed scan from earlier in the show).
      • If the highest lot already has TikTok data (i.e., no blank at the top),
        create a new blank lot at max+1 and point current_lot_id at it.
    """
    all_lots = call(mdl, uid,
        "ynf.operator.lot", "search_read",
        [[("session_id", "=", SESSION_ID)]],
        {"fields": ["id", "lot_number", "state", "review_later",
                    "tiktok_order_id", "tiktok_seller_sku",
                    "buyer_username", "buyer_nickname"],
         "limit": 0}
    )
    if not all_lots:
        return

    max_lot_num = max(l["lot_number"] for l in all_lots)

    # A lot is "blank" (suitable as a scan buffer) if it has no TikTok data,
    # no review_later flag, and is open.
    def is_blank(l):
        return (
            not l["review_later"]
            and not (l["tiktok_order_id"] or "").strip()
            and not (l["tiktok_seller_sku"] or "").strip()
            and not (l["buyer_username"] or "").strip()
            and not (l["buyer_nickname"] or "").strip()
        )

    blank_lots = [l for l in all_lots if is_blank(l)]

    # Mark any blank lot that is behind the max as review_later (stale)
    stale = [l for l in blank_lots if l["lot_number"] < max_lot_num]
    if stale:
        stale_ids = [l["id"] for l in stale]
        call(mdl, uid, "ynf.operator.lot", "write",
             [stale_ids, {"review_later": True}])
        for l in stale:
            print(f"  [buffer]   lot #{l['lot_number']} marked review_later (stale blank)")

    # Check if the top lot is already a fresh blank
    top_blanks = [l for l in blank_lots if l["lot_number"] == max_lot_num]
    if top_blanks:
        # Already have a blank at the top — make sure current_lot_id points to it
        call(mdl, uid, "ynf.operator.session", "write",
             [[SESSION_ID], {"current_lot_id": top_blanks[0]["id"]}])
        return

    # No blank at the top — create one
    new_lot_num = max_lot_num + 1
    new_lot_id = call(mdl, uid,
        "ynf.operator.lot", "create",
        [{"session_id": SESSION_ID,
          "lot_number": new_lot_num,
          "state":      "open"}]
    )
    call(mdl, uid, "ynf.operator.session", "write",
         [[SESSION_ID], {"current_lot_id": new_lot_id}])
    print(f"  [buffer]   created blank lot #{new_lot_num} (id={new_lot_id}) — ready to scan")


def catchup_cycle(mdl, uid, do_api_sync=False):
    # 1. Fetch all pending orders for this session
    pendings = call(mdl, uid,
        "ynf.operator.tiktok.pending", "search_read",
        [[("session_id", "=", SESSION_ID)]],
        {"fields": ["id", "lot_number", "buyer_username", "buyer_nickname"],
         "order": "lot_number asc",
         "limit": 0}
    )

    # 2. Fetch existing lot numbers (just the numbers, fast)
    existing = call(mdl, uid,
        "ynf.operator.lot", "search_read",
        [[("session_id", "=", SESSION_ID)]],
        {"fields": ["id", "lot_number", "review_later",
                    "tiktok_order_id", "buyer_username"],
         "limit": 0}
    )
    existing_nums = {l["lot_number"] for l in existing}

    # 3. Create any missing lots (with review_later so TikTok data can be applied)
    missing = sorted(
        p["lot_number"] for p in pendings
        if p["lot_number"] not in existing_nums
    )
    created = 0
    for lot_num in missing:
        call(mdl, uid,
            "ynf.operator.lot", "create",
            [{"session_id": SESSION_ID,
              "lot_number": lot_num,
              "state":       "open",
              "review_later": True}]
        )
        created += 1
        pending = next((p for p in pendings if p["lot_number"] == lot_num), {})
        buyer = pending.get("buyer_username") or pending.get("buyer_nickname") or "?"
        print(f"  [new lot] #{lot_num}  buyer={buyer}")

    # 4. Optionally run full TikTok API sync (pulls latest from TikTok)
    if do_api_sync:
        try:
            result = call(mdl, uid,
                "ynf.operator.session", "action_sync_tiktok_orders",
                [[SESSION_ID]]
            )
            msg = (result or {}).get("params", {}).get("message", "done")
            print(f"  [api sync] {msg}")
        except Exception as e:
            print(f"  [api sync] WARNING: {e}")
        # Re-fetch pending after sync (may have new ones)
        pendings = call(mdl, uid,
            "ynf.operator.tiktok.pending", "search_read",
            [[("session_id", "=", SESSION_ID)]],
            {"fields": ["id", "lot_number", "buyer_username", "buyer_nickname"],
             "order": "lot_number asc",
             "limit": 0}
        )

    # 5. Apply all pending orders
    applied = 0
    for pending in pendings:
        lot_num = pending["lot_number"]
        try:
            result = call(mdl, uid,
                "ynf.operator.session",
                "action_apply_pending_tiktok_order_for_lot",
                [[SESSION_ID], lot_num]
            )
            if isinstance(result, dict) and result.get("applied"):
                applied += 1
                buyer = pending.get("buyer_username") or pending.get("buyer_nickname") or "?"
                print(f"  [applied]  lot #{lot_num}  buyer={buyer}")
        except Exception as e:
            print(f"  [error]    lot #{lot_num}: {e}")

    # 6. Always ensure a fresh blank lot exists at the top for the operator
    ensure_fresh_buffer_lot(mdl, uid)

    return created, applied


def ensure_buffer_only(mdl, uid):
    """Fast path: just ensure the buffer lot when there's nothing else to do."""
    ensure_fresh_buffer_lot(mdl, uid)


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    print("=== Go Live Session 26 – Live Catch-up Daemon ===")
    print(f"Polling every {POLL_SECONDS}s  |  API sync every {SYNC_EVERY_N * POLL_SECONDS}s")
    print("Press Ctrl+C to stop.\n")

    uid, mdl = rpc_connect()
    print(f"Connected (uid={uid})\n")

    poll_count = 0
    total_created = 0
    total_applied = 0

    while True:
        poll_count += 1
        do_sync = (poll_count % SYNC_EVERY_N == 1)  # sync on 1st, then every N

        try:
            created, applied = catchup_cycle(mdl, uid, do_api_sync=do_sync)
            if not created and not applied and not do_sync:
                # Still ensure buffer even on idle cycles
                ensure_fresh_buffer_lot(mdl, uid)
            total_created += created
            total_applied += applied

            if created or applied or do_sync:
                # Quick DB stats
                stats = call(mdl, uid,
                    "ynf.operator.lot", "search_read",
                    [[("session_id", "=", SESSION_ID)]],
                    {"fields": ["lot_number", "tiktok_status", "state"],
                     "limit": 0}
                )
                max_lot  = max((l["lot_number"] for l in stats), default=0)
                won      = sum(1 for l in stats if l["state"] == "won")
                open_    = sum(1 for l in stats if l["state"] == "open")
                pending_left = call(mdl, uid,
                    "ynf.operator.tiktok.pending", "search_read",
                    [[("session_id", "=", SESSION_ID)]],
                    {"fields": ["lot_number"], "limit": 0}
                )
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] lots={len(stats)} max=#{max_lot} "
                      f"won={won} open={open_} "
                      f"pending={len(pending_left)} "
                      f"+created={created} +applied={applied}")

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] cycle error: {e}")
            # Reconnect on error
            try:
                uid, mdl = rpc_connect()
            except Exception:
                pass

        try:
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            break

    print(f"\nStopped. Total: created={total_created}  applied={total_applied}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDaemon stopped by user.")
