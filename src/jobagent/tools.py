"""Tool implementations.

Design rules:
* Reads use a read-only connection and parameterised templates. The model never writes SQL.
* The agent can only *propose* edits. Applying or rolling back needs a human (CLI).
* Every call is written to the audit log.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any

from . import db
from .db import EDITABLE_FIELDS, STATUSES

MAX_ROWS = 50


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def _log(tool: str, args: dict, summary: str, actor: str = "agent") -> None:
    conn = db.connect_rw()
    try:
        db.audit(conn, actor, tool, args, summary)
    finally:
        conn.close()


def get_schema() -> dict:
    """Return table columns, allowed statuses and editable fields."""
    conn = db.connect_ro()
    try:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(applications)")]
    finally:
        conn.close()
    out = {
        "table": "applications",
        "columns": cols,
        "statuses": list(STATUSES),
        "editable_fields": list(EDITABLE_FIELDS),
    }
    _log("get_schema", {}, "ok")
    return out


def list_applications(status: str | None = None, limit: int = 20) -> dict:
    """List applications, optionally filtered by status."""
    limit = max(1, min(int(limit), MAX_ROWS))
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {list(STATUSES)}")
    conn = db.connect_ro()
    try:
        if status:
            cur = conn.execute(
                "SELECT id, company, role, status, deadline, fit, next_action, notes "
                "FROM applications WHERE status = ? ORDER BY COALESCE(deadline,'9999') LIMIT ?",
                (status, limit),
            )
        else:
            cur = conn.execute(
                "SELECT id, company, role, status, deadline, fit, next_action, notes "
                "FROM applications ORDER BY COALESCE(deadline,'9999') LIMIT ?",
                (limit,),
            )
        rows = _rows(cur)
    finally:
        conn.close()
    _log("list_applications", {"status": status, "limit": limit}, f"{len(rows)} rows")
    return {"count": len(rows), "applications": rows}


def upcoming_deadlines(days: int = 7, today: str | None = None) -> dict:
    """Applications not yet submitted whose deadline falls within the next `days` days."""
    days = max(1, min(int(days), 365))
    start = date.fromisoformat(today) if today else date.today()
    end = start + timedelta(days=days)
    conn = db.connect_ro()
    try:
        cur = conn.execute(
            "SELECT id, company, role, status, deadline, fit, next_action FROM applications "
            "WHERE deadline IS NOT NULL AND deadline BETWEEN ? AND ? "
            "AND status IN ('not_started','pending') ORDER BY deadline LIMIT ?",
            (start.isoformat(), end.isoformat(), MAX_ROWS),
        )
        rows = _rows(cur)
    finally:
        conn.close()
    _log("upcoming_deadlines", {"days": days, "today": today}, f"{len(rows)} rows")
    return {"from": start.isoformat(), "to": end.isoformat(), "count": len(rows), "applications": rows}


def search_applications(query: str, limit: int = 10) -> dict:
    """Case-insensitive search over company, role and notes."""
    query = (query or "").strip()
    if not query or len(query) > 100:
        raise ValueError("query must be 1-100 characters")
    limit = max(1, min(int(limit), MAX_ROWS))
    like = f"%{query}%"
    conn = db.connect_ro()
    try:
        cur = conn.execute(
            "SELECT id, company, role, status, deadline, fit, notes FROM applications "
            "WHERE company LIKE ? OR role LIKE ? OR notes LIKE ? LIMIT ?",
            (like, like, like, limit),
        )
        rows = _rows(cur)
    finally:
        conn.close()
    _log("search_applications", {"query": query}, f"{len(rows)} rows")
    return {"count": len(rows), "applications": rows}


def _validate_changes(changes: dict) -> dict:
    if not changes:
        raise ValueError("changes must not be empty")
    bad = [k for k in changes if k not in EDITABLE_FIELDS]
    if bad:
        raise ValueError(f"fields not editable: {bad}; allowed: {list(EDITABLE_FIELDS)}")
    clean = dict(changes)
    if "status" in clean and clean["status"] not in STATUSES:
        raise ValueError(f"status must be one of {list(STATUSES)}")
    if "deadline" in clean and clean["deadline"] not in (None, ""):
        date.fromisoformat(str(clean["deadline"]))  # raises ValueError if not ISO
    if "fit" in clean and clean["fit"] is not None:
        if int(clean["fit"]) not in range(1, 6):
            raise ValueError("fit must be 1-5")
        clean["fit"] = int(clean["fit"])
    for k in ("notes", "next_action"):
        if k in clean and clean[k] is not None and len(str(clean[k])) > 500:
            raise ValueError(f"{k} too long (max 500 characters)")
    return clean


def propose_update(application_id: int, changes: dict, reason: str = "") -> dict:
    """Create a pending change. Nothing in `applications` is modified until a human approves."""
    clean = _validate_changes(changes)
    conn = db.connect_rw()
    try:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (int(application_id),)).fetchone()
        if row is None:
            raise ValueError(f"application {application_id} not found")
        previous = {k: row[k] for k in clean}
        cur = conn.execute(
            "INSERT INTO pending_changes (application_id, changes, previous_values, reason, status, created_at) "
            "VALUES (?,?,?,?, 'pending', ?)",
            (row["id"], json.dumps(clean), json.dumps(previous), reason[:300], db.now_iso()),
        )
        conn.commit()
        change_id = cur.lastrowid
        db.audit(conn, "agent", "propose_update", {"id": application_id, "changes": clean}, f"change {change_id}")
    finally:
        conn.close()
    return {
        "change_id": change_id,
        "status": "pending_human_approval",
        "message": "Proposal saved. A human must run `jobagent approve <id>` to apply it.",
        "previous_values": previous,
    }


def draft_followup(application_id: int) -> dict:
    """Return a follow-up email draft for the user to review. Never sends anything."""
    conn = db.connect_ro()
    try:
        row = conn.execute(
            "SELECT company, role, status, applied_on FROM applications WHERE id = ?",
            (int(application_id),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"application {application_id} not found")
    when = f" on {row['applied_on']}" if row["applied_on"] else ""
    body = (
        f"Subject: Follow-up on my application for {row['role']}\n\n"
        f"Dear {row['company']} hiring team,\n\n"
        f"I applied for the {row['role']} position{when} and remain very interested. "
        "I would be glad to answer any questions or share more detail about my work.\n\n"
        "Kind regards"
    )
    _log("draft_followup", {"id": application_id}, "draft created (not sent)")
    return {"application_id": int(application_id), "sent": False, "draft": body}


# ---- Human-only operations (exposed through the CLI, never through MCP) ----

def list_pending() -> list[dict]:
    conn = db.connect_rw()
    try:
        rows = _rows(
            conn.execute(
                "SELECT pc.id, pc.application_id, a.company, a.role, pc.changes, pc.previous_values, pc.reason "
                "FROM pending_changes pc JOIN applications a ON a.id = pc.application_id "
                "WHERE pc.status = 'pending' ORDER BY pc.id"
            )
        )
    finally:
        conn.close()
    return rows


def approve_change(change_id: int) -> dict:
    conn = db.connect_rw()
    try:
        pc = conn.execute("SELECT * FROM pending_changes WHERE id = ?", (change_id,)).fetchone()
        if pc is None or pc["status"] != "pending":
            raise ValueError("change not found or not pending")
        changes = _validate_changes(json.loads(pc["changes"]))
        sets = ", ".join(f"{k} = ?" for k in changes)
        conn.execute(
            f"UPDATE applications SET {sets}, updated_at = ? WHERE id = ?",  # keys are allow-listed
            (*changes.values(), db.now_iso(), pc["application_id"]),
        )
        conn.execute(
            "UPDATE pending_changes SET status='approved', decided_at=? WHERE id=?",
            (db.now_iso(), change_id),
        )
        conn.commit()
        db.audit(conn, "human", "approve_change", {"change_id": change_id}, "applied")
    finally:
        conn.close()
    return {"change_id": change_id, "status": "approved", "applied": changes}


def reject_change(change_id: int) -> dict:
    conn = db.connect_rw()
    try:
        cur = conn.execute(
            "UPDATE pending_changes SET status='rejected', decided_at=? WHERE id=? AND status='pending'",
            (db.now_iso(), change_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("change not found or not pending")
        db.audit(conn, "human", "reject_change", {"change_id": change_id}, "rejected")
    finally:
        conn.close()
    return {"change_id": change_id, "status": "rejected"}


def rollback_change(change_id: int) -> dict:
    conn = db.connect_rw()
    try:
        pc = conn.execute("SELECT * FROM pending_changes WHERE id = ?", (change_id,)).fetchone()
        if pc is None or pc["status"] != "approved":
            raise ValueError("only approved changes can be rolled back")
        previous = _validate_changes(json.loads(pc["previous_values"]))
        sets = ", ".join(f"{k} = ?" for k in previous)
        conn.execute(
            f"UPDATE applications SET {sets}, updated_at = ? WHERE id = ?",
            (*previous.values(), db.now_iso(), pc["application_id"]),
        )
        conn.execute(
            "UPDATE pending_changes SET status='rolled_back', decided_at=? WHERE id=?",
            (db.now_iso(), change_id),
        )
        conn.commit()
        db.audit(conn, "human", "rollback_change", {"change_id": change_id}, "restored")
    finally:
        conn.close()
    return {"change_id": change_id, "status": "rolled_back", "restored": previous}
