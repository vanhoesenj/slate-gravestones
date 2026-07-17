"""Local admin app for the slate gravestone library.

Run:  python app.py   →  http://localhost:5050
Everything runs locally; nothing here is exposed to the internet.
"""
import json
import os
import threading
import time

from flask import Flask, jsonify, request, send_from_directory, send_file, abort

import db
import images
import r2
import publish as publish_mod

app = Flask(__name__, static_folder="static", static_url_path="/static")
# never cache admin assets — a stale cached page after an update can save
# incomplete data
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
db.init()


# ---------- pages / media ----------

@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/media/<int:photo_id>/<name>")
def media(photo_id, name):
    if name not in ("thumb.jpg", "disp.jpg", "enh.jpg", "depth.jpg"):
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

@app.get("/api/guide")
def guide():
    path = os.path.join(os.path.dirname(__file__), "..", "ADMIN-GUIDE.md")
    try:
        with open(path) as f:
            return jsonify({"md": f.read()})
    except OSError:
        return jsonify({"md": "ADMIN-GUIDE.md not found in the repo root."})


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
        "drafts": con.execute(
            "SELECT COUNT(*) c FROM stones "
            "WHERE transcription LIKE '[DRAFT]%'").fetchone()["c"],
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
        where.append(
            "(s.title LIKE ? OR s.notes LIKE ? OR s.transcription LIKE ? OR "
            "EXISTS (SELECT 1 FROM persons p WHERE p.stone_id=s.id AND "
            "p.name LIKE ?))")
        params += [f"%{request.args['q']}%"] * 4
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
    out["persons"] = [dict(r) for r in con.execute(
        "SELECT id, name, birth_year AS birth, death_year AS death "
        "FROM persons WHERE stone_id=? ORDER BY sort, id", (sid,))]
    out["photos"] = [dict(r) for r in con.execute(
        "SELECT id, filename, width, height, is_primary, r2_synced "
        "FROM photos WHERE stone_id=? ORDER BY is_primary DESC, id", (sid,))]
    out["tag_ids"] = [r["tag_id"] for r in con.execute(
        "SELECT tag_id FROM stone_tags WHERE stone_id=?", (sid,))]
    con.close()
    return jsonify(out)


@app.put("/api/stones/<int:sid>")
def edit_stone(sid):
    """Partial update: only fields present in the payload are written, so an
    out-of-date client can never blank a field it doesn't know about."""
    d = request.json
    allowed = ["title", "year", "birth_year", "date_text", "notes",
               "transcription", "submitted_by", "cemetery_id"]
    sets = [f"{k}=?" for k in allowed if k in d]
    vals = [d[k] for k in allowed if k in d]
    con = db.connect()
    if sets:
        con.execute(f"UPDATE stones SET {', '.join(sets)} WHERE id=?",
                    (*vals, sid))
    if "persons" in d:
        con.execute("DELETE FROM persons WHERE stone_id=?", (sid,))
        deaths, births, kept = [], [], 0
        for i, p in enumerate(d["persons"]):
            name = (p.get("name") or "").strip()
            b, dd = p.get("birth"), p.get("death")
            if not name and b is None and dd is None:
                continue
            con.execute(
                "INSERT INTO persons(stone_id, name, birth_year, death_year, "
                "sort) VALUES(?,?,?,?,?)", (sid, name, b, dd, i))
            kept += 1
            if dd:
                deaths.append(dd)
            if b:
                births.append(b)
        # keep the stone-level chart/filter fields in sync: principal year =
        # earliest death on the stone (best proxy for carving date)
        con.execute("UPDATE stones SET year=?, birth_year=? WHERE id=?",
                    (min(deaths) if deaths else None,
                     births[0] if kept == 1 and births else None, sid))
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


# ---------- outlines ----------

OUTLINE_PROG = {"running": False, "total": 0, "done": 0, "ok": 0,
                "failed": 0, "msg": ""}


