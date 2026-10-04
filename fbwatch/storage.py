"""Αποθήκευση σε SQLite: πηγές, posts και ιστορικό λήψεων."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    url TEXT NOT NULL,
    label TEXT
);
CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    permalink TEXT NOT NULL,
    author TEXT,
    text TEXT,
    posted_at TEXT,
    posted_at_raw TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    screenshot_path TEXT,
    html_path TEXT,
    sha256 TEXT,
    archive_url TEXT,
    archive_requested_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source_id);
CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts(posted_at);
CREATE TABLE IF NOT EXISTS captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    screenshot_path TEXT,
    html_path TEXT,
    sha256 TEXT,
    FOREIGN KEY(post_id) REFERENCES posts(post_id)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    date_from TEXT,
    date_to TEXT,
    source_ids TEXT NOT NULL,
    folder TEXT,
    status TEXT,
    posts_count INTEGER DEFAULT 0,
    posts_new INTEGER DEFAULT 0,
    message TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source_id TEXT,
    status TEXT,
    posts_seen INTEGER DEFAULT 0,
    posts_new INTEGER DEFAULT 0,
    message TEXT
);
"""


@dataclass
class PostRecord:
    post_id: str
    source_id: str
    permalink: str
    author: Optional[str] = None
    text: Optional[str] = None
    posted_at: Optional[str] = None
    posted_at_raw: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    screenshot_path: Optional[str] = None
    html_path: Optional[str] = None
    sha256: Optional[str] = None
    archive_url: Optional[str] = None
    archive_requested_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class Storage:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- sources -------------------------------------------------------
    def upsert_source(self, source_id: str, kind: str, url: str, label: Optional[str]) -> None:
        self.conn.execute(
            "INSERT INTO sources(id, kind, url, label) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, url=excluded.url, label=excluded.label",
            (source_id, kind, url, label),
        )
        self.conn.commit()

    def sources(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM sources ORDER BY id"))

    # --- posts ---------------------------------------------------------
    def get_post(self, post_id: str) -> Optional[PostRecord]:
        row = self.conn.execute("SELECT * FROM posts WHERE post_id=?", (post_id,)).fetchone()
        return PostRecord(**dict(row)) if row else None

    def has_post(self, post_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM posts WHERE post_id=?", (post_id,)).fetchone() is not None

    def insert_post(self, rec: PostRecord) -> None:
        d = rec.to_dict()
        cols = ", ".join(d)
        marks = ", ".join("?" for _ in d)
        self.conn.execute(f"INSERT INTO posts({cols}) VALUES ({marks})", tuple(d.values()))
        if rec.screenshot_path or rec.html_path:
            self.conn.execute(
                "INSERT INTO captures(post_id, captured_at, screenshot_path, html_path, sha256) VALUES (?,?,?,?,?)",
                (rec.post_id, rec.first_seen, rec.screenshot_path, rec.html_path, rec.sha256),
            )
        self.conn.commit()

    def touch_post(self, post_id: str, seen_at: str) -> None:
        self.conn.execute("UPDATE posts SET last_seen=? WHERE post_id=?", (seen_at, post_id))
        self.conn.commit()

    def add_capture(
        self, post_id: str, captured_at: str, screenshot_path: Optional[str],
        html_path: Optional[str], sha256: Optional[str], make_current: bool = True,
    ) -> None:
        self.conn.execute(
            "INSERT INTO captures(post_id, captured_at, screenshot_path, html_path, sha256) VALUES (?,?,?,?,?)",
            (post_id, captured_at, screenshot_path, html_path, sha256),
        )
        if make_current:
            self.conn.execute(
                "UPDATE posts SET screenshot_path=?, html_path=?, sha256=?, last_seen=? WHERE post_id=?",
                (screenshot_path, html_path, sha256, captured_at, post_id),
            )
        self.conn.commit()

    def update_post_fields(self, post_id: str, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE posts SET {sets} WHERE post_id=?", (*fields.values(), post_id))
        self.conn.commit()

    def posts_without_archive(self, limit: int = 50, retry_after_hours: int = 24, now: Optional[str] = None) -> list[PostRecord]:
        """Posts χωρίς snapshot. Αποτυχημένες προσπάθειες ξαναδοκιμάζονται μόνο μετά από retry_after_hours."""
        from datetime import datetime as _dt, timedelta, timezone as _tz
        cutoff = (_dt.fromisoformat(now) if now else _dt.now(_tz.utc)) - timedelta(hours=retry_after_hours)
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE archive_url IS NULL AND (archive_requested_at IS NULL OR archive_requested_at < ?) "
            "ORDER BY first_seen DESC LIMIT ?", (cutoff.isoformat(timespec="seconds"), limit)
        )
        return [PostRecord(**dict(r)) for r in rows]

    def query_posts(
        self,
        source_ids: Optional[Iterable[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        date_field: str = "posted_at",
        include_undated: bool = True,
    ) -> list[PostRecord]:
        if date_field not in ("posted_at", "first_seen"):
            raise ValueError("date_field: posted_at | first_seen")
        where, params = [], []
        if source_ids:
            ids = list(source_ids)
            where.append(f"source_id IN ({','.join('?' for _ in ids)})")
            params.extend(ids)
        range_clauses = []
        if date_from:
            range_clauses.append(f"{date_field} >= ?")
            params.append(date_from.isoformat(timespec="seconds"))
        if date_to:
            range_clauses.append(f"{date_field} <= ?")
            params.append(date_to.isoformat(timespec="seconds"))
        if range_clauses:
            rng = " AND ".join(range_clauses)
            if include_undated and date_field == "posted_at":
                where.append(f"(({rng}) OR posted_at IS NULL)")
            else:
                where.append(f"({rng})")
        sql = "SELECT * FROM posts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(posted_at, first_seen) DESC"
        return [PostRecord(**dict(r)) for r in self.conn.execute(sql, params)]

    def count_posts(self, source_id: Optional[str] = None) -> int:
        if source_id:
            return self.conn.execute("SELECT COUNT(*) FROM posts WHERE source_id=?", (source_id,)).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    # --- runs ----------------------------------------------------------
    def start_run(self, source_id: Optional[str], started_at: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(started_at, source_id, status) VALUES (?,?,?)", (started_at, source_id, "running")
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, finished_at: str, status: str, posts_seen: int, posts_new: int, message: str = "") -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, posts_seen=?, posts_new=?, message=? WHERE id=?",
            (finished_at, status, posts_seen, posts_new, message, run_id),
        )
        self.conn.commit()

    def recent_runs(self, limit: int = 20) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)))

    # --- jobs (έλεγχοι) ------------------------------------------------
    def insert_job(self, name: str, created_at: str, date_from: Optional[str], date_to: Optional[str],
                   source_ids: list[str], folder: Optional[str]) -> int:
        cur = self.conn.execute(
            "INSERT INTO jobs(name, created_at, date_from, date_to, source_ids, folder, status) VALUES (?,?,?,?,?,?,?)",
            (name, created_at, date_from, date_to, ",".join(source_ids), folder, "running"),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_job(self, job_id: int, status: str, posts_count: int, posts_new: int, message: str = "") -> None:
        self.conn.execute(
            "UPDATE jobs SET status=?, posts_count=?, posts_new=?, message=? WHERE id=?",
            (status, posts_count, posts_new, message, job_id),
        )
        self.conn.commit()

    def jobs(self, limit: int = 200) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)))

    def delete_job(self, job_id: int) -> None:
        self.conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        self.conn.commit()
