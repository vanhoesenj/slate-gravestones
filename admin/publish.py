"""Export the database to docs/data/library.json for the public site."""
import json
import os
from datetime import datetime, timezone

import db
import r2

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "data",
                        "library.json")


def export():
    con = db.connect()
    data = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "imageBase": r2.public_base(),  # site builds img URLs from this
        "categories": [dict(r) for r in con.execute(
            "SELECT id, name, single_select AS single FROM categories ORDER BY sort, name")],
        "tags": [dict(r) for r in con.execute(
            "SELECT id, category_id AS cat, name FROM tags ORDER BY name")],
        "cemeteries": [dict(r) for r in con.execute(
            """SELECT c.id, c.name, c.city, c.state, c.country, c.lat, c.lng,
                      COUNT(s.id) AS stones
               FROM cemeteries c LEFT JOIN stones s ON s.cemetery_id = c.id
               GROUP BY c.id ORDER BY c.name""")],
        "stones": [],
    }
    stones = con.execute(
        "SELECT id, cemetery_id AS cem, title, year, birth_year AS birth, "
        "date_text AS dateText, notes, transcription AS trans "
        "FROM stones ORDER BY id").fetchall()
    tags_by_stone = {}
    for r in con.execute("SELECT stone_id, tag_id FROM stone_tags"):
        tags_by_stone.setdefault(r["stone_id"], []).append(r["tag_id"])
    photos_by_stone = {}
    for r in con.execute(
            "SELECT id, stone_id, width AS w, height AS h, is_primary, r2_synced "
            "FROM photos ORDER BY is_primary DESC, id"):
        photos_by_stone.setdefault(r["stone_id"], []).append(
            {"id": r["id"], "w": r["w"], "h": r["h"]})
    for s in stones:
        rec = dict(s)
        rec["tags"] = tags_by_stone.get(s["id"], [])
        rec["photos"] = photos_by_stone.get(s["id"], [])
        if rec["photos"]:  # only publish stones that have at least one photo
            data["stones"].append(rec)
    con.close()

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    return {"stones": len(data["stones"]),
            "cemeteries": len(data["cemeteries"]),
            "path": os.path.abspath(OUT_PATH)}


if __name__ == "__main__":
    print(export())
