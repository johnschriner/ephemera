import sqlite3

DB_PATH = "ephemera.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()

    db.execute("""
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        file_url TEXT,
        storage_key TEXT,
        caption TEXT,
        status TEXT,
        media_type TEXT,
        uploaded_at TEXT
    )
    """)
    db.commit()

    cols = [row["name"] for row in db.execute("PRAGMA table_info(images)").fetchall()]

    if "media_type" not in cols:
        db.execute("ALTER TABLE images ADD COLUMN media_type TEXT DEFAULT 'image'")
        db.commit()

    if "file_url" not in cols:
        db.execute("ALTER TABLE images ADD COLUMN file_url TEXT")
        db.commit()

    if "storage_key" not in cols:
        db.execute("ALTER TABLE images ADD COLUMN storage_key TEXT")
        db.commit()