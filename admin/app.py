"""Local admin app for the slate gravestone library.

Run:  python app.py   →  http://localhost:5050
Everything runs locally; nothing here is exposed to the internet.
"""
import os

from flask import Flask, jsonify, request, send_from_directory, send_file, abort

import db
import images
import r2
import publish as publish_mod

app = Flask(__name__, static_folder="static", static_url_path="/static")
db.init()


# ---------- pages / media ----------

@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/media/<int:photo_id>/<name>")
def media(photo_id, name):
    if name not in ("thumb.jpg", "disp.jpg"):
        abort(404)
    return send_from_directory(images.photo_dir(photo_id), name)


@app.get("/orig")
def orig():
    """Preview an original image during import (local use only)."""
    path = os.path.abspath(request.args.get("path", ""))
    src = os.path.abspath(_source_dir())
    if not src or not path.startswith(src) or not os.path.exists(path):
        abort(404)
    return send_file(path)


def _source_dir():
    return r2.load_config().get("photo_source_dir", "")


# ---------- summary ----------

@app.get("/api/summary")
def summary():
    con = db.connect()
    out = {
        "cemeteries": con.execute("SELECT COUNT(*) c FROM cemeteries").fetchone()["c"],
        "stones": con.execute("SELECT COUNT(*) c FROM stones").fetchone()["c"],
        "photos": con.execute("SELECT COUNT(*) c FROM photos").fetchone()["c"],
        "unsynced": con.execute(
            "SELECT COUNT(*) c FROM photos WHERE r2_synced=0").fetchone()["c"],
        "untagged": con.execute(
            "SELECT COUNT(*) c FROM stones WHERE id NOT IN "
            "(SELECT stone_id FROM stone_tags)").fetchone()["c"],
        "r2_configured": r2.r2_configured(),
        "source_dir": _source_dir(),
    }
    con.close()
    return jsonify(out)


# ---------- cemeteries ----------

@app.get("/api/cemeteries")
def cemeteries():
    con = db.connect()
    rows = [dict(r) for r in con.execute(
        """SELECT c.*, COUNT(s.id) AS stones FROM cemeteries c
           LEFT JOIN stones s ON s.cemetery_id=c.id
           GROUP BY c.id ORDER BY c.name""")]
    con.close()
    return jsonify(rows)


@app.post("/api/cemeteries")
def add_cemetery():
    d = request.json
    con = db.connect()
    cur = con.execute(
        "INSERT INTO cemeteries(name, city, state, country, lat, lng, notes) "
        "VALUES(?,?,?,?,?,?,?)",
        (d["name"], d.get("city", ""), d.get("state", ""),
         d.get("country", "United States"), d.get("lat"), d.get("lng"),
         d.get("notes", "")))
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return jsonify({"id": new_id})


@app.put("/api/cemeteries/<int:cid>")
def edit_cemetery(cid):
    d = request.json
    con = db.connect()
    con.execute(
        "UPDATE cemeteries SET name=?, city=?, state=?, country=?, lat=?, lng=?, "
        "notes=? WHERE id=?",
        (d["name"], d.get("city", ""), d.get("state", ""),
         d.get("country", ""), d.get("lat"), d.get("lng"),
         d.get("notes", ""), cid))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.delete("/api/cemeteries/<int:cid>")
