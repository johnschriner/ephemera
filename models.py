import sqlite3

DB_PATH = "ephemera.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            caption TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            media_type TEXT NOT NULL DEFAULT 'image',
            uploaded_at TEXT NOT NULL,
            approved_at TEXT
        )
        """
    )
    db.commit()

    cols = [row["name"] for row in db.execute("PRAGMA table_info(images)").fetchall()]
    if "media_type" not in cols:
        db.execute("ALTER TABLE images ADD COLUMN media_type TEXT DEFAULT 'image'")
        db.commit()
    if "approved_at" not in cols:
        db.execute("ALTER TABLE images ADD COLUMN approved_at TEXT")
        db.commit()
