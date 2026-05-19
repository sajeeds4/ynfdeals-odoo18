import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.config import POSTGRES_SIDECAR_SCHEMA
from server.postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, postgres_available

OUT_PATH = Path(__file__).resolve().parents[1] / "exports" / "inventory_dupe_research_full.csv"


MANUAL_BY_ID = {
    36: {
        "inspiration_fragrance": "The House of Oud Dates Delight",
        "similarity_pct": "72",
        "confidence": "low-medium",
        "classification": "inspired by / adjacent",
        "notes": "Commonly compared to Angels' Share, but stronger community consensus points to Dates Delight or a broader same-lane gourmand profile rather than a clean 1:1 clone.",
        "sources": "Community consensus / retailer descriptions",
    },
    37: {
        "inspiration_fragrance": "Khamrah coffee flanker lane / no single clean target",
        "similarity_pct": "68",
        "confidence": "low",
        "classification": "flanker / not a clean dupe call",
        "notes": "Better treated as a coffee flanker of Khamrah than as a direct dupe of one famous original.",
        "sources": "Community consensus",
    },
    38: {
        "inspiration_fragrance": "Creed Aventus",
        "similarity_pct": "83",
        "confidence": "medium",
        "classification": "same DNA / likely inspiration",
        "notes": "Frequently compared to Aventus in the clone community, but not usually sold as a straight 1:1 clone.",
        "sources": "Community consensus",
    },
    39: {
        "inspiration_fragrance": "Burberry Goddess",
        "similarity_pct": "88",
        "confidence": "medium",
        "classification": "close dupe / same DNA",
        "notes": "Often compared with Burberry Goddess because of the vanilla-lavender profile.",
        "sources": "Community consensus",
    },
    40: {
        "inspiration_fragrance": "Dior Sauvage Elixir",
        "similarity_pct": "84",
        "confidence": "medium",
        "classification": "inspired by / twist clone",
        "notes": "Widely treated as Sauvage Elixir-inspired, though sweeter and more vanilla-forward than the Dior original.",
        "sources": "Retailer references and community consensus",
    },
    42: {
        "inspiration_fragrance": "Giardini di Toscana Bianco Latte",
        "similarity_pct": "91",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "Commonly and explicitly positioned as a Bianco Latte alternative.",
        "sources": "Retailer references and community consensus",
    },
    45: {
        "inspiration_fragrance": "Initio Oud for Greatness",
        "similarity_pct": "92",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "One of the clearest and most widely accepted clone relationships in the catalog.",
        "sources": "Retailer references and community consensus",
    },
    49: {
        "inspiration_fragrance": "YSL Y EDP",
        "similarity_pct": "88",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "Multiple retailers position Fakhar Men as YSL Y-inspired.",
        "sources": "Retailer references",
    },
    50: {
        "inspiration_fragrance": "Initio Paragon",
        "similarity_pct": "89",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "Very common consensus match.",
        "sources": "Retailer references and community consensus",
    },
    54: {
        "inspiration_fragrance": "Dolce & Gabbana My Devotion",
        "similarity_pct": "90",
        "confidence": "medium",
        "classification": "close dupe / same DNA",
        "notes": "Better fit than Devotion Intense from the research I found. I would still validate side-by-side before selling it as an exact match.",
        "sources": "Community consensus",
    },
    55: {
        "inspiration_fragrance": "Givenchy L'Interdit",
        "similarity_pct": "90",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "Multiple retailers position Fakhar Women as L'Interdit-inspired.",
        "sources": "Retailer references",
    },
    56: {
        "inspiration_fragrance": "Parfums de Marly Delina",
        "similarity_pct": "93",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "Maison Alhambra explicitly positions Delilah as Delina-inspired.",
        "sources": "Maison Alhambra official page",
    },
    60: {
        "inspiration_fragrance": "Parfums de Marly Sedley",
        "similarity_pct": "90",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "One of the clearest Lattafa freshie clone relationships.",
        "sources": "Retailer references and community consensus",
    },
    61: {
        "inspiration_fragrance": "Maison Francis Kurkdjian Baccarat Rouge 540",
        "similarity_pct": "86",
        "confidence": "high",
        "classification": "close dupe / same DNA",
        "notes": "Commonly sold as a BR540-style scent, though not usually described as an exact replacement for everyone.",
        "sources": "Retailer references and community consensus",
    },
    64: {
        "inspiration_fragrance": "Billie Eilish Eilish No. 1",
        "similarity_pct": "92",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "A very commonly agreed clone match.",
        "sources": "Retailer references and community consensus",
    },
    69: {
        "inspiration_fragrance": "Paco Rabanne Invictus",
        "similarity_pct": "78",
        "confidence": "medium",
        "classification": "same lane / likely inspiration",
        "notes": "Very often compared to Invictus, but Hawas has enough personality that I would not present it as a strict 1:1.",
        "sources": "Community consensus",
    },
    70: {
        "inspiration_fragrance": "Maison Francis Kurkdjian Baccarat Rouge 540 Extrait",
        "similarity_pct": "92",
        "confidence": "high",
        "classification": "direct dupe",
        "notes": "The name itself points directly to the BR540 clone lane.",
        "sources": "Product naming and community consensus",
    },
    72: {
        "inspiration_fragrance": "Louis Vuitton Pacific Chill",
        "similarity_pct": "82",
        "confidence": "medium",
        "classification": "inspired by / same DNA",
        "notes": "Good consensus match, but less universally described as a near-identical clone than Delilah or Oud for Glory.",
        "sources": "Community consensus",
    },
    102: {
        "inspiration_fragrance": "Creed Aventus",
        "similarity_pct": "80",
        "confidence": "medium",
        "classification": "same DNA / likely inspiration",
        "notes": "The name strongly suggests Aventus positioning, but I would still sell it as Aventus-style rather than exact.",
        "sources": "Naming convention and community consensus",
    },
    109: {
        "inspiration_fragrance": "Creed Aventus",
        "similarity_pct": "78",
        "confidence": "medium",
        "classification": "same DNA / likely inspiration",
        "notes": "The name strongly suggests Aventus positioning, but not enough evidence for a strict dupe claim.",
        "sources": "Naming convention and community consensus",
    },
    126: {
        "inspiration_fragrance": "Creed Green Irish Tweed",
        "similarity_pct": "87",
        "confidence": "medium",
        "classification": "close dupe / same DNA",
        "notes": "L'Aventure Knight is commonly framed as Green Irish Tweed-inspired.",
        "sources": "Retailer references and community consensus",
    },
    128: {
        "inspiration_fragrance": "Unclear / not enough reliable agreement yet",
        "similarity_pct": "",
        "confidence": "low",
        "classification": "unconfirmed",
        "notes": "Do not assign a % yet. It does not have the same strong consensus that original Afnan 9PM has with Ultra Male.",
        "sources": "Recent community discussion",
    },
    130: {
        "inspiration_fragrance": "Paco Rabanne Invictus Aqua 2016",
        "similarity_pct": "86",
        "confidence": "medium",
        "classification": "close dupe / same DNA",
        "notes": "Often framed as an Invictus Aqua-style scent, but still worth side-by-side validation before making an absolute claim.",
        "sources": "Community consensus",
    },
}


