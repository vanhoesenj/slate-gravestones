"""Seed a 'Marker Type' category (single-select). Safe to run more than once —
existing tags are left alone. Run from repo root: python3 scripts/add_marker_types.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "admin"))

import db  # noqa: E402

MARKER_TYPES = [
    "Tablet / Headstone",
    "Companion Stones",
    "Footstone",
    "Ledger / Slab",
    "Chest Tomb",
    "Table Tomb",
    "Obelisk",
    "Column / Broken Column",
    "Pedestal Monument (Die on Base)",
    "Cross",
    "Cradle Grave / Bedstead",
    "Flower Box",
    "Sarcophagus",
    "Mausoleum / Vault",
    "Military / Government Marker",
    "Cenotaph",
    "Fragment / Displaced Stone",
    "Other",
]


def main():
    db.init()
    con = db.connect()
    row = con.execute(
        "SELECT id FROM categories WHERE name='Marker Type'").fetchone()
    if row:
        cat_id = row["id"]
        print("Category 'Marker Type' already exists — adding any missing tags.")
    else:
        cat_id = con.execute(
            "INSERT INTO categories(name, single_select, sort) VALUES(?,?,?)",
            ("Marker Type", 1, 3)).lastrowid
    added = 0
    for name in MARKER_TYPES:
        cur = con.execute(
            "INSERT OR IGNORE INTO tags(category_id, name) VALUES(?,?)",
            (cat_id, name))
        added += cur.rowcount
    con.commit()
    con.close()
    print(f"Done — {added} tag(s) added to 'Marker Type'.")


if __name__ == "__main__":
    main()
