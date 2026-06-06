"""Purchase helper routes and vendor-facing quote HTML."""

from html import escape

from fastapi import APIRouter

router = APIRouter()


def _fmt_money(value):
    try:
        return f"${float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _fmt_qty(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _build_vendor_html(data, base_url=""):
    session = data.get("session") or {}
    order = data.get("order") or {}
    lines = data.get("lines") or []
    status = str(session.get("status") or "").lower()
    is_open = status == "pending"
    token = escape(str(session.get("token") or ""))
    submit_path = f"{base_url}/api/v2/purchases/bargain/{token}/submit"

    rows = []
    for line in lines:
        line_id = int(line.get("line_id") or 0)
        product = escape(str(line.get("current_product_name") or line.get("product_name_snapshot") or "Product"))
        sku = escape(str(line.get("sku_snapshot") or ""))
        barcode = escape(str(line.get("barcode_snapshot") or ""))
        qty = _fmt_qty(line.get("qty_ordered"))
        our_price = _fmt_money(line.get("our_price"))
        vendor_price = line.get("vendor_price")
        rows.append(f"""
          <tr>
            <td>
              <strong>{product}</strong>
              <span>{sku or barcode or "No SKU"}{f" | {barcode}" if sku and barcode else ""}</span>
            </td>
            <td class="num">{qty}</td>
            <td class="num muted">{our_price}</td>
            <td><input name="vp_{line_id}" type="number" min="0" step="0.01" value="{escape(str(vendor_price or ""))}" {"disabled" if not is_open else ""}></td>
            <td><input name="avail_{line_id}" value="{escape(str(line.get("availability_status") or "available"))}" {"disabled" if not is_open else ""}></td>
            <td><input name="aq_{line_id}" type="number" min="0" step="1" value="{escape(str(line.get("available_qty") or ""))}" {"disabled" if not is_open else ""}></td>
            <td><input name="case_{line_id}" value="{escape(str(line.get("case_pack") or ""))}" {"disabled" if not is_open else ""}></td>
            <td><input name="repl_{line_id}" value="{escape(str(line.get("replacement") or ""))}" {"disabled" if not is_open else ""}></td>
            <td><input name="bulk_{line_id}" value="{escape(str(line.get("bulk_discount") or ""))}" {"disabled" if not is_open else ""}></td>
          </tr>
        """)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(str(order.get("po_number") or "Purchase Quote"))}</title>
  <style>
    :root {{ color-scheme: light; --ink:#10233f; --muted:#64748b; --line:#d9e0e7; --soft:#f8fafc; --blue:#2f5da8; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, Arial, sans-serif; background:#f3f6fa; color:var(--ink); }}
    .wrap {{ max-width:1180px; margin:0 auto; padding:28px 18px; }}
    .card {{ background:white; border:1px solid var(--line); border-radius:18px; box-shadow:0 18px 42px rgba(16,35,63,.08); overflow:hidden; }}
    header {{ padding:22px 24px; display:flex; justify-content:space-between; gap:18px; border-bottom:1px solid var(--line); }}
    h1 {{ margin:0; font-size:26px; letter-spacing:0; }}
    .eyebrow {{ font-size:11px; font-weight:800; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }}
    .meta {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; padding:16px 24px; background:var(--soft); border-bottom:1px solid var(--line); }}
    .meta div {{ background:white; border:1px solid var(--line); border-radius:12px; padding:10px 12px; }}
    .meta span {{ display:block; font-size:11px; font-weight:800; text-transform:uppercase; color:var(--muted); margin-bottom:4px; }}
    form {{ padding:20px 24px 24px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th {{ text-align:left; background:#10233f; color:white; padding:10px 8px; font-size:11px; text-transform:uppercase; letter-spacing:.06em; }}
    td {{ border-bottom:1px solid #edf1f5; padding:9px 8px; vertical-align:top; }}
    td span {{ display:block; color:var(--muted); font-size:12px; margin-top:3px; }}
    .num {{ text-align:right; white-space:nowrap; }}
    .muted {{ color:var(--muted); }}
    input, textarea {{ width:100%; min-height:34px; border:1px solid var(--line); border-radius:9px; padding:7px 9px; font:inherit; }}
    textarea {{ min-height:80px; margin-top:10px; }}
    .actions {{ margin-top:18px; display:flex; justify-content:flex-end; gap:10px; align-items:center; }}
    button {{ border:0; border-radius:11px; min-height:40px; padding:0 18px; background:var(--blue); color:white; font-weight:800; cursor:pointer; }}
    .closed {{ color:#9a6b12; font-weight:800; }}
    @media (max-width: 860px) {{ .meta {{ grid-template-columns:1fr; }} table {{ min-width:980px; }} .table-scroll {{ overflow:auto; }} header {{ display:block; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <header>
        <div>
          <div class="eyebrow">YNF Deals Vendor Quote</div>
          <h1>{escape(str(order.get("po_number") or "Purchase Quote"))}</h1>
        </div>
        <div>
          <div class="eyebrow">Status</div>
          <div class="closed">{escape(status.title() or "Pending")}</div>
        </div>
      </header>
      <section class="meta">
        <div><span>Vendor</span>{escape(str(order.get("vendor_name") or "-"))}</div>
        <div><span>Order Date</span>{escape(str(order.get("order_date") or "-"))}</div>
        <div><span>Expected</span>{escape(str(order.get("expected_date") or "-"))}</div>
        <div><span>Lines</span>{len(lines)}</div>
      </section>
      <form method="post" action="{submit_path}">
        <div class="table-scroll">
          <table>
            <thead><tr><th>Product</th><th>Qty</th><th>Our Price</th><th>Your Price</th><th>Availability</th><th>Available Qty</th><th>Case Pack</th><th>Replacement</th><th>Bulk Discount</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        <textarea name="vendor_notes" placeholder="Vendor notes, ETA, substitutions, minimums...">{escape(str(session.get("vendor_notes") or ""))}</textarea>
        <div class="actions">
          {"<span class='closed'>This quote is closed.</span>" if not is_open else "<button type='submit'>Submit Quote</button>"}
        </div>
      </form>
    </div>
  </div>
</body>
</html>"""
