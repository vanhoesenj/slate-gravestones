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
        "notes, transcription AS trans FROM stones ORDER BY id").fetchall()
    persons_by_stone = {}
    for r in con.execute(
            "SELECT stone_id, name, birth_year AS birth, death_year AS death "
            "FROM persons ORDER BY stone_id, sort, id"):
        persons_by_stone.setdefault(r["stone_id"], []).append(
            {"name": r["name"], "birth": r["birth"], "death": r["death"]})
    tags_by_stone = {}
    for r in con.execute("SELECT stone_id, tag_id FROM stone_tags"):
        tags_by_stone.setdefault(r["stone_id"], []).append(r["tag_id"])
    photos_by_stone = {}
    for r in con.execute(
            "SELECT id, stone_id, width AS w, height AS h, is_primary, "
            "r2_synced, has_depth FROM photos ORDER BY is_primary DESC, id"):
        p = {"id": r["id"], "w": r["w"], "h": r["h"]}
        if r["has_depth"]:
            p["depth"] = 1
        photos_by_stone.setdefault(r["stone_id"], []).append(p)
    # approved outlines only; primary photo's outline wins
    outline_by_stone = {}
    for r in con.execute(
            "SELECT stone_id, outline_path AS d, outline_h AS h FROM photos "
            "WHERE outline_status='approved' AND outline_path != '' "
            "ORDER BY is_primary DESC, id"):
        outline_by_stone.setdefault(r["stone_id"],
                                    {"d": r["d"], "h": r["h"]})
    for s in stones:
        rec = dict(s)
        rec["persons"] = persons_by_stone.get(s["id"], [])
        rec["tags"] = tags_by_stone.get(s["id"], [])
        if s["id"] in outline_by_stone:
            rec["outline"] = outline_by_stone[s["id"]]
        rec["photos"] = photos_by_stone.get(s["id"], [])
        if rec["photos"]:  # only publish stones that have at least one photo
            data["stones"].append(rec)
    con.close()

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    # shape space (morphometrics) — recomputed automatically from approved
    # outlines; the site hides the feature if the file is absent
    morpho_path = os.path.join(os.path.dirname(os.path.abspath(OUT_PATH)),
                               "morpho.json")
    morpho_n = 0
    try:
        import morpho_core
        years = {s["id"]: s["year"] for s in data["stones"]}
        morpho = morpho_core.analyze(
            {sid: o["d"] for sid, o in outline_by_stone.items()}, years)
        if morpho:
            with open(morpho_path, "w") as f:
                json.dump(morpho, f, separators=(",", ":"))
            morpho_n = morpho["n"]
        elif os.path.exists(morpho_path):
            os.remove(morpho_path)
    except Exception as e:
        print(f"morphometrics skipped: {e}")

    return {"stones": len(data["stones"]),
            "cemeteries": len(data["cemeteries"]),
            "shapes_analyzed": morpho_n,
            "path": os.path.abspath(OUT_PATH)}


if __name__ == "__main__":
    print(export())
