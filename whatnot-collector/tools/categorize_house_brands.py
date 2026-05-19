from pathlib import Path
from datetime import datetime, timezone
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.config import POSTGRES_SIDECAR_SCHEMA
from server.postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, postgres_available

HOUSE_RULES = [
    (
        "Maison Al Hambra",
        (
            "maison alhambra",
            "maison al hambra",
            "al hambra",
            "alhambra",
            "jean lowe",
            "glacier bold",
            "delilah pour femme",
            "barakkat rouge 540 by maison alhambra",
        ),
    ),
    (
        "Al Rehab",
        (
            "al rehab",
            "al-rehab",
        ),
    ),
    (
        "Lattafa",
        (
            "lattafa",
        ),
    ),
    (
        "Afnan",
        (
            "afnan",
            "9 pm night out by afnan",
        ),
    ),
    (
        "Rasasi",
        (
            "rasasi",
            "hawas for men",
            "hawas ice",
        ),
    ),
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize(value):
    return (value or "").strip().lower()


def detect_house(name, brand):
    haystack = f"{normalize(brand)} || {normalize(name)}"
    for house, patterns in HOUSE_RULES:
        if any(pattern in haystack for pattern in patterns):
            return house
    return None


def ensure_category(cur, name):
    cur.execute(
        f"SELECT id FROM {POSTGRES_SIDECAR_SCHEMA}.product_categories WHERE LOWER(name) = LOWER(%s)",
        (name,),
    )
    row = cur.fetchone()
    if row:
      return row[0]
    ts = now_iso()
    cur.execute(
        f"""
        INSERT INTO {POSTGRES_SIDECAR_SCHEMA}.product_categories(name, created_at, updated_at)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (name, ts, ts),
    )
    return cur.fetchone()[0]


def main():
    if not postgres_available():
        raise SystemExit("postgres_required: categorize_house_brands no longer writes SQLite whatnot.db")
    ensure_wave1_postgres_schema()
    conn = _pg_connect()
    cur = conn.cursor()

    category_ids = {name: ensure_category(cur, name) for name, _ in HOUSE_RULES}

    cur.execute(f"SELECT id, name, brand, category_id FROM {POSTGRES_SIDECAR_SCHEMA}.products")
    rows = cur.fetchall()
    assignments = {name: [] for name, _ in HOUSE_RULES}

    for product_id, name, brand, _category_id in rows:
        house = detect_house(name, brand)
        if not house:
            continue
        assignments[house].append(product_id)

    ts = now_iso()
    for house, product_ids in assignments.items():
        if not product_ids:
            continue
        cur.executemany(
            f"UPDATE {POSTGRES_SIDECAR_SCHEMA}.products SET category_id = %s, updated_at = %s WHERE id = %s",
            [(category_ids[house], ts, product_id) for product_id in product_ids],
        )

    conn.commit()
    conn.close()

    for house, product_ids in assignments.items():
        print(f"{house}\tcategory_id={category_ids[house]}\tproducts={len(product_ids)}")


if __name__ == "__main__":
    main()