def _outline_worker(ids):
    import outline_core
    errs = []
    try:
        OUTLINE_PROG["msg"] = "loading model (first run downloads ~170MB)…"
        outline_core.get_session()
        con = db.connect()
        for pid in ids:
            OUTLINE_PROG["msg"] = f"tracing photo #{pid}…"
            _thumb, disp, _enh = images.derivative_paths(pid)
            d, h = (outline_core.extract(disp) if os.path.exists(disp)
                    else (None, "no display file"))
            if d is None:
                con.execute("UPDATE photos SET outline_status='rejected', "
                            "outline_path='' WHERE id=?", (pid,))
                OUTLINE_PROG["failed"] += 1
                errs.append(f"photo #{pid}: {h}")
            else:
                con.execute("UPDATE photos SET outline_path=?, outline_h=?, "
                            "outline_status='draft' WHERE id=?", (d, h, pid))
                OUTLINE_PROG["ok"] += 1
            con.commit()
            OUTLINE_PROG["done"] += 1
        con.close()
        OUTLINE_PROG["msg"] = (f"done — {OUTLINE_PROG['ok']} drafted, "
                               f"{OUTLINE_PROG['failed']} failed"
                               + (f" ({'; '.join(errs[:3])})" if errs else ""))
    except Exception as e:
        OUTLINE_PROG["msg"] = "error: " + str(e)
    finally:
        OUTLINE_PROG["running"] = False


@app.post("/api/outlines/extract")
def outlines_extract():
    if OUTLINE_PROG["running"]:
        return jsonify({"error": "extraction already running"}), 400
    try:
        import rembg  # noqa: F401
    except ImportError:
        return jsonify({"error":
            "rembg is not installed — run: pip3 install rembg onnxruntime "
            "then restart the admin app."}), 400
    con = db.connect()
    ids = [r["id"] for r in con.execute(
        "SELECT id FROM photos WHERE outline_status='' "
        "OR outline_status IS NULL ORDER BY id")]
    con.close()
    if not ids:
        return jsonify({"started": False,
                        "msg": "No new photos to trace — all done."})
    OUTLINE_PROG.update(running=True, total=len(ids), done=0, ok=0,
                        failed=0, msg="starting…")
    threading.Thread(target=_outline_worker, args=(ids,), daemon=True).start()
    return jsonify({"started": True, "total": len(ids)})


@app.get("/api/outlines/progress")
def outlines_progress():
    return jsonify(OUTLINE_PROG)


@app.post("/api/photos/<int:pid>/retrace")
def retrace_outline(pid):
    """Synchronous single-photo re-trace (used by the ↻ button)."""
    try:
        import rembg  # noqa: F401
    except ImportError:
        return jsonify({"error": "rembg not installed"}), 400
    import outline_core
    _t, disp, _e = images.derivative_paths(pid)
    if not os.path.exists(disp):
        return jsonify({"error": "no display image for this photo"}), 400
    d, h = outline_core.extract(disp)
    con = db.connect()
    if d is None:
        con.execute("UPDATE photos SET outline_status='rejected', "
                    "outline_path='' WHERE id=?", (pid,))
        con.commit()
        con.close()
        return jsonify({"ok": False, "reason": h})
    con.execute("UPDATE photos SET outline_path=?, outline_h=?, "
                "outline_status='draft' WHERE id=?", (d, h, pid))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.get("/api/outlines")
def outlines():
    status = request.args.get("status", "draft")
    con = db.connect()
    where = "p.outline_status != ''" if status == "all" else "p.outline_status = ?"
    params = [] if status == "all" else [status]
    rows = [dict(r) for r in con.execute(
        f"""SELECT p.id, p.stone_id, p.outline_path AS d, p.outline_h AS h,
                   p.outline_status AS status, p.is_primary,
                   s.title, c.name AS cemetery
            FROM photos p JOIN stones s ON s.id=p.stone_id
            JOIN cemeteries c ON c.id=s.cemetery_id
            WHERE {where} ORDER BY p.id""", params)]
    counts = {r["outline_status"]: r["n"] for r in con.execute(
        "SELECT outline_status, COUNT(*) n FROM photos "
        "WHERE outline_status != '' GROUP BY outline_status")}
    con.close()
    return jsonify({"photos": rows, "counts": counts})


@app.put("/api/photos/<int:pid>/outline")
def set_outline_status(pid):
    status = request.json.get("status")
    if status not in ("draft", "approved", "rejected"):
        return jsonify({"error": "bad status"}), 400
    con = db.connect()
    con.execute("UPDATE photos SET outline_status=? WHERE id=?", (status, pid))
    con.commit()
    con.close()
    return jsonify({"ok": True})


# ---------- relief maps (virtual raking light) ----------

DEPTH_PROG = {"running": False, "total": 0, "done": 0, "ok": 0,
              "failed": 0, "msg": ""}


