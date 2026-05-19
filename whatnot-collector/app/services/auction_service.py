from server.api import _current_company_session
from server.company_db import list_auction_results, list_pending_winner_assignments


def list_results(session_id=None, limit: int = 500):
    sid = session_id
    if sid is None:
        current = _current_company_session()
        sid = int(current["id"]) if current else None
    rows = list_auction_results(session_id=sid, limit=limit)
    total_revenue = round(sum(row.get("sale_price") or 0 for row in rows), 2)
    total_fees = round(sum(row.get("fees") or 0 for row in rows), 2)
    total_profit = round(sum(row.get("profit") or 0 for row in rows), 2)
    return {
        "ok": True,
        "rows": rows,
        "total": len(rows),
        "total_revenue": total_revenue,
        "total_fees": total_fees,
        "total_profit": total_profit,
    }


def list_pending(session_id=None, limit: int = 200, statuses=None):
    sid = session_id
    if sid is None:
        current = _current_company_session()
        sid = int(current["id"]) if current else None
    rows = list_pending_winner_assignments(session_id=sid, statuses=statuses, limit=limit)
    return {"ok": True, "rows": rows, "total": len(rows)}
