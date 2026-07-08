"""SQLite database: schema, seed vocabularies, connection helpers."""
import os
import sqlite3

# Override with SG_DB env var if you want the database somewhere else.
DB_PATH = os.environ.get("SG_DB") or os.path.join(
    os.path.dirname(__file__), "..", "data", "library.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cemeteries (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT DEFAULT '',
    state TEXT DEFAULT '',
    country TEXT DEFAULT 'United States',
    lat REAL,
    lng REAL,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stones (
    id INTEGER PRIMARY KEY,
    cemetery_id INTEGER NOT NULL REFERENCES cemeteries(id) ON DELETE CASCADE,
    title TEXT DEFAULT '',            -- e.g. name on the stone
    year INTEGER,                     -- death year (principal date; drives charts)
    birth_year INTEGER,
    transcription TEXT DEFAULT '',    -- inscription as carved, line breaks kept
    has_audio INTEGER DEFAULT 0,      -- Welsh TTS audio built & uploaded
    date_text TEXT DEFAULT '',        -- full date as inscribed, free text
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY,
    stone_id INTEGER NOT NULL REFERENCES stones(id) ON DELETE CASCADE,
    name TEXT DEFAULT '',
    birth_year INTEGER,
    death_year INTEGER,
    sort INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY,
    stone_id INTEGER NOT NULL REFERENCES stones(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,           -- original filename, for reference
    orig_path TEXT DEFAULT '',        -- absolute path to the source file at import time
    width INTEGER,
    height INTEGER,
    taken TEXT DEFAULT '',            -- EXIF DateTimeOriginal if present
    is_primary INTEGER DEFAULT 0,
    r2_synced INTEGER DEFAULT 0,
    outline_path TEXT DEFAULT '',     -- normalized SVG path (viewBox 0 0 100 h)
    outline_h REAL,                   -- viewBox height matching outline_path
    outline_status TEXT DEFAULT '',   -- '', 'draft', 'approved', 'rejected'
    has_depth INTEGER DEFAULT 0,      -- depth.jpg built (raking-light viewer)
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    single_select INTEGER DEFAULT 0,  -- 1 = pick one (e.g. Shape), 0 = pick many
    sort INTEGER DEFAULT 100
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE(category_id, name)
);

CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY,
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    stone_id INTEGER NOT NULL,
    ch TEXT NOT NULL,                 -- the recognized character
    conf REAL,
    status TEXT DEFAULT 'ok'          -- 'ok' | 'bad' (curator-rejected)
);

CREATE TABLE IF NOT EXISTS photo_emb (
    photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
    vec TEXT NOT NULL                 -- JSON list, unit-norm CLIP embedding
);

CREATE TABLE IF NOT EXISTS stone_tags (
    stone_id INTEGER NOT NULL REFERENCES stones(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE(stone_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_stones_cem ON stones(cemetery_id);
CREATE INDEX IF NOT EXISTS idx_photos_stone ON photos(stone_id);
CREATE INDEX IF NOT EXISTS idx_stone_tags_stone ON stone_tags(stone_id);
CREATE INDEX IF NOT EXISTS idx_stone_tags_tag ON stone_tags(tag_id);
"""

SHAPES = [
    "Square Top", "Ogee Top", "Oval, Arc or Cambered Top", "Half Round Top",
    "Serpentine Top", "Peon Top", "Offset Peon Top", "Oval Top with Shoulders",
    "Oval Top with Scotia Shoulders", "Square Top with Rounded Shoulders",
    "Checked Top", "Raised Shoulder", "Square Top with Scotia Shoulders",
    "Peon Top with Checked Shoulders", "Square Top with Splayed Shoulders",
    "Square Top with Gothic Shoulders", "Oval Top with Checked Shoulders",
    "Square Top with Double Rounded Shoulders", "Half Ogee Top",
    "Ogee Top with Checked Shoulders",
]

ICONOGRAPHY = [
    "Urn", "Willow", "Tree (other)", "Wheat", "Bible / Book", "Praying Hands",
    "Winged Skull / Death's Head", "Cherub / Soul Effigy", "Winged Face",
    "Hourglass", "Rosette", "Columns / Pilasters", "Drapery", "Lamb", "Dove",
    "Flowers", "Clasped Hands", "Finger Pointing Up", "Anchor", "Crown",
    "Sun / Moon / Stars", "Coffin", "Crossed Bones", "Heart", "Vine / Foliage",
    "Geometric Border", "Masonic Symbol", "None / Plain",
]


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    con = connect()
    con.executescript(SCHEMA)
    # migrations for databases created before these columns existed
    cols = [r["name"] for r in con.execute("PRAGMA table_info(stones)")]
    if "birth_year" not in cols:
        con.execute("ALTER TABLE stones ADD COLUMN birth_year INTEGER")
        con.commit()
    if "transcription" not in cols:
        con.execute("ALTER TABLE stones ADD COLUMN transcription TEXT DEFAULT ''")
        con.commit()
    if "has_audio" not in cols:
        con.execute("ALTER TABLE stones ADD COLUMN has_audio INTEGER DEFAULT 0")
        con.commit()
    pcols = [r["name"] for r in con.execute("PRAGMA table_info(photos)")]
    if "outline_path" not in pcols:
        con.execute("ALTER TABLE photos ADD COLUMN outline_path TEXT DEFAULT ''")
        con.execute("ALTER TABLE photos ADD COLUMN outline_h REAL")
        con.execute("ALTER TABLE photos ADD COLUMN outline_status TEXT DEFAULT ''")
        con.commit()
    if "has_depth" not in pcols:
        con.execute("ALTER TABLE photos ADD COLUMN has_depth INTEGER DEFAULT 0")
        con.commit()
    if "letters_scanned" not in pcols:
        con.execute("ALTER TABLE photos ADD COLUMN letters_scanned INTEGER DEFAULT 0")
        con.commit()
    # backfill persons from legacy single-name stones (runs once)
    if (con.execute("SELECT COUNT(*) FROM persons").fetchone()[0] == 0 and
            con.execute("SELECT COUNT(*) FROM stones").fetchone()[0] > 0):
        con.execute(
            "INSERT INTO persons(stone_id, name, birth_year, death_year, sort) "
            "SELECT id, title, birth_year, year, 0 FROM stones WHERE title != ''")
        con.commit()
    # Seed vocabularies only if empty
    if con.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        con.execute(
            "INSERT INTO categories(name, single_select, sort) VALUES('Shape', 1, 1)")
        con.execute(
            "INSERT INTO categories(name, single_select, sort) VALUES('Iconography', 0, 2)")
        shape_id = con.execute(
            "SELECT id FROM categories WHERE name='Shape'").fetchone()[0]
        icon_id = con.execute(
            "SELECT id FROM categories WHERE name='Iconography'").fetchone()[0]
        con.executemany("INSERT INTO tags(category_id, name) VALUES(?, ?)",
                        [(shape_id, s) for s in SHAPES])
        con.executemany("INSERT INTO tags(category_id, name) VALUES(?, ?)",
                        [(icon_id, s) for s in ICONOGRAPHY])
        con.commit()
    con.close()


if __name__ == "__main__":
    init()
    print(f"Database ready at {os.path.abspath(DB_PATH)}")
