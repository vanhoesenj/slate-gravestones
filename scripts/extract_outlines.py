"""CLI for gravestone silhouette extraction (the admin app's Outlines tab has
a "Trace new outlines" button that does the same thing).

Setup: pip3 install rembg onnxruntime   (first run downloads a ~170MB model)

Usage (from repo root):
    python3 scripts/extract_outlines.py            # all photos not yet tried
    python3 scripts/extract_outlines.py --photo 3  # one photo
    python3 scripts/extract_outlines.py --force    # redo everything

Outlines are saved as drafts; review in the admin Outlines tab. Only APPROVED
outlines are published.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "admin"))

import db            # noqa: E402
import images        # noqa: E402
import outline_core  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", type=int, help="only this photo id")
    ap.add_argument("--force", action="store_true",
                    help="re-extract even if an outline exists")
    args = ap.parse_args()

    try:
        import rembg  # noqa: F401
    except ImportError:
        sys.exit("rembg is not installed — run: pip3 install rembg onnxruntime")
    print("Loading segmentation model (first run downloads ~170MB)…")
    outline_core.get_session()

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
        d, h = outline_core.extract(disp)
        if d is None:
            print(f"  photo #{pid}: FAILED — {h}")
            con.execute("UPDATE photos SET outline_status='rejected', "
                        "outline_path='' WHERE id=?", (pid,))
            failed += 1
        else:
            con.execute(
                "UPDATE photos SET outline_path=?, outline_h=?, "
                "outline_status='draft' WHERE id=?", (d, h, pid))
            print(f"  photo #{pid}: outline drafted (aspect 100x{h})")
            ok += 1
        con.commit()
    con.close()
    print(f"\nDone: {ok} drafted, {failed} failed/skipped.")


if __name__ == "__main__":
    main()
