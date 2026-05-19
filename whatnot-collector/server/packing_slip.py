"""
Whatnot packing-slip PDF parser.

Parses the packing-slip PDFs that Whatnot emails after each stream.
Structure: odd pages = packing slips, even pages = USPS shipping labels (no text).

Each packing-slip page contains:
  - "To: <username>"
  - Buyer full name + address
  - Line items with lot numbers (#N), order IDs, and prices
  - Tracking number at the bottom
"""

import re
import PyPDF2
from io import BytesIO


def parse_packing_slip_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Parse a Whatnot packing-slip PDF and return a list of shipments.

    Each shipment dict:
      {
        "username": "rj0118",
        "buyer_name": "Rabia Rehman",
        "address": "52 E Fenimore St. Valley Stream, NY. 11580-3408. US",
        "ship_date": "22 March, 2026",
        "weight": "80.0 oz",
        "tracking_number": "9336220762600010296181",
        "shipping_method": "USPS Ground Advantage",
        "items": [
          {"lot_number": "8", "order_id": "913015121", "price": 10.0, "whatnot_name": "$1 PERFUMES WITH YNFDEALS"},
          ...
        ],
        "total_items": 5,
        "total_price": 72.0,
      }
    """
    reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
    shipments = []

    for page in reader.pages:
        text = page.extract_text()
        if not text or "Whatnot Packing Slip" not in text:
            continue  # skip label pages / empty pages

        shipment = _parse_slip_page(text)
        if shipment:
            # Filter out GIVEAWAY items
            shipment["items"] = [
                item for item in shipment["items"]
                if not _is_giveaway(item)
            ]
            # Skip shipments that only contained giveaways
            if not shipment["items"]:
                continue
            # Recalculate totals after filtering
            shipment["total_items"] = len(shipment["items"])
            shipment["total_price"] = sum(i["price"] for i in shipment["items"])
            shipments.append(shipment)

    return shipments


def _is_giveaway(item: dict) -> bool:
    """Check if a line item is a giveaway (should be excluded)."""
    text = " ".join([
        str(item.get("whatnot_name") or ""),
        str(item.get("raw_text") or ""),
    ]).lower()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return False
    if re.search(r"\bgive\s*away\b", text):
        return True
    if "giveyyy" in text or "givey" in text:
        return True
    if "freebie" in text or "free item" in text:
        return True
    if "random give" in text:
        return True
    return False


def _parse_slip_page(text: str) -> dict | None:
    """Parse a single packing-slip page text."""

    # Extract username: "To: <username> [NEW] From: ynfdeals"
    # Some buyers have a "NEW" badge between username and "From:"
    m_user = re.search(r"To:\s+(\S+)(?:\s+NEW)?\s+From:", text)
    if not m_user:
        return None
    username = m_user.group(1)

    # Extract buyer name and address
    # Text structure: "To: username From: ynfdeals\nBuyer Name\nAddress lines...\n■ promo ■\nDD Month, YYYY"
    lines = text.split("\n")
    buyer_name = ""
    address_parts = []
    ship_date = ""
    found_from = False
    collecting_address = False
    for line in lines:
        stripped = line.strip()
        if "From:" in line:
            found_from = True
            continue
        if not found_from:
            continue

        # Skip promo text blocks (■ delimited) and empty lines
        if stripped.startswith("■") or (not stripped):
            continue
        # Skip "$1 STARTS" / promo lines that appear in older stream PDFs
        if re.match(r"^\$\d+\s+STARTS", stripped, re.IGNORECASE):
            continue

        # Date line — e.g. "22 March, 2026"
        if re.match(r"\d{1,2}\s+\w+,?\s+\d{4}", stripped):
            ship_date = stripped
            break

        # QTY header — stop
        if stripped.startswith("QTY"):
            break

        if not buyer_name:
            buyer_name = stripped
            collecting_address = True
            continue

        if collecting_address:
            # Address lines contain digits/street info, end at promo or date
            address_parts.append(stripped)

    # Clean address: strip promo text that's concatenated (■ delimited)
    raw_address = " ".join(address_parts)
    # Remove everything from the first ■ onward
    if "■" in raw_address:
        raw_address = raw_address[:raw_address.index("■")]
    address = raw_address.strip()

    # Extract lot numbers, order IDs, and prices
    # Pattern: #<lot_number> ... Order <order_id> $<price>
    # Lot numbers are short (1-4 digits); tracking numbers are 20+ digits — skip those.
    items = []
    lot_matches = [m for m in re.findall(r"#(\d+)", text) if len(m) <= 5]
    order_matches = re.findall(r"Order\s+(\d+)", text)
    price_matches = re.findall(r"Order\s+\d+\s+\$(\d+(?:\.\d+)?)", text)

    # Extract the generic product name (before #N)
    name_match = re.search(r"1\s+(.+?)\s*#\d+", text)
    whatnot_name = name_match.group(1).strip() if name_match else ""
    # Clean up multi-line name
    whatnot_name = re.sub(r"\s+", " ", whatnot_name)

    for idx, lot_num in enumerate(lot_matches):
        item = {
            "lot_number": lot_num,
            "order_id": order_matches[idx] if idx < len(order_matches) else None,
            "price": float(price_matches[idx]) if idx < len(price_matches) else 0.0,
            "whatnot_name": whatnot_name,
            "raw_text": text,
        }
        items.append(item)

    # Extract tracking number and shipping method
    # e.g. "USPS Ground Advantage™  #9336220762600010296181 80.0 oz"
    tracking = ""
    shipping_method = ""
    weight = ""
    m_ship = re.search(r"(USPS\s+[\w\s]+?)™?\s+#(\d{20,})\s+([\d.]+\s*(?:oz|lb))", text)
    if m_ship:
        shipping_method = m_ship.group(1).strip()
        tracking = m_ship.group(2)
        weight = m_ship.group(3)
    else:
        # Fallback: just tracking
        m_track = re.search(r"#(\d{20,})", text)
        if m_track:
            tracking = m_track.group(1)
        # Try weight separately
        m_wt = re.search(r"(\d+(?:\.\d+)?\s*(?:oz|lb))\s*$", text)
        if m_wt:
            weight = m_wt.group(1)

    # Extract total
    m_total = re.search(r"(\d+)\s+Items\s+\$(\d+(?:\.\d+)?)", text)
    total_items = int(m_total.group(1)) if m_total else len(items)
    total_price = float(m_total.group(2)) if m_total else sum(i["price"] for i in items)

    return {
        "username": username,
        "buyer_name": buyer_name,
        "address": address,
        "ship_date": ship_date,
        "weight": weight,
        "tracking_number": tracking,
        "shipping_method": shipping_method,
        "items": items,
        "total_items": total_items,
        "total_price": total_price,
    }


def match_lots_to_products(shipments: list[dict], auction_rows: list[dict]) -> list[dict]:
    """
    Match lot numbers from packing slips to auction_results to get real product names.

    auction_rows: list of dicts from list_auction_results() — each has
      lot_number, product_name, winner_username, sale_price, barcode, sku, etc.

    Returns enriched shipments with matched product info per item.
    """
    # Build lookup: lot_number -> auction result
    lot_lookup = {}
    for row in auction_rows:
        ln = str(row.get("lot_number") or "").strip()
        if ln:
            lot_lookup[ln] = row

    for shipment in shipments:
        for item in shipment["items"]:
            ln = str(item["lot_number"]).strip()
            match = lot_lookup.get(ln)
            if match:
                item["matched"] = True
                item["product_name"] = match.get("product_name") or "Unknown"
                item["barcode"] = match.get("barcode") or ""
                item["sku"] = match.get("sku") or ""
                item["cost_price"] = match.get("cost_price") or 0
                item["auction_result_id"] = match.get("id")
                item["lot_id"] = match.get("lot_id")
            else:
                item["matched"] = False
                item["product_name"] = "⚠ NOT FOUND"
                item["barcode"] = ""
                item["sku"] = ""
                item["cost_price"] = 0
                item["auction_result_id"] = None
                item["lot_id"] = None

    return shipments