NAME_RULES = [
    {
        "match": "choco musk",
        "inspiration_fragrance": "Unconfirmed / popular standalone gourmand",
        "similarity_pct": "",
        "confidence": "low",
        "classification": "standalone / unconfirmed",
        "notes": "Often compared to gourmand designers, but not one stable, reliable target.",
        "sources": "Community consensus",
    },
    {
        "match": "spanish vanilla",
        "inspiration_fragrance": "Unconfirmed / vanilla style scent",
        "similarity_pct": "",
        "confidence": "low",
        "classification": "standalone / unconfirmed",
        "notes": "No strong reliable clone target found.",
        "sources": "",
    },
    {
        "match": "french coffee",
        "inspiration_fragrance": "Unconfirmed / coffee gourmand lane",
        "similarity_pct": "",
        "confidence": "low",
        "classification": "standalone / unconfirmed",
        "notes": "Frequently compared to designer coffee gourmands, but not a stable 1:1 clone target.",
        "sources": "Community consensus",
    },
    {
        "match": "angham second song",
        "inspiration_fragrance": "Dolce & Gabbana My Devotion",
        "similarity_pct": "90",
        "confidence": "medium",
        "classification": "close dupe / same DNA",
        "notes": "Better fit than Devotion Intense from current research, but still worth side-by-side validation.",
        "sources": "Community consensus",
    },
    {
        "match": "angham",
        "inspiration_fragrance": "Burberry Goddess",
        "similarity_pct": "88",
        "confidence": "medium",
        "classification": "close dupe / same DNA",
        "notes": "Often compared with Burberry Goddess because of the vanilla-lavender profile.",
        "sources": "Community consensus",
    },
]


