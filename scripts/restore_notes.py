"""One-time restore of two notes lost on 2026-07-06 (recovered from git
history, commit 4a615e1). Only writes where the field is still empty.
Run from repo root: python3 scripts/restore_notes.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "admin"))

import db  # noqa: E402

RECOVERED = {
    3: ("Englyn\n\nHe was born in a humble cottage,\nIn the land of California;"
        "\nHe grew up in Havre de Grace,\nAfter arriving there;\nAnd here he "
        "rests\nQuietly in the grave;\nUntil the morning he is restored\nTo "
        "live in the land of peace."),
    4: ("Englyn\n\nMy beloved spouse sleeps here;\nI shall seek him no more,"
        "\nAlas, he will not return,\nHis strength spent in a bed of earth."),
}


def main():
    con = db.connect()
    for sid, notes in RECOVERED.items():
        row = con.execute("SELECT title, notes FROM stones WHERE id=?",
                          (sid,)).fetchone()
        if not row:
            print(f"stone {sid}: not found, skipped")
        elif (row["notes"] or "").strip():
            print(f"stone {sid} ({row['title']}): notes not empty, left alone")
        else:
            con.execute("UPDATE stones SET notes=? WHERE id=?", (notes, sid))
            print(f"stone {sid} ({row['title']}): notes restored")
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