def _depth_worker(ids):
    import depth_core
    try:
        DEPTH_PROG["msg"] = "loading depth model (first run downloads ~100MB)…"
        depth_core.get_pipe()
        con = db.connect()
        for pid in ids:
            DEPTH_PROG["msg"] = f"estimating depth for photo #{pid}…"
            _t, disp, _e = images.derivative_paths(pid)
            out = os.path.join(images.photo_dir(pid), "depth.jpg")
            try:
                depth_core.build_depth(disp, out)
                con.execute("UPDATE photos SET has_depth=1, r2_synced=0 "
                            "WHERE id=?", (pid,))
                DEPTH_PROG["ok"] += 1
            except Exception as e:
                DEPTH_PROG["failed"] += 1
                DEPTH_PROG["msg"] = f"photo #{pid} failed: {e}"
            con.commit()
            DEPTH_PROG["done"] += 1
        con.close()
        DEPTH_PROG["msg"] = (f"done — {DEPTH_PROG['ok']} built, "
                             f"{DEPTH_PROG['failed']} failed. "
                             "Now run 'Sync images to R2' on the Publish tab.")
    except Exception as e:
        DEPTH_PROG["msg"] = "error: " + str(e)
    finally:
        DEPTH_PROG["running"] = False


@app.post("/api/depth/build")
def depth_build():
    if DEPTH_PROG["running"]:
        return jsonify({"error": "already running"}), 400
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return jsonify({"error":
            "Depth model not installed — run: pip3 install torch transformers "
            "(one-time, ~2GB) then restart the admin app."}), 400
    con = db.connect()
    ids = []
    for r in con.execute("SELECT id FROM photos WHERE has_depth=0 ORDER BY id"):
        _t, disp, _e = images.derivative_paths(r["id"])
        if os.path.exists(disp):
            ids.append(r["id"])
    con.close()
    if not ids:
        return jsonify({"started": False,
                        "msg": "No new photos — all relief maps built."})
    DEPTH_PROG.update(running=True, total=len(ids), done=0, ok=0,
                      failed=0, msg="starting…")
    threading.Thread(target=_depth_worker, args=(ids,), daemon=True).start()
    return jsonify({"started": True, "total": len(ids)})


@app.get("/api/depth/progress")
def depth_progress():
    return jsonify(DEPTH_PROG)


# ---------- Welsh audio (Piper TTS) ----------

AUDIO_PROG = {"running": False, "total": 0, "done": 0, "ok": 0,
              "failed": 0, "msg": ""}
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "media", "audio")


def _audio_worker(rows):
    import audio_core
    errs = []
    try:
        AUDIO_PROG["msg"] = "loading Welsh voice (first run downloads ~65MB)…"
        audio_core.get_voice()
        con = db.connect()
        for sid, text in rows:
            AUDIO_PROG["msg"] = f"reading gravestone #{sid} aloud…"
            wav = os.path.join(AUDIO_DIR, f"{sid}.wav")
            try:
                audio_core.synth(text, wav)
                r2.upload_object(f"audio/{sid}.wav", wav, "audio/wav")
                con.execute("UPDATE stones SET has_audio=1 WHERE id=?", (sid,))
                AUDIO_PROG["ok"] += 1
            except Exception as e:
                AUDIO_PROG["failed"] += 1
                errs.append(f"stone #{sid}: {type(e).__name__}: {e}")
            con.commit()
            AUDIO_PROG["done"] += 1
        con.close()
        AUDIO_PROG["msg"] = (f"done — {AUDIO_PROG['ok']} recordings built and "
                             f"uploaded, {AUDIO_PROG['failed']} failed"
                             + (f" (first error: {errs[0]})" if errs else "")
                             + ". Export + push to publish.")
    except Exception as e:
        AUDIO_PROG["msg"] = "error: " + str(e)
    finally:
        AUDIO_PROG["running"] = False


@app.post("/api/audio/build")
def audio_build():
    if AUDIO_PROG["running"]:
        return jsonify({"error": "already running"}), 400
    try:
        import piper  # noqa: F401
    except ImportError:
        return jsonify({"error": "Piper is not installed — run: "
                        "pip3 install piper-tts then restart the admin app."}), 400
    if not r2.r2_configured():
        return jsonify({"error": "R2 must be configured (audio uploads "
                        "directly to the bucket)."}), 400
    import audio_core
    con = db.connect()
    rows = [(r["id"], r["transcription"]) for r in con.execute(
        "SELECT id, transcription FROM stones "
        "WHERE has_audio=0 AND transcription != ''")
        if audio_core.is_welsh(r["transcription"])]
    con.close()
    if not rows:
        return jsonify({"started": False,
                        "msg": "No new Welsh inscriptions to record."})
    AUDIO_PROG.update(running=True, total=len(rows), done=0, ok=0,
                      failed=0, msg="starting…")
    threading.Thread(target=_audio_worker, args=(rows,), daemon=True).start()
    return jsonify({"started": True, "total": len(rows)})