def normalize(value):
    return (value or "").strip().lower()


def get_mapping(product_id, name):
    if product_id in MANUAL_BY_ID:
        return MANUAL_BY_ID[product_id]
    lname = normalize(name)
    for rule in NAME_RULES:
        if rule["match"] in lname:
            return rule
    return {
        "inspiration_fragrance": "",
        "similarity_pct": "",
        "confidence": "low",
        "classification": "unconfirmed",
        "notes": "No reliable dupe target found yet. Needs dedicated product-level research or side-by-side smell test.",
        "sources": "",
    }


def main():
    if not postgres_available():
        raise SystemExit("postgres_required: build_full_dupe_research no longer reads SQLite whatnot.db")
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT p.id, p.name, p.brand, p.sku, p.barcode, pc.name AS category,
                   p.cost_price, p.retail_price, p.on_hand_qty, p.active
            FROM {POSTGRES_SIDECAR_SCHEMA}.products p
            LEFT JOIN {POSTGRES_SIDECAR_SCHEMA}.product_categories pc ON pc.id = p.category_id
            ORDER BY LOWER(COALESCE(p.brand, '')), LOWER(p.name)
            """
        )
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "product_id",
                "product_name",
                "brand",
                "category",
                "sku",
                "barcode",
                "cost_price",
                "retail_price",
                "on_hand_qty",
                "active",
                "inspiration_fragrance",
                "similarity_pct",
                "confidence",
                "classification",
                "needs_smell_test",
                "notes",
                "sources",
            ],
        )
        writer.writeheader()
        mapped = 0
        for row in rows:
            mapping = get_mapping(row["id"], row["name"])
            if mapping["inspiration_fragrance"]:
                mapped += 1
            writer.writerow(
                {
                    "product_id": row["id"],
                    "product_name": row["name"],
                    "brand": row["brand"],
                    "category": row["category"],
                    "sku": row["sku"],
                    "barcode": row["barcode"],
                    "cost_price": row["cost_price"],
                    "retail_price": row["retail_price"],
                    "on_hand_qty": row["on_hand_qty"],
                    "active": row["active"],
                    "inspiration_fragrance": mapping["inspiration_fragrance"],
                    "similarity_pct": mapping["similarity_pct"],
                    "confidence": mapping["confidence"],
                    "classification": mapping["classification"],
                    "needs_smell_test": "yes" if mapping["confidence"] != "high" else "optional",
                    "notes": mapping["notes"],
                    "sources": mapping["sources"],
                }
            )

    print(f"wrote {len(rows)} rows")
    print(f"mapped {mapped} products with a named inspiration target")
    print(OUT_PATH)


if __name__ == "__main__":
    main()
