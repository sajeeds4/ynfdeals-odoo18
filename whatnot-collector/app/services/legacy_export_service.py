from __future__ import annotations

import csv
import io

from server.company_db import list_auction_results, list_buyer_groups
from server.company_db import get_product_profit_rows
from server.events_db import get_audience_users


def build_auction_results_csv(session_id: int | None = None) -> str:
    rows = list_auction_results(session_id=session_id, limit=10000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["ID", "Session", "Lot #", "Winner", "Product", "SKU", "Barcode", "Sale Price", "Cost", "Fees", "Profit", "Margin %", "Sold At"]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("id"),
                row.get("session_id"),
                row.get("lot_number"),
                row.get("winner_username"),
                row.get("product_name"),
                row.get("sku"),
                row.get("barcode"),
                row.get("sale_price"),
                row.get("cost_price"),
                row.get("fees"),
                row.get("profit"),
                round(row.get("margin_pct") or 0, 1),
                row.get("sold_at"),
            ]
        )
    return buf.getvalue()


def build_orders_csv(session_id: int | None = None) -> str:
    rows = list_buyer_groups(session_id=session_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Session", "Buyer", "Revenue", "Cost", "Profit", "Sale Order", "Lots"])
    for row in rows:
        writer.writerow(
            [
                row.get("id"),
                row.get("session_id"),
                row.get("whatnot_buyer_username") or row.get("winner_username"),
                row.get("total_revenue"),
                row.get("total_cost"),
                row.get("total_profit"),
                row.get("sale_order_id") or "",
                row.get("lot_count") or "",
            ]
        )
    return buf.getvalue()


def build_reports_csv(session_id: int | None = None) -> str:
    rows = get_product_profit_rows(session_id=session_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Product", "SKU", "Barcode", "Session", "Times Sold", "Avg Price", "Revenue", "Cost", "Profit", "Avg Margin %"])
    for row in rows:
        writer.writerow(
            [
                row.get("product_name"),
                row.get("sku"),
                row.get("barcode"),
                row.get("session_name") or row.get("session_id_name"),
                row.get("times_sold"),
                round(row.get("avg_winning_price") or 0, 2),
                row.get("total_revenue"),
                row.get("total_cost"),
                row.get("total_profit"),
                round(row.get("avg_margin") or 0, 1),
            ]
        )
    return buf.getvalue()


def build_users_csv() -> str:
    rows = get_audience_users(min_streams=1, limit=1000000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Username", "Tier", "Roles", "Streams", "Chat Messages", "Bids", "Total Wins", "Total Spent", "First Seen", "Last Seen"])
    for row in rows:
        writer.writerow(
            [
                row["username"],
                row["tier"],
                ", ".join(row.get("roles") or []),
                row["stream_count"],
                row["chat_messages"],
                row["bids"],
                row["total_wins"],
                row["total_spent"],
                row["first_seen"],
                row["last_seen"],
            ]
        )
    return buf.getvalue()
