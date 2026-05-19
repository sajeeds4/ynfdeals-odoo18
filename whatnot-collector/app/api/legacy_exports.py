from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from app.services.legacy_export_service import (
    build_auction_results_csv,
    build_orders_csv,
    build_reports_csv,
    build_users_csv,
)


router = APIRouter()


def _csv_response(csv_text: str, filename: str) -> Response:
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/export/auction_results.csv")
def export_auction_results_csv(session_id: int | None = None):
    return _csv_response(build_auction_results_csv(session_id=session_id), "auction_results.csv")


@router.get("/api/export/orders.csv")
def export_orders_csv(session_id: int | None = None):
    return _csv_response(build_orders_csv(session_id=session_id), "buyer_orders.csv")


@router.get("/api/export/reports.csv")
def export_reports_csv(session_id: int | None = None):
    return _csv_response(build_reports_csv(session_id=session_id), "product_report.csv")


@router.get("/api/export/users.csv")
def export_users_csv():
    return Response(
        content=b"competitor monitoring retired",
        status_code=410,
        media_type="text/plain; charset=utf-8",
    )
