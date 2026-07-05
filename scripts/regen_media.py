"""Rebuild missing thumbnail/display derivatives from the original photos.

Safe to run anytime:  python3 scripts/regen_media.py
Only photos whose derivative files are missing are regenerated (from their
orig_path recorded at import). Regenerated photos are marked r2_synced=0 so
the next "Sync images to R2" re-uploads them.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "admin"))

import db      # noqa: E402
import images  # noqa: E402


def main():
    db.init()
    con = db.connect()
    photos = con.execute(
        "SELECT id, orig_path, filename FROM photos ORDER BY id").fetchall()
    ok = missing_src = skipped = 0
    for p in photos:
        thumb, disp = images.derivative_paths(p["id"])
        if os.path.exists(thumb) and os.path.exists(disp):
            skipped += 1
            continue
        if not p["orig_path"] or not os.path.exists(p["orig_path"]):
            print(f"  photo #{p['id']} ({p['filename']}): original not found at "
                  f"{p['orig_path']!r} — re-import it or fix the path")
            missing_src += 1
            continue
        w, h = images.make_derivatives(p["orig_path"], p["id"])
        con.execute("UPDATE photos SET width=?, height=?, r2_synced=0 WHERE id=?",
                    (w, h, p["id"]))
        con.commit()
        print(f"  photo #{p['id']} ({p['filename']}): regenerated ({w}x{h})")
        ok += 1
    con.close()
    print(f"\nDone: {ok} regenerated, {skipped} already fine, "
          f"{missing_src} missing originals")
    if ok:
        print("Run 'Sync images to R2' in the admin Publish tab to re-upload.")


if __name__ == "__main__":
    main()
