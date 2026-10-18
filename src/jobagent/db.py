"""SQLite layer: schema, read-only and read-write connections, audit logging."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

STATUSES = (
    "not_started",
    "pending",
    "submitted",
    "interview",
    "offer",
    "rejected",
    "skipped",
)

# Fields the agent may propose to change. Everything else is read-only to it.
EDITABLE_FIELDS = ("status", "deadline", "notes", "next_action", "fit")

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started',
    deadline TEXT,
    applied_on TEXT,
    fit INTEGER,
    notes TEXT DEFAULT '',
    next_action TEXT DEFAULT '',
    source_section TEXT DEFAULT '',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS pending_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications(id),
    changes TEXT NOT NULL,
    previous_values TEXT,
    reason TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool TEXT NOT NULL,
    args TEXT,
    result_summary TEXT
);
"""


def db_path() -> Path:
    return Path(os.environ.get("JOBAGENT_DB", "data/jobs.db"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(path: Path | None = None) -> Path:
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
    return path


def connect_rw(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path or db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def connect_ro(path: Path | None = None) -> sqlite3.Connection:
    """Read-only connection: any write attempt raises sqlite3.OperationalError."""
    p = Path(path or db_path()).resolve()
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def audit(conn: sqlite3.Connection, actor: str, tool: str, args: dict, summary: str) -> None:
    conn.execute(
        "INSERT INTO audit_log (ts, actor, tool, args, result_summary) VALUES (?,?,?,?,?)",
        (now_iso(), actor, tool, json.dumps(args, default=str), summary[:500]),
    )
    conn.commit()
