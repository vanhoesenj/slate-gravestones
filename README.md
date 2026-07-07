# Slate Gravestones — a visual library

An interactive library of slate grave markers: photos tagged by cemetery,
date, gravestone shape, and iconography, browsable on a MapLibre map with
filters and charts.

Architecture: **GitHub Pages** serves the public site from `docs/`;
**Cloudflare R2** hosts the images (free tier, zero egress); a **local admin
app** (Flask + SQLite) handles importing, tagging, and publishing. The public
site is fully static — it reads one JSON file and the R2 images.

```
admin/       local admin app (never deployed) — python admin/app.py
data/        library.db — SQLite source of truth (created on first run)
docs/        the public site, served by GitHub Pages
scripts/     smoke_test.py — end-to-end test of the admin pipeline
config.json  your R2 keys + photo folder (gitignored; copy config.example.json)
```

## One-time setup

### 1. Python

```bash
cd admin
pip3 install -r requirements.txt
python3 app.py          # → http://localhost:5050
```

(If you import iPhone HEIC files directly, also `pip3 install pillow-heif`.)

### 2. Cloudflare R2 (~10 minutes, free)

1. Sign up / log in at dash.cloudflare.com → **R2 Object Storage**
   (requires adding a payment card, but the 10 GB free tier means $0 for this
   project's scale).
2. **Create bucket** → name it `slate-gravestones` (location: Eastern North
   America).
3. In the bucket → **Settings → Public access → R2.dev subdomain → Allow**.
   Copy the URL it gives you (`https://pub-….r2.dev`).
4. Back on the R2 overview page → **Manage R2 API Tokens → Create API Token**:
   permission "Object Read & Write", scope it to this bucket. Copy the
   **Access Key ID** and **Secret Access Key** (shown once).
5. Your **Account ID** is on the R2 overview page sidebar.
6. `cp config.example.json config.json` and fill in all five values, plus
   `photo_source_dir` — the folder the ingest scans (your Google Drive
   gravestones folder; with Drive for desktop it's usually under
   `/Users/you/Library/CloudStorage/GoogleDrive-…/My Drive/…`).

Later, you can swap the r2.dev URL for a custom domain (bucket → Settings →
Custom Domains) and just update `public_base_url` + republish.

### 3. GitHub Pages

```bash
git remote add origin git@github.com:YOURUSER/slate-gravestones.git
git push -u origin main
```

On GitHub: repo → **Settings → Pages → Deploy from a branch →
`main` / `docs`**. The site appears at
`https://YOURUSER.github.io/slate-gravestones/` a minute or two after each
push. (Custom domain later: add it under Pages settings and site paths need
no changes — everything is relative.)

## The workflow

Start the admin whenever you're working: `python3 admin/app.py` →
http://localhost:5050. Nothing is public until step 7, so work in any order
and publish when ready.

1. **Add photos** to the Google Drive source folder — one subfolder per
   cemetery works best (the folder name auto-matches the cemetery on import).
2. **Cemeteries tab** (new cemeteries only) — add it, click the map or use
   the place search to set its location.
3. **Import tab** — Scan; already-imported photos are skipped automatically.
   Photos appear grouped by folder with a "select folder" button. Import
   "one gravestone per photo", or select several shots of the same marker and
   import "as ONE gravestone". Derivatives are generated locally (thumbnail,
   display, and a CLAHE-enhanced version that brings out worn carving);
   originals are never modified.
4. **Transcription drafts** (optional but worth it) — ask Claude in Cowork to
   "transcribe the new gravestones" (it reads the enhanced images and writes
   `data/transcription_drafts.json`), or let the scheduled task do it Friday
   night. Then Publish tab → **Apply transcription drafts**. Drafts land
   prefixed `[DRAFT]` and only ever fill empty fields; search "[DRAFT]" on
   the Gravestones tab to find entries awaiting your review.
5. **Outlines** (optional) — `python3 scripts/extract_outlines.py` traces
   silhouettes for any photos it hasn't tried yet, then review in the
   **Outlines tab**: approve ✓ or reject ✕. Only approved outlines publish
   (they power the site's Photos ⁄ Outlines gallery toggle).
6. **Gravestones tab** — the editing pass: title, people on the stone
   (name/birth/death rows — add as many as the marker carries), correct the
   inscription draft and remove its `[DRAFT]` prefix, notes/translation, and
   the tag chips (Shape, Iconography, Marker Type, Condition — "+ add"
   creates new tags on the spot; whole new categories via the Tags tab).
   The "untagged only" checkbox is your tagging to-do list.
7. **Publish tab** — ① **Sync images to R2** (needed only when there are new
   or rebuilt images; harmless otherwise) ② **Export library.json**
   ③ commit & push — GitHub Desktop, or:

   ```bash
   git add -A
   git commit -m "Update library"
   git push
   ```

   The live site updates a minute or two after the push. Tag-only or
   text-only edits still need ② and ③ — but not ①.

## Gravestone outlines (silhouette library)

One-time: `pip3 install rembg onnxruntime` (first run downloads a ~170MB
segmentation model). Then:

1. `python3 scripts/extract_outlines.py` — segments each photo, traces the
   stone's silhouette, saves it as a draft. Front-on shots work best; angled
   or context shots may fail or come out skewed (that's what review is for).
2. Admin → **Outlines** tab: each draft shows the photo beside its traced
   silhouette — approve ✓ or reject ✕. Only approved outlines publish.
3. Export + push. The public site's gallery gets a Photos ⁄ Outlines toggle;
   outlines inherit all filters, so "ogee tops by decade, as silhouettes" is
   two clicks.

Re-run the script anytime — it only processes photos it hasn't tried yet
(`--force` redoes everything, `--photo N` targets one).

## Notes & gotchas

- **Dropbox + git**: this repo lives in Dropbox. Dropbox syncing `.git/` can
  leave stale `HEAD.lock`/`index.lock` files that block commits (this bit the
  slate-map repo). Fix: in Finder press Cmd+Shift+. to show hidden files and
  delete the `.lock` files — or better, tell Dropbox to ignore `.git/`
  (right-click folder → "Don't sync to dropbox.com"), or move the repo out of
  Dropbox entirely (GitHub is already the backup).
- `data/library.db` **is committed** — it's small, and pushing it means GitHub
  also backs up your catalog. `admin/media/` and `config.json` are not.
- Deleting a photo/stone in the admin removes it from the library but never
  touches your original files.
- Test the pipeline anytime: `SG_DB=/tmp/t.db python3 scripts/smoke_test.py`
  (uses a throwaway DB; cleans up after itself).
- Free-tier ceilings, for reference: R2 10 GB storage ≈ ~10–15k photos at
  these derivative sizes; GitHub Pages soft limits (1 GB repo, 100 GB/mo
  bandwidth) are nowhere near being an issue since images don't live there.
