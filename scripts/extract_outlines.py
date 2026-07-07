"""Extract gravestone silhouettes from photos using background segmentation.

One-time setup (the first run also downloads a ~170MB model):
    pip3 install rembg onnxruntime

Usage (from repo root):
    python3 scripts/extract_outlines.py            # all photos without an outline
    python3 scripts/extract_outlines.py --photo 3  # one photo
    python3 scripts/extract_outlines.py --force    # redo everything

For each photo it segments the foreground stone, traces the largest contour,
simplifies it, and stores a normalized SVG path in the database with status
'draft'. Review drafts in the admin's Outlines tab (approve/reject); only
APPROVED outlines are published to the site.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "admin"))

import db      # noqa: E402
import images  # noqa: E402

MIN_AREA_FRAC = 0.12   # reject masks smaller than this fraction of the image
SIMPLIFY = 0.002       # contour simplification (fraction of perimeter)


def extract(disp_path):
    """Returns (svg_path_d, viewbox_h) or (None, reason)."""
    import cv2
    import numpy as np
    from PIL import Image
    from rembg import remove

    img = Image.open(disp_path)
    mask = remove(img, only_mask=True, session=extract.session)
    m = np.array(mask)
    _, m = cv2.threshold(m, 127, 255, cv2.THRESH_BINARY)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, "no foreground found"
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < MIN_AREA_FRAC * m.shape[0] * m.shape[1]:
        return None, "foreground too small (stone not dominant in frame?)"
    c = cv2.approxPolyDP(c, SIMPLIFY * cv2.arcLength(c, True), True)
    pts = c.reshape(-1, 2).astype(float)
    x0, y0 = pts.min(axis=0)
    w, h = pts.max(axis=0) - (x0, y0)
    if w < 10 or h < 10:
        return None, "degenerate contour"
    scale = 100.0 / w
    pts = (pts - (x0, y0)) * scale
    d = "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"
    return d, round(h * scale, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", type=int, help="only this photo id")
    ap.add_argument("--force", action="store_true",
                    help="re-extract even if an outline exists")
    args = ap.parse_args()

    try:
        from rembg import new_session
    except ImportError:
        sys.exit("rembg is not installed — run: pip3 install rembg onnxruntime")
    print("Loading segmentation model (first run downloads ~170MB)…")
    extract.session = new_session("u2net")

    db.init()
    con = db.connect()
    where, params = [], []
    if args.photo:
        where.append("id=?")
        params.append(args.photo)
    if not args.force:
        where.append("(outline_status='' OR outline_status IS NULL)")
    rows = con.execute(
        f"SELECT id FROM photos {'WHERE ' + ' AND '.join(where) if where else ''} "
        "ORDER BY id", params).fetchall()
    print(f"{len(rows)} photo(s) to process")
    ok = failed = 0
    for r in rows:
        pid = r["id"]
        _thumb, disp, _enh = images.derivative_paths(pid)
        if not os.path.exists(disp):
            print(f"  photo #{pid}: no display derivative, skipped")
            failed += 1
            continue
        d, h = extract(disp)
        if d is None:
            print(f"  photo #{pid}: FAILED — {h}")
            con.execute("UPDATE photos SET outline_status='rejected', "
                        "outline_path='' WHERE id=?", (pid,))
            failed += 1
        else:
            con.execute(
                "UPDATE photos SET outline_path=?, outline_h=?, "
                "outline_status='draft' WHERE id=?", (d, h, pid))
            print(f"  photo #{pid}: outline drafted "
                  f"({len(d) // 8} points, aspect 100x{h})")
            ok += 1
        con.commit()
    con.close()
    print(f"\nDone: {ok} drafted, {failed} failed/skipped.")
    if ok:
        print("Review them in the admin app → Outlines tab, then Export + push.")


if __name__ == "__main__":
    main()
