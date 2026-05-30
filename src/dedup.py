"""
SQLite-backed deduplication.
Tracks all PMIDs we've already processed per-user so we never summarize the same paper twice.
"""

import sqlite3
from pathlib import Path


def init_db(db_path: str) -> None:
    """Create tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            pmid TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            first_seen TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def filter_new(articles: list[dict], source: str, db_path: str = None) -> list[dict]:
    """
    Return only articles whose PMIDs we haven't seen before.
    Inserts newly-seen PMIDs into the per-user database.

    Args:
        articles: list of article dicts with 'pmid' key
        source: source label for tracking
        db_path: path to user-specific SQLite database; defaults to root history.db
    """
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "history.db")

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    new_articles = []
    for art in articles:
        pmid = art["pmid"]
        cur.execute("SELECT 1 FROM seen WHERE pmid = ?", (pmid,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO seen (pmid, source, first_seen) VALUES (?, ?, datetime('now'))",
                (pmid, source),
            )
            new_articles.append(art)

    conn.commit()
    conn.close()
    return new_articles


def stats(db_path: str = None) -> dict:
    """Return simple stats: total tracked, by source."""
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "history.db")

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM seen")
    total = cur.fetchone()[0]
    cur.execute("SELECT source, COUNT(*) FROM seen GROUP BY source")
    by_source = dict(cur.fetchall())
    conn.close()
    return {"total": total, "by_source": by_source}
