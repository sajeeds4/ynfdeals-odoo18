from __future__ import annotations

from server.api import _resolve_company_session
from server.company_db import get_product_profit_rows


def get_legacy_product_profit(session_id: str | int | None = None):
    company_session = _resolve_company_session(session_id)
    rows = get_product_profit_rows(session_id=company_session["id"] if company_session else None)
    return {"rows": rows}