@app.get("/api/audio/progress")
def audio_progress():
    return jsonify(AUDIO_PROG)


# ---------- visual constellation (CLIP embeddings) ----------

EMB_PROG = {"running": False, "total": 0, "done": 0, "ok": 0,
            "failed": 0, "msg": ""}


def _emb_worker(ids):
    import clip_core
    try:
        EMB_PROG["msg"] = "loading CLIP model (first run downloads ~600MB)…"
        clip_core.get_model()
        con = db.connect()
        for pid in ids:
            EMB_PROG["msg"] = f"embedding photo #{pid}…"
            thumb, _disp, _enh = images.derivative_paths(pid)
            try:
                vec = clip_core.embed(thumb)
                con.execute("INSERT OR REPLACE INTO photo_emb(photo_id, vec) "
                            "VALUES(?,?)", (pid, json.dumps(vec)))
                EMB_PROG["ok"] += 1
            except Exception as e:
                EMB_PROG["failed"] += 1
                EMB_PROG["msg"] = f"photo #{pid} failed: {e}"
            con.commit()
            EMB_PROG["done"] += 1
        con.close()
        EMB_PROG["msg"] = (f"done — {EMB_PROG['ok']} embedded, "
                           f"{EMB_PROG['failed']} failed. Export + push to "
                           "publish the constellation.")
    except Exception as e:
        EMB_PROG["msg"] = "error: " + str(e)
    finally:
        EMB_PROG["running"] = False


@app.post("/api/constellation/build")
def emb_build():
    if EMB_PROG["running"]:
        return jsonify({"error": "already running"}), 400
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return jsonify({"error": "Not installed — run: pip3 install torch "
                        "transformers then restart the admin app."}), 400
    con = db.connect()
    ids = []
    for r in con.execute(
            "SELECT id FROM photos WHERE id NOT IN "
            "(SELECT photo_id FROM photo_emb) ORDER BY id"):
        thumb = images.derivative_paths(r["id"])[0]
        if os.path.exists(thumb):
            ids.append(r["id"])
    con.close()
    if not ids:
        return jsonify({"started": False, "msg": "All photos embedded."})
    EMB_PROG.update(running=True, total=len(ids), done=0, ok=0,
                    failed=0, msg="starting…")
    threading.Thread(target=_emb_worker, args=(ids,), daemon=True).start()
    return jsonify({"started": True, "total": len(ids)})


@app.get("/api/constellation/progress")
def emb_progress():
    return jsonify(EMB_PROG)


# ---------- letterforms ----------

LET_PROG = {"running": False, "total": 0, "done": 0, "ok": 0,
            "failed": 0, "msg": ""}


def _letters_worker(rows):
    import letters_core
    try:
        con = db.connect()
        for pid, sid in rows:
            LET_PROG["msg"] = f"reading letters on photo #{pid}…"
            _t, _d, enh = images.derivative_paths(pid)
            try:
                found, img = letters_core.extract_letters(enh)
                for ch, box, conf in found:
                    cur = con.execute(
                        "INSERT INTO letters(photo_id, stone_id, ch, conf) "
                        "VALUES(?,?,?,?)", (pid, sid, ch, conf))
                    lid = cur.lastrowid
                    path = letters_core.save_crop(img, box, lid)
                    if r2.r2_configured():
                        r2.upload_object(f"letters/{lid}.jpg", path,
                                         "image/jpeg")
                    LET_PROG["ok"] += 1
                con.execute("UPDATE photos SET letters_scanned=1 WHERE id=?",
                            (pid,))
            except Exception as e:
                LET_PROG["failed"] += 1
                LET_PROG["msg"] = f"photo #{pid} failed: {e}"
            con.commit()
            LET_PROG["done"] += 1
        con.close()
        LET_PROG["msg"] = (f"done — {LET_PROG['ok']} letters found across "
                           f"{LET_PROG['done']} photos. Review below, then "
                           "Export + push.")
    except Exception as e:
        LET_PROG["msg"] = "error: " + str(e)
    finally:
        LET_PROG["running"] = False


@app.post("/api/letters/build")
def letters_build():
    if LET_PROG["running"]:
        return jsonify({"error": "already running"}), 400
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception:
        return jsonify({"error": "Tesseract not available — run: "
                        "brew install tesseract && pip3 install pytesseract, "
                        "then restart the admin app."}), 400
    con = db.connect()
    rows = []
    for r in con.execute("SELECT id, stone_id FROM photos "
                         "WHERE letters_scanned=0 ORDER BY id"):
        if os.path.exists(images.derivative_paths(r["id"])[2]):
            rows.append((r["id"], r["stone_id"]))
    con.close()
    if not rows:
        return jsonify({"started": False, "msg": "All photos scanned."})
    LET_PROG.update(running=True, total=len(rows), done=0, ok=0,
                    failed=0, msg="starting…")
    threading.Thread(target=_letters_worker, args=(rows,), daemon=True).start()
    return jsonify({"started": True, "total": len(rows)})


