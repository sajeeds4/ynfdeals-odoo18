"""Purchase-order service helpers shared by the legacy and FastAPI routes."""

from __future__ import annotations

from io import BytesIO
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from server.company_db import (
    get_bargain_session_by_token,
    get_purchase_order_detail,
    submit_bargain,
)


COMPANY_NAME = "YNF Deals"
COMPANY_LEGAL = "Bharuchi Corp"
COMPANY_EMAIL = "bharuchicorp@gmail.com"


def _money(value):
    try:
        return f"${float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _qty(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _safe_filename(value):
    text = re.sub(r"[^A-Za-z0-9._ -]+", "", str(value or "").strip())
    return text or "purchase-order"


def get_bargain_by_token(token):
    return get_bargain_session_by_token(token)


def submit_bargain_quote(token, vendor_prices, vendor_notes=None):
    return submit_bargain(token, vendor_prices, vendor_notes=vendor_notes)


def build_purchase_pdf(order_id):
    detail = get_purchase_order_detail(int(order_id))
    if not detail:
        return None

    order = detail.get("order") or {}
    lines = detail.get("lines") or []
    po_number = order.get("po_number") or f"PO-{order_id}"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.42 * inch,
        bottomMargin=0.42 * inch,
        title=f"{po_number} Purchase Order",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "PoTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#10233F"),
        spaceAfter=4,
    )
    eyebrow = ParagraphStyle(
        "Eyebrow",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748B"),
        uppercase=True,
    )
    small = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#475569"),
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#10233F"),
    )
    right = ParagraphStyle("Right", parent=body, alignment=TA_RIGHT)

    story = []
    header = Table(
        [
            [
                Paragraph(f"<b>{COMPANY_NAME}</b><br/><font size='8'>{COMPANY_LEGAL}<br/>{COMPANY_EMAIL}</font>", body),
                Paragraph(f"<font size='8' color='#64748B'><b>PURCHASE ORDER</b></font><br/><font size='20'><b>{po_number}</b></font>", right),
            ]
        ],
        colWidths=[3.7 * inch, 3.35 * inch],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(header)

    meta = Table(
        [
            [
                Paragraph("<b>Vendor</b>", eyebrow),
                Paragraph("<b>Order Date</b>", eyebrow),
                Paragraph("<b>Expected</b>", eyebrow),
                Paragraph("<b>Status</b>", eyebrow),
            ],
            [
                Paragraph(str(order.get("vendor_name") or "-"), body),
                Paragraph(str(order.get("order_date") or "-"), body),
                Paragraph(str(order.get("expected_date") or "-"), body),
                Paragraph(str(order.get("status") or "-").replace("_", " ").title(), body),
            ],
        ],
        colWidths=[2.25 * inch, 1.6 * inch, 1.6 * inch, 1.6 * inch],
    )
    meta.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#D9E0E7")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7EDF3")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(meta)
    story.append(Spacer(1, 14))

    rows = [[
        Paragraph("<b>#</b>", small),
        Paragraph("<b>Product</b>", small),
        Paragraph("<b>SKU / Barcode</b>", small),
        Paragraph("<b>Qty</b>", right),
        Paragraph("<b>Unit</b>", right),
        Paragraph("<b>Total</b>", right),
    ]]
    for index, line in enumerate(lines, start=1):
        product_name = line.get("current_product_name") or line.get("product_name_snapshot") or "Product"
        sku = line.get("sku_snapshot") or "-"
        barcode = line.get("barcode_snapshot") or "-"
        rows.append([
            Paragraph(str(index), small),
            Paragraph(str(product_name), body),
            Paragraph(f"{sku}<br/><font color='#64748B'>{barcode}</font>", small),
            Paragraph(_qty(line.get("qty_ordered")), right),
            Paragraph(_money(line.get("unit_cost")), right),
            Paragraph(_money(line.get("line_total")), right),
        ])

    table = Table(rows, colWidths=[0.35 * inch, 3.0 * inch, 1.45 * inch, 0.62 * inch, 0.8 * inch, 0.88 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10233F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#E7EDF3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBFCFE")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    shipping = float(order.get("shipping_cost") or 0)
    tax = float(order.get("tax_cost") or 0)
    misc = float(order.get("misc_cost") or 0)
    subtotal = sum(float(line.get("line_total") or 0) for line in lines)
    total = float(order.get("total_cost") or (subtotal + shipping + tax + misc))
    totals = Table(
        [
            ["Subtotal", _money(subtotal)],
            ["Shipping", _money(shipping)],
            ["Tax", _money(tax)],
            ["Misc", _money(misc)],
            [Paragraph("<b>Total</b>", body), Paragraph(f"<b>{_money(total)}</b>", right)],
        ],
        colWidths=[1.2 * inch, 1.15 * inch],
        hAlign="RIGHT",
    )
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 4), (-1, 4), 1.0, colors.HexColor("#10233F")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(totals)

    if order.get("notes"):
        story.append(Spacer(1, 12))
        story.append(Paragraph("<b>Notes</b>", eyebrow))
        story.append(Paragraph(str(order.get("notes")).replace("\n", "<br/>"), small))

    story.append(Spacer(1, 20))
    footer = Table(
        [[
            Paragraph("Issued by YNF Deals purchasing. Confirm availability, substitutions, case packs, and ship date before fulfillment.", small),
        ]],
        colWidths=[7.0 * inch],
    )
    footer.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D9E0E7")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(footer)

    doc.build(story)
    return {
        "filename": f"{_safe_filename(po_number)}.pdf",
        "content": buffer.getvalue(),
    }
