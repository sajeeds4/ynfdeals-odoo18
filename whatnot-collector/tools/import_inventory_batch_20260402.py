from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from server.company_db import ensure_category, get_product, record_inventory_movement, upsert_product


BATCH_NOTE = "Imported from supplier line items on 2026-04-02"

ITEMS = [
    {"name": "Lattafa Angham 3.4 EDP SPR", "qty": 12, "cost": 18.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Yara Candy 3.4 SPR", "qty": 12, "cost": 14.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Now Women 3.4 EDP SPR", "qty": 24, "cost": 11.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Asad Bourbon 3.3 EDP SPR", "qty": 12, "cost": 14.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Fakhar Men 3.4 SPR", "qty": 12, "cost": 14.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Art of Universe 3.3", "qty": 6, "cost": 24.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Fakhar Women 3.4 SPR", "qty": 12, "cost": 14.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Badee Al Oud Honor and Glory 3.4", "qty": 12, "cost": 15.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Asad Zanzibar 3.4 SPR", "qty": 24, "cost": 12.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Fragrance World Barakkat Rouge 540 Extrait 3.4 SPR", "qty": 120, "cost": 11.00, "brand": "Fragrance World", "category_id": 5},
    {"name": "Jean Lowe Vibe 3.4 SPR", "qty": 12, "cost": 17.00, "brand": "Maison Al Hambra", "category_id": 6},
    {"name": "Lattafa Dynasty 3.4 SPR", "qty": 12, "cost": 16.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Jean Lowe Azure 3.3 EDP SPR", "qty": 12, "cost": 17.00, "brand": "Maison Al Hambra", "category_id": 6},
    {"name": "Lattafa Petra 3.4 EDP SPR", "qty": 12, "cost": 19.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Victoria 3.3", "qty": 12, "cost": 18.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Qimmah 3.4 EDP SPR", "qty": 12, "cost": 11.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Musamam White Intense 3.3 SPR", "qty": 12, "cost": 21.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Armaf Club De Nuit Women 3.6 EDP SPR", "qty": 12, "cost": 16.50, "brand": "Armaf", "category_id": 3},
    {"name": "Armaf Club De Nuit Intense Men 3.6 EDP SPR", "qty": 12, "cost": 19.00, "brand": "Armaf", "category_id": 3},
    {"name": "Lattafa Nebras Elixir 3.4 EDP SPR", "qty": 12, "cost": 23.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Ana Coral 2.0 SPR", "qty": 12, "cost": 10.50, "brand": "Lattafa", "category_id": 8},
    {"name": "Nitro 3.3 EDP SPR", "qty": 12, "cost": 18.50, "brand": "Nitro", "category_id": 3},
    {"name": "Testers Assorted 3.4 SPR", "qty": 30, "cost": 6.00, "brand": "Assorted", "category_id": 3},
    {"name": "Lattafa Mayar Cherry Intense 3.3 SPR", "qty": 12, "cost": 18.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Badee Al Oud Noble Blush 3.3", "qty": 12, "cost": 15.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Armaf Odyssey Candy 3.3 SPR", "qty": 12, "cost": 12.00, "brand": "Armaf", "category_id": 3},
    {"name": "Asdaaf Fouad 3.3 SPR", "qty": 12, "cost": 12.00, "brand": "Asdaaf", "category_id": 3},
    {"name": "Lattafa Teriaq Intense 3.4 EDP SPR", "qty": 12, "cost": 20.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Afnan Supremacy Collector Edition 3.4 EDP SPR", "qty": 6, "cost": 27.00, "brand": "Afnan", "category_id": 9},
    {"name": "Maison Alhambra Flaming Elixir 3.4 SPR", "qty": 10, "cost": 12.00, "brand": "Maison Al Hambra", "category_id": 6},
    {"name": "Lattafa Yara My Collection 4PCS Set", "qty": 6, "cost": 21.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Teriaq 3.4 EDP SPR", "qty": 6, "cost": 16.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Maison Alhambra Luxe 3.4 SPR", "qty": 18, "cost": 14.00, "brand": "Maison Al Hambra", "category_id": 6},
    {"name": "Maison Alhambra Avant 3.4 EDP SPR", "qty": 6, "cost": 10.50, "brand": "Maison Al Hambra", "category_id": 6},
    {"name": "Maison Alhambra Jorge Di Profumo 3.4 SPR", "qty": 6, "cost": 10.50, "brand": "Maison Al Hambra", "category_id": 6},
    {"name": "Afnan Turathi Electric Men 3.0 SPR", "qty": 6, "cost": 25.00, "brand": "Afnan", "category_id": 9},
    {"name": "Amber Oud Gold Edition 60 ML", "qty": 6, "cost": 22.00, "brand": "Al Haramain", "category_id": 3},
    {"name": "Lattafa Now Black 3.4 SPR", "qty": 12, "cost": 11.00, "brand": "Lattafa", "category_id": 8},
    {"name": "Lattafa Nasamat 3.4 SPR", "qty": 6, "cost": 13.50, "brand": "Lattafa", "category_id": 8},
]


def ensure_defaults():
    for name in ("Fragrances", "Health & Beauty", "Fragrance World", "Maison Al Hambra", "Al Rehab", "Lattafa", "Afnan", "Rasasi"):
        ensure_category(name)


def main():
    ensure_defaults()
    created = 0
    adjusted = 0
    imported_ids = []
    for item in ITEMS:
        row = upsert_product(
            name=item["name"],
            category_id=item["category_id"],
            brand=item["brand"],
            supplier_name="Supplier Batch Import",
            product_type="storable",
            cost_price=item["cost"],
            retail_price=item["cost"],
            notes=BATCH_NOTE,
        )
        imported_ids.append(int(row["id"]))
        created += 1
        current_qty = float(row.get("on_hand_qty") or 0.0)
        delta = float(item["qty"]) - current_qty
        if abs(delta) > 0.0001:
            record_inventory_movement(
                int(row["id"]),
                "adjustment",
                delta,
                reason="batch_import_2026_04_02",
                reference_type="inventory_import",
                reference_id=int(row["id"]),
            )
            adjusted += 1
    print({
        "ok": True,
        "created_or_updated": created,
        "stock_adjusted": adjusted,
        "product_ids": imported_ids[:10],
        "total_items": len(ITEMS),
    })


if __name__ == "__main__":
    main()