@app.get("/api/letters/progress")
def letters_progress():
    return jsonify(LET_PROG)


@app.get("/api/letters")
def letters_list():
    ch = request.args.get("ch", "")
    unrev = " AND reviewed=0" if request.args.get("unreviewed") == "1" else ""
    con = db.connect()
    counts = {r["ch"]: r["n"] for r in con.execute(
        f"SELECT ch, COUNT(*) n FROM letters WHERE status='ok'{unrev} "
        "GROUP BY ch")}
    rows = [dict(r) for r in con.execute(
        "SELECT l.id, l.ch, l.stone_id, l.conf, l.reviewed, s.title "
        "FROM letters l JOIN stones s ON s.id=l.stone_id "
        f"WHERE l.status='ok'{unrev} AND l.ch=? ORDER BY l.id",
        (ch,))] if ch else []
    con.close()
    return jsonify({"counts": counts, "letters": rows})


@app.put("/api/letters/<int:lid>")
def letters_update(lid):
    d = request.json
    con = db.connect()
    if d.get("status") in ("ok", "bad"):
        con.execute("UPDATE letters SET status=?, reviewed=1 WHERE id=?",
                    (d["status"], lid))
    if d.get("ch"):
        con.execute("UPDATE letters SET ch=?, reviewed=1 WHERE id=?",
                    (d["ch"].strip().upper()[:1], lid))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.post("/api/letters/mark_reviewed")
def letters_mark_reviewed():
    ch = request.json.get("ch", "")
    con = db.connect()
    cur = con.execute(
        "UPDATE letters SET reviewed=1 WHERE status='ok' AND ch=?", (ch,))
    con.commit()
    n = cur.rowcount
    con.close()
    return jsonify({"marked": n})


@app.get("/media_letters/<int:lid>.jpg")
def media_letter(lid):
    import letters_core
    return send_from_directory(letters_core.LETTER_DIR, f"{lid}.jpg")


# ---------- transcription drafts ----------
# A drafts file (data/transcription_drafts.json) is a list of
# {"stone_id": 3, "transcription": "ER COF\nam\n…", "translation": "In memory…"}.
# Claude (or any OCR pipeline) writes it; the Apply button loads it into empty
# fields only, prefixed [DRAFT], so it can never overwrite reviewed work.

DRAFTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data",
                           "transcription_drafts.json")


@app.get("/api/drafts/status")
def drafts_status():
    if not os.path.exists(DRAFTS_PATH):
        return jsonify({"found": False})
    try:
        with open(DRAFTS_PATH) as f:
            drafts = json.load(f)
        return jsonify({"found": True, "count": len(drafts)})
    except Exception as e:
        return jsonify({"found": True, "error": str(e)})


@app.post("/api/drafts/apply")
def drafts_apply():
    if not os.path.exists(DRAFTS_PATH):
        return jsonify({"error": "No drafts file found."}), 400
    with open(DRAFTS_PATH) as f:
        drafts = json.load(f)
    con = db.connect()
    applied = skipped = missing = 0
    for d in drafts:
        s = con.execute("SELECT transcription, notes FROM stones WHERE id=?",
                        (d.get("stone_id"),)).fetchone()
        if not s:
            missing += 1
            continue
        did = False
        if d.get("transcription") and not (s["transcription"] or "").strip():
            con.execute("UPDATE stones SET transcription=? WHERE id=?",
                        ("[DRAFT] " + d["transcription"].strip(),
                         d["stone_id"]))
            did = True
        if d.get("translation") and not (s["notes"] or "").strip():
            con.execute("UPDATE stones SET notes=? WHERE id=?",
                        ("[DRAFT translation] " + d["translation"].strip(),
                         d["stone_id"]))
            did = True
        applied += did
        skipped += not did
    con.commit()
    con.close()
    os.rename(DRAFTS_PATH,
              DRAFTS_PATH + ".applied-" + time.strftime("%Y%m%d-%H%M%S"))
    return jsonify({"applied": applied, "skipped": skipped, "missing": missing})


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
            thumb, disp, enh = images.derivative_paths(pid)
            depth = os.path.join(images.photo_dir(pid), "depth.jpg")
            r2.upload_photo(pid, thumb, disp, enh, depth)
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
