# Admin Panel — User Guide

The admin app runs only on your Mac (`python3 admin/app.py` →
http://localhost:5050). Nothing you do here is public until you Export and
push (step ⑦ below). This guide covers every tab, the everyday workflows,
and the fix-it recipes.

**Golden rules**

- Your original photos (Google Drive) are never modified, moved, or uploaded.
  Everything the site shows is generated from them.
- After **pulling code updates**: restart the app (Ctrl+C, rerun) and refresh
  the browser. Python changes need the restart; page changes only the refresh.
- `data/library.db` is the catalog. It's committed to git, so every push is
  also a backup — commit even on days you don't publish.

---

## Tab by tab

### Cemeteries

Add or edit cemeteries. Click the map to drop the location pin, or use the
place search (Nominatim). A cemetery can't be deleted while it still has
gravestones. New cemeteries appear immediately in the Import and Gravestones
dropdowns.

### Import

1. Photos live in your Google Drive source folder (`photo_source_dir` in
   `config.json`), ideally **one subfolder per cemetery** — the folder name
   auto-selects the matching cemetery.
2. **Scan** lists only photos not yet imported (matched by file path —
   see "Moving files" in Troubleshooting).
3. Select photos (click, or **select folder**), then either:
   - **one gravestone per photo** — the common case, or
   - **as ONE gravestone** — for several shots of the same marker
     (front + detail + context).
4. Import generates three local derivatives per photo: thumbnail, display
   (2000px), and the CLAHE-enhanced version that pulls out worn carving.

### Gravestones

The editing pass. Filter by cemetery, **untagged only** (your tagging to-do
list), or search — the search box also matches inscriptions, so searching
`[DRAFT]` lists transcriptions awaiting review.

Click a gravestone to edit:

- **Title** — the display label ("William Lloyd", or "Children of Thomas and
  Elinor Davies" for multi-burial stones).
- **People on this stone** — one row per person (name, birth, death); **+ add
  person** for companion stones and child stones. The stone's chart/filter
  year is set automatically to the earliest death (the best carving-date
  proxy).
- **Inscription** — as carved, keeping line breaks. Drafts arrive prefixed
  `[DRAFT]`; correct against the photo, delete the prefix, Save.
- **Notes** — translations, observations. Public after export.
- **Tag chips** — Shape / Marker Type / Condition are pick-one; Iconography is
  pick-many. **+ add** creates a new tag in place. Click a highlighted chip to
  deselect it.
- **Photo tools** (hover a photo): **★** set primary — the photo used for the
  gallery thumbnail, the outline, and the constellation; **◐** open the
  enhanced version; **⇄** move the photo to another gravestone by its # (see
  the replace-a-photo recipe below); **✕** remove the photo from the library
  (the original file is untouched).

### Tags

Manage vocabularies. Add whole new categories anytime (e.g. Carver) — choose
single- or multi-select; they appear immediately in the editor and become
site filters after export. Rename a tag (✎) to fix a typo everywhere at once.
Delete (✕) works even on used tags after a warning. The number beside each
tag is how many gravestones use it.

### Analysis

Four background jobs, each with a progress line, each processing only what's
new — click them after every import batch. One-time installs are listed in
Setup below.

- **Trace new outlines** — segments each photo and traces the stone's
  silhouette as a draft. Review in the grid: **✓ approve** if the silhouette
  matches the stone, **✕ reject** if not (angled shots, cluttered frames).
  Only approved outlines publish; they power the site's Outlines view, and —
  recomputed automatically at Export — the Shape-space view and
  "similar shapes."
- **Build new relief maps** — AI depth map per photo, powering the site's
  💡 raking-light viewer. Needs a **Sync to R2** afterward.
- **Record new Welsh inscriptions** — detects which stones are inscribed in
  Welsh, reads each aloud (Piper's Welsh voice), and uploads the recording
  directly to R2. The site's 🔊 button appears after Export + push. A stone's
  audio is only generated once — see the recipe below if you correct an
  inscription afterward.
- **Embed new photos** — visual-similarity embedding per photo (CLIP). The
  constellation view regenerates at Export from primary photos.

### Publish

1. **Apply transcription drafts** — loads `data/transcription_drafts.json`
   (written by Claude in a Cowork session, or by the Friday-night scheduled
   task) into empty Inscription/Notes fields, prefixed `[DRAFT]`. It can
   never overwrite something you've written, and the file is archived after
   applying.
2. **Sync images to R2** — uploads new or rebuilt image files (thumb,
   display, enhanced, relief). Needed only when those changed; harmless to
   click anytime. Audio uploads itself during recording; outlines and shape
   data travel inside the JSON files, not R2.
3. **Export library.json** — writes everything public to `docs/data/`:
   the catalog, plus `morpho.json` (shape space) and `constellation.json`,
   both recomputed on the spot.
4. **Commit & push** (GitHub Desktop or `git add -A && git commit && git
   push`). The live site updates a minute or two later.

Minimal publish for tag/text-only edits: Export + push. Anything involving
images: Sync first.

---

## Recipes

### Replace or crop a gravestone's photo

Use when an extraction went wrong — e.g. two markers in one frame polluted
the outline, constellation position, or shape classification.

1. Crop the original in Preview/Photos to just the target stone. **Save the
   crop as a new file** into the cemetery's folder in Google Drive (never
   overwrite the original — the wide shot is worth keeping as context).
2. Import tab → Scan → import the crop ("one gravestone per photo"). It
   arrives as a temporary new gravestone.
3. Open the temp gravestone → **⇄** on its photo → enter the real
   gravestone's **#** → the photo moves. Delete the now-empty temp
   gravestone.
4. On the real gravestone: **★** the crop to make it primary (keep the wide
   shot as a secondary photo).
5. Analysis tab: **Trace new outlines** → approve the crop's outline, and
   **reject the old bad one** so only the good one is eligible.
   **Build new relief maps** and **Embed new photos** pick up the crop
   automatically.
6. Publish: Sync → Export → push. Shape space, similar-shapes, and the
   constellation all recompute from the new primary.

### Correct an inscription after audio was recorded

Audio is generated once per stone, so a corrected inscription needs a
re-record: fix the text, then run from the repo root

```bash
python3 -c "import sys; sys.path.insert(0,'admin'); import db; c=db.connect(); c.execute('UPDATE stones SET has_audio=0 WHERE id=STONE_ID'); c.commit()"
```

(replace `STONE_ID`), then Analysis → **Record new Welsh inscriptions**.

### Re-run one photo's outline

`python3 scripts/extract_outlines.py --photo PHOTO_ID --force`, then review
in the Analysis tab. (`--force` alone redoes every photo.)

### Rebuild missing thumbnails / derivatives

`python3 scripts/regen_media.py` — rebuilds anything missing from the
originals and flags it for re-sync. Safe anytime.

### Restore two lost notes / add seed vocabularies

One-time scripts, safe to re-run: `scripts/restore_notes.py`,
`scripts/add_marker_types.py`, `scripts/add_condition.py`.

---

## Setup summary (one-time installs)

| Feature | Install | First-run download |
|---|---|---|
| Core admin | `pip3 install -r admin/requirements.txt` | — |
| iPhone HEIC import | `pip3 install pillow-heif` | — |
| Outlines | `pip3 install rembg onnxruntime` | ~170MB model |
| Relief maps & constellation | `pip3 install torch transformers` (~2GB) | ~100MB + ~600MB models |
| Welsh audio | `pip3 install piper-tts` | ~65MB voice |

Restart the admin app after any install. R2 setup (bucket, public URL, API
token, **CORS policy allowing GET** — required by the raking-light viewer)
is in the README.

---

## Troubleshooting

- **A button 404s or a field won't save** → the running app predates the
  code: Ctrl+C, `python3 admin/app.py`, refresh the page.
- **Site shows stale styling/behavior** → hard refresh (Cmd+Shift+R).
- **Images missing on the live site** → run Sync; if it says nothing to
  upload but files are missing, reset the flags and re-sync:
  `python3 -c "import sys; sys.path.insert(0,'admin'); import db; c=db.connect(); c.execute('UPDATE photos SET r2_synced=0'); c.commit()"`
- **Raking light fails but the depth.jpg URL loads** → the bucket's CORS
  policy is missing, or a pre-CORS cached copy is stuck (the viewer already
  works around this; adding the policy fixes it for good).
- **Moving/renaming already-imported files in Google Drive** → the scanner
  matches by path, so moved files reappear as "new." Don't re-import ones
  you've already tagged (or delete the old entry first if you want to).
- **git commit blocked by `.lock` files** (Dropbox syncing `.git/`) → show
  hidden files in Finder (Cmd+Shift+.) and delete `HEAD.lock` /
  `index.lock`, or tell Dropbox not to sync the repo folder.
- **Piper/torch errors in a job's status line** → the message names the
  install to run; failed items stay queued and retry on the next click.

---

## The weekly rhythm

Photograph → drop into Drive (folder per cemetery) → Import → run the four
Analysis buttons → tag & review while they run → Friday 11pm the scheduled
task drafts transcriptions for anything still blank → weekend: Apply drafts,
review `[DRAFT]`s, approve outlines → Sync, Export, push. The site does the
rest.