def del_cemetery(cid):
    con = db.connect()
    n = con.execute("SELECT COUNT(*) c FROM stones WHERE cemetery_id=?",
                    (cid,)).fetchone()["c"]
    if n:
        con.close()
        return jsonify({"error": f"Cemetery has {n} gravestones; move or delete them first."}), 400
    con.execute("DELETE FROM cemeteries WHERE id=?", (cid,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


# ---------- categories & tags ----------

@app.get("/api/categories")
def categories():
    con = db.connect()
    cats = [dict(r) for r in con.execute(
        "SELECT id, name, single_select AS single, sort FROM categories "
        "ORDER BY sort, name")]
    tags = con.execute(
        """SELECT t.id, t.category_id, t.name, COUNT(st.stone_id) AS used
           FROM tags t LEFT JOIN stone_tags st ON st.tag_id=t.id
           GROUP BY t.id ORDER BY t.name""").fetchall()
    for c in cats:
        c["tags"] = [dict(t) for t in tags if t["category_id"] == c["id"]]
    con.close()
    return jsonify(cats)


@app.post("/api/categories")
def add_category():
    d = request.json
    con = db.connect()
    try:
        cur = con.execute(
            "INSERT INTO categories(name, single_select, sort) VALUES(?,?,?)",
            (d["name"].strip(), 1 if d.get("single") else 0, d.get("sort", 100)))
        con.commit()
        return jsonify({"id": cur.lastrowid})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        con.close()


@app.post("/api/tags")
def add_tag():
    d = request.json
    con = db.connect()
    try:
        cur = con.execute("INSERT INTO tags(category_id, name) VALUES(?,?)",
                          (d["category_id"], d["name"].strip()))
        con.commit()
        return jsonify({"id": cur.lastrowid})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        con.close()


@app.put("/api/tags/<int:tid>")
def rename_tag(tid):
    con = db.connect()
    con.execute("UPDATE tags SET name=? WHERE id=?",
                (request.json["name"].strip(), tid))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.delete("/api/tags/<int:tid>")
def del_tag(tid):
    con = db.connect()
    used = con.execute("SELECT COUNT(*) c FROM stone_tags WHERE tag_id=?",
                       (tid,)).fetchone()["c"]
    if used and request.args.get("force") != "1":
        con.close()
        return jsonify({"error": f"Tag is used on {used} gravestones."}), 400
    con.execute("DELETE FROM stone_tags WHERE tag_id=?", (tid,))
    con.execute("DELETE FROM tags WHERE id=?", (tid,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


# ---------- stones ----------

@app.get("/api/stones")
def stones():
    con = db.connect()
    where, params = [], []
    if request.args.get("cemetery"):
        where.append("s.cemetery_id=?")
        params.append(request.args["cemetery"])
    if request.args.get("untagged") == "1":
        where.append("s.id NOT IN (SELECT stone_id FROM stone_tags)")
    if request.args.get("q"):
        where.append("(s.title LIKE ? OR s.notes LIKE ?)")
        params += [f"%{request.args['q']}%"] * 2
    sql = f"""SELECT s.id, s.cemetery_id, s.title, s.year, s.date_text,
                     c.name AS cemetery,
                     (SELECT id FROM photos WHERE stone_id=s.id
                      ORDER BY is_primary DESC, id LIMIT 1) AS thumb,
                     (SELECT COUNT(*) FROM photos WHERE stone_id=s.id) AS nphotos,
                     (SELECT COUNT(*) FROM stone_tags WHERE stone_id=s.id) AS ntags
              FROM stones s JOIN cemeteries c ON c.id=s.cemetery_id
              {'WHERE ' + ' AND '.join(where) if where else ''}
              ORDER BY s.id DESC"""
    rows = [dict(r) for r in con.execute(sql, params)]
    con.close()
    return jsonify(rows)


@app.get("/api/stones/<int:sid>")
def stone(sid):
    con = db.connect()
    s = con.execute("SELECT * FROM stones WHERE id=?", (sid,)).fetchone()
    if not s:
        con.close()
        abort(404)
    out = dict(s)
    out["photos"] = [dict(r) for r in con.execute(
        "SELECT id, filename, width, height, is_primary, r2_synced "
        "FROM photos WHERE stone_id=? ORDER BY is_primary DESC, id", (sid,))]
    out["tag_ids"] = [r["tag_id"] for r in con.execute(
        "SELECT tag_id FROM stone_tags WHERE stone_id=?", (sid,))]
    con.close()
    return jsonify(out)


@app.put("/api/stones/<int:sid>")
def edit_stone(sid):
    d = request.json
    con = db.connect()
    con.execute(
        "UPDATE stones SET title=?, year=?, birth_year=?, date_text=?, notes=?, "
        "cemetery_id=? WHERE id=?",
        (d.get("title", ""), d.get("year"), d.get("birth_year"),
         d.get("date_text", ""), d.get("notes", ""), d["cemetery_id"], sid))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.put("/api/stones/<int:sid>/tags")
def set_stone_tags(sid):
    ids = request.json.get("tag_ids", [])
    con = db.connect()
    con.execute("DELETE FROM stone_tags WHERE stone_id=?", (sid,))
    con.executemany("INSERT OR IGNORE INTO stone_tags(stone_id, tag_id) VALUES(?,?)",
                    [(sid, t) for t in ids])
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.delete("/api/stones/<int:sid>")
def del_stone(sid):
    con = db.connect()
    con.execute("DELETE FROM stones WHERE id=?", (sid,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.put("/api/photos/<int:pid>/primary")
def set_primary(pid):
    con = db.connect()
    sid = con.execute("SELECT stone_id FROM photos WHERE id=?",
                      (pid,)).fetchone()["stone_id"]
    con.execute("UPDATE photos SET is_primary=0 WHERE stone_id=?", (sid,))
    con.execute("UPDATE photos SET is_primary=1 WHERE id=?", (pid,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.put("/api/photos/<int:pid>/move")
def move_photo(pid):
    con = db.connect()
    con.execute("UPDATE photos SET stone_id=?, is_primary=0 WHERE id=?",
                (request.json["stone_id"], pid))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.delete("/api/photos/<int:pid>")
def del_photo(pid):
    con = db.connect()
    con.execute("DELETE FROM photos WHERE id=?", (pid,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


# ---------- import ----------

@app.get("/api/import/scan")
def scan():
    src = request.args.get("dir") or _source_dir()
    if not src or not os.path.isdir(src):
        return jsonify({"error": f"Folder not found: {src}"}), 400
    con = db.connect()
    known = {r["orig_path"] for r in con.execute("SELECT orig_path FROM photos")}
    con.close()
    files = []
    for root, _dirs, names in os.walk(src):
        for n in sorted(names):
            if os.path.splitext(n)[1].lower() in images.RASTER_EXTS:
                p = os.path.join(root, n)
                if p not in known:
                    files.append({"path": p,
                                  "rel": os.path.relpath(p, src),
                                  "name": n})
    return jsonify({"dir": src, "files": files})


@app.post("/api/import")
def do_import():
    """Import a list of files into ONE stone (front end calls once per stone)."""
    d = request.json
    paths, cem_id = d["paths"], d["cemetery_id"]
    con = db.connect()
    cur = con.execute("INSERT INTO stones(cemetery_id) VALUES(?)", (cem_id,))
    sid = cur.lastrowid
    imported, errors = [], []
    for i, p in enumerate(paths):
        try:
            cur = con.execute(
                "INSERT INTO photos(stone_id, filename, orig_path, is_primary) "
                "VALUES(?,?,?,?)",
                (sid, os.path.basename(p), p, 1 if i == 0 else 0))
            pid = cur.lastrowid
            w, h = images.make_derivatives(p, pid)
            con.execute("UPDATE photos SET width=?, height=?, taken=? WHERE id=?",
                        (w, h, images.exif_taken(p), pid))
            imported.append(pid)
        except Exception as e:
            con.execute("DELETE FROM photos WHERE id=?", (pid,))
            errors.append({"path": p, "error": str(e)})
    if not imported:
        con.execute("DELETE FROM stones WHERE id=?", (sid,))
        sid = None
    con.commit()
    con.close()
    return jsonify({"stone_id": sid, "photos": imported, "errors": errors})


# ---------- R2 sync & publish ----------

@app.post("/api/r2/sync")
def r2_sync():
    if not r2.r2_configured():
        return jsonify({"error": "R2 is not configured — edit config.json."}), 400
    limit = int(request.json.get("limit", 10)) if request.json else 10
    con = db.connect()
    rows = con.execute("SELECT id FROM photos WHERE r2_synced=0 LIMIT ?",
                       (limit,)).fetchall()
    done, errors = [], []
    for row in rows:
        pid = row["id"]
        try:
            thumb, disp = images.derivative_paths(pid)
            r2.upload_photo(pid, thumb, disp)
            con.execute("UPDATE photos SET r2_synced=1 WHERE id=?", (pid,))
            con.commit()
            done.append(pid)
        except Exception as e:
            errors.append({"id": pid, "error": str(e)})
            break  # likely config/network issue; stop the batch
    remaining = con.execute(
        "SELECT COUNT(*) c FROM photos WHERE r2_synced=0").fetchone()["c"]
    con.close()
    return jsonify({"done": done, "errors": errors, "remaining": remaining})


@app.post("/api/publish")
def do_publish():
    if not r2.public_base():
        return jsonify({"error": "Set r2.public_base_url in config.json first."}), 400
    res = publish_mod.export()
    return jsonify(res)


if __name__ == "__main__":
    print("Slate gravestone admin → http://localhost:5050")
    app.run(port=5050, debug=False)
