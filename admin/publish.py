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
        "notes, transcription AS trans, has_audio, submitted_by "
        "FROM stones ORDER BY id").fetchall()
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
        if rec.pop("has_audio", 0):
            rec["audio"] = 1
        sub = (rec.pop("submitted_by", "") or "").strip()
        if sub:
            rec["sub"] = sub
        rec["persons"] = persons_by_stone.get(s["id"], [])
        rec["tags"] = tags_by_stone.get(s["id"], [])
        if s["id"] in outline_by_stone:
            rec["outline"] = outline_by_stone[s["id"]]
        rec["photos"] = photos_by_stone.get(s["id"], [])
        if rec["photos"]:  # only publish stones that have at least one photo
            data["stones"].append(rec)
    # visual-similarity embeddings (primary photo per stone), for the
    # constellation view
    emb_by_stone = {}
    for r in con.execute(
            "SELECT p.stone_id, e.vec FROM photo_emb e "
            "JOIN photos p ON p.id=e.photo_id "
            "ORDER BY p.stone_id, p.is_primary DESC, p.id"):
        emb_by_stone.setdefault(r["stone_id"], r["vec"])
    letter_rows = [dict(r) for r in con.execute(
        "SELECT id, ch, stone_id FROM letters WHERE status='ok' ORDER BY id")]
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

    # constellation: 2D projection of CLIP embeddings, one point per stone
    constel_path = os.path.join(os.path.dirname(os.path.abspath(OUT_PATH)),
                                "constellation.json")
    constel_n = 0
    try:
        if len(emb_by_stone) >= 3:
            import numpy as np
            sids = list(emb_by_stone)
            X = np.array([json.loads(emb_by_stone[s]) for s in sids])
            Xc = X - X.mean(axis=0)
            _u, _s, Vt = np.linalg.svd(Xc, full_matrices=False)
            xy = Xc @ Vt[:2].T
            lo, hi = xy.min(axis=0), xy.max(axis=0)
            xy = 0.06 + 0.88 * (xy - lo) / np.maximum(hi - lo, 1e-9)
            with open(constel_path, "w") as f:
                json.dump({"n": len(sids), "stones": {
                    str(s): [round(float(xy[i, 0]), 3),
                             round(float(xy[i, 1]), 3)]
                    for i, s in enumerate(sids)}}, f, separators=(",", ":"))
            constel_n = len(sids)
        elif os.path.exists(constel_path):
            os.remove(constel_path)
    except Exception as e:
        print(f"constellation skipped: {e}")

    # letterforms: per-character shape clustering (PCA over normalized crops)
    letters_path = os.path.join(os.path.dirname(os.path.abspath(OUT_PATH)),
                                "letters.json")
    letters_n = 0
    try:
        if letter_rows:
            import numpy as np

            import letters_core
            years = {s["id"]: s["year"] for s in data["stones"]}
            by_ch = {}
            for row in letter_rows:
                by_ch.setdefault(row["ch"], []).append(row)
            out = []
            for ch, rows_ in by_ch.items():
                vecs, kept = [], []
                for row in rows_:
                    try:
                        vecs.append(letters_core.crop_vector(row["id"]))
                        kept.append(row)
                    except OSError:
                        continue
                if not kept:
                    continue
                if len(kept) >= 3:
                    X = np.array(vecs)
                    Xc = X - X.mean(axis=0)
                    _u, _s, Vt = np.linalg.svd(Xc, full_matrices=False)
                    xy = Xc @ Vt[:2].T
                    lo, hi = xy.min(axis=0), xy.max(axis=0)
                    xy = 0.08 + 0.84 * (xy - lo) / np.maximum(hi - lo, 1e-9)
                else:
                    xy = np.full((len(kept), 2), 0.5)
                for i, row in enumerate(kept):
                    out.append([row["id"], row["ch"], row["stone_id"],
                                round(float(xy[i, 0]), 3),
                                round(float(xy[i, 1]), 3),
                                years.get(row["stone_id"])])
            if out:
                with open(letters_path, "w") as f:
                    json.dump({"n": len(out), "letters": out}, f,
                              separators=(",", ":"))
                letters_n = len(out)
        elif os.path.exists(letters_path):
            os.remove(letters_path)
    except Exception as e:
        print(f"letterforms skipped: {e}")

    return {"stones": len(data["stones"]),
            "cemeteries": len(data["cemeteries"]),
            "shapes_analyzed": morpho_n,
            "constellation": constel_n,
            "letters": letters_n,
            "path": os.path.abspath(OUT_PATH)}


if __name__ == "__main__":
    print(export())
