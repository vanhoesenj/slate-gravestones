"""Seed a 'Condition' category (single-select), using the standard cemetery
conservation scale. Safe to run more than once.
Run from repo root: python3 scripts/add_condition.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "admin"))

import db  # noqa: E402

CONDITIONS = ["Excellent", "Good", "Fair", "Poor", "Ruined / Fragmentary"]


def main():
    db.init()
    con = db.connect()
    row = con.execute("SELECT id FROM categories WHERE name='Condition'").fetchone()
    cat_id = row["id"] if row else con.execute(
        "INSERT INTO categories(name, single_select, sort) VALUES('Condition', 1, 4)"
    ).lastrowid
    added = 0
    for name in CONDITIONS:
        added += con.execute(
            "INSERT OR IGNORE INTO tags(category_id, name) VALUES(?,?)",
            (cat_id, name)).rowcount
    con.commit()
    con.close()
    print(f"Done — {added} tag(s) added to 'Condition'.")


if __name__ == "__main__":
    main()
