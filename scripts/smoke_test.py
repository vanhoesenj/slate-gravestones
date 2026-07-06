"""End-to-end smoke test using Flask's test client (no server needed).
Creates test images, a cemetery, imports, tags, syncs (skipped without R2),
and publishes. Run from repo root:  python scripts/smoke_test.py
Cleans up after itself (removes test rows, media, and library.json)."""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "admin"))

from PIL import Image, ImageDraw  # noqa: E402


def make_test_photos(d, n=3):
    paths = []
    for i in range(n):
        img = Image.new("RGB", (1600, 2400), (90 + i * 20, 100, 110))
        dr = ImageDraw.Draw(img)
        dr.polygon([(300, 600), (800, 300), (1300, 600), (1300, 2200),
                    (300, 2200)], fill=(60, 70, 78))
        dr.text((700, 1200), f"TEST {i}", fill=(230, 230, 220))
        p = os.path.join(d, f"test_stone_{i}.jpg")
        img.save(p, "JPEG")
        paths.append(p)
    return paths


def main():
    assert os.environ.get("SG_DB"), \
        "Run with a throwaway DB:  SG_DB=/tmp/t.db python3 scripts/smoke_test.py"
    # keep generated thumbnails in a throwaway dir so test cleanup can NEVER
    # delete real media (photo IDs in the test DB overlap with real ones)
    os.environ["SG_MEDIA"] = tempfile.mkdtemp(prefix="sg_media_")

    # temp config so scan + publish work
    cfg_path = os.path.join(ROOT, "config.json")
    had_cfg = os.path.exists(cfg_path)
    src = tempfile.mkdtemp(prefix="sg_test_")
    if not had_cfg:
        with open(cfg_path, "w") as f:
            json.dump({"photo_source_dir": src,
                       "r2": {"public_base_url": "https://example.test"}}, f)

    # publishing during the test overwrites docs/data/library.json — keep the
    # real one safe and restore it afterwards
    lib_path = os.path.join(ROOT, "docs", "data", "library.json")
    lib_backup = open(lib_path).read() if os.path.exists(lib_path) else None

    import app as appmod
    c = appmod.app.test_client()

    def call(method, url, **kw):
        r = getattr(c, method)(url, **kw)
        body = r.get_json()
        assert r.status_code < 400, f"{method} {url} -> {r.status_code}: {body}"
        return body

    make_test_photos(src)
    print("summary:", call("get", "/api/summary"))

    cem = call("post", "/api/cemeteries", json={
        "name": "TEST West Cemetery", "city": "Middletown Springs",
        "state": "Vermont", "lat": 43.48, "lng": -73.12})
    print("cemetery id:", cem["id"])

    scan = call("get", f"/api/import/scan?dir={src}")
    assert len(scan["files"]) == 3, scan
    print("scan found:", [f["name"] for f in scan["files"]])

    # one stone from two photos + one stone from one photo
    paths = [f["path"] for f in scan["files"]]
    s1 = call("post", "/api/import", json={"paths": paths[:2], "cemetery_id": cem["id"]})
    s2 = call("post", "/api/import", json={"paths": paths[2:], "cemetery_id": cem["id"]})
    assert not s1["errors"] and not s2["errors"], (s1, s2)
    print("stones:", s1["stone_id"], s2["stone_id"])

    # rescan should find nothing new
    assert len(call("get", f"/api/import/scan?dir={src}")["files"]) == 0

    # derivative files exist (thumb, display, enhanced)
    import images
    t, d, e = images.derivative_paths(s1["photos"][0])
    assert os.path.exists(t) and os.path.exists(d) and os.path.exists(e)
    im = Image.open(d)
    assert max(im.size) == 2000, im.size
    print("derivatives ok:", im.size)

    # media endpoint serves the thumb
    r = c.get(f"/media/{s1['photos'][0]}/thumb.jpg")
    assert r.status_code == 200 and r.data[:2] == b"\xff\xd8"

    # tags: add category, add tag, tag the stone
    cats = call("get", "/api/categories")
    shape = next(c_ for c_ in cats if c_["name"] == "Shape")
    icon = next(c_ for c_ in cats if c_["name"] == "Iconography")
    assert len(shape["tags"]) == 20 and shape["single"] == 1
    newcat = call("post", "/api/categories", json={"name": "TEST Carver", "single": True})
    newtag = call("post", "/api/tags", json={"category_id": newcat["id"], "name": "Zerubbabel Collins"})
    call("put", f"/api/stones/{s1['stone_id']}", json={
        "title": "Test Person", "year": 1794, "date_text": "Jan. 1, 1794",
        "notes": "", "cemetery_id": cem["id"]})
    call("put", f"/api/stones/{s1['stone_id']}/tags", json={
        "tag_ids": [shape["tags"][1]["id"], icon["tags"][0]["id"], newtag["id"]]})
    st = call("get", f"/api/stones/{s1['stone_id']}")
    assert len(st["tag_ids"]) == 3 and st["year"] == 1794
    print("tagging ok:", st["tag_ids"])

    # multiple persons on one stone; stone year syncs to earliest death
    call("put", f"/api/stones/{s1['stone_id']}", json={
        "cemetery_id": cem["id"],
        "persons": [{"name": "Catharine", "death": 1852},
                    {"name": "Richard", "birth": 1863, "death": 1863}]})
    st = call("get", f"/api/stones/{s1['stone_id']}")
    assert len(st["persons"]) == 2 and st["year"] == 1852, st
    print("persons ok:", [p["name"] for p in st["persons"]])

    # primary photo swap
    call("put", f"/api/photos/{s1['photos'][1]}/primary")

    # publish
    pub = call("post", "/api/publish")
    print("publish:", pub)
    with open(pub["path"]) as f:
        data = json.load(f)
    assert data["imageBase"], "imageBase should come from config.json"
    assert len(data["stones"]) == 2
    assert data["stones"][0]["photos"][0]["id"] == s1["photos"][1]  # primary first
    assert any(t["name"] == "Zerubbabel Collins" for t in data["tags"])
    assert len(data["stones"][0]["persons"]) == 2
    print("library.json ok:", {k: len(v) for k, v in data.items() if isinstance(v, list)})

    # stones list filters
    lst = call("get", f"/api/stones?cemetery={cem['id']}&q=Test")
    assert len(lst) == 1 and lst[0]["ntags"] == 3

    # ---- cleanup ----
    import db
    con = db.connect()
    for pid in s1["photos"] + s2["photos"]:
        shutil.rmtree(images.photo_dir(pid), ignore_errors=True)
    con.execute("DELETE FROM stones WHERE cemetery_id=?", (cem["id"],))
    con.execute("DELETE FROM cemeteries WHERE id=?", (cem["id"],))
    con.execute("DELETE FROM tags WHERE id=?", (newtag["id"],))
    con.execute("DELETE FROM categories WHERE id=?", (newcat["id"],))
    con.commit()
    con.close()
    if lib_backup is not None:
        with open(lib_path, "w") as f:
            f.write(lib_backup)  # restore the real export
    else:
        try:
            os.remove(pub["path"])
        except OSError:
            pass
    shutil.rmtree(src, ignore_errors=True)
    if not had_cfg:
        os.remove(cfg_path)
    print("\nALL SMOKE TESTS PASSED ✓  (test data cleaned up)")


if __name__ == "__main__":
    main()
