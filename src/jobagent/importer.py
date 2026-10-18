"""Load applications from a CSV file or from a Markdown tracker with pipe tables."""

from __future__ import annotations

import csv
import re
import sqlite3
from datetime import date
from pathlib import Path

from . import db

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

SECTION_STATUS = (
    ("rejected", "rejected"),
    ("pending", "pending"),
    ("in progress", "pending"),
    ("skipped", "skipped"),
    ("built", "not_started"),
)


def _status_for(section: str, row_text: str) -> str:
    low = row_text.lower()
    if "submitted" in low and "not yet submitted" not in low:
        return "submitted"
    s = section.lower()
    for key, status in SECTION_STATUS:
        if key in s:
            return status
    return "not_started"


def parse_deadline(text: str, year: int) -> str | None:
    m = re.search(r"(?:by|deadline)[^0-9]{0,12}(\d{1,2})\s+([A-Za-z]{3})", text, re.IGNORECASE)
    if not m:
        return None
    mon = MONTHS.get(m.group(2).lower())
    if not mon:
        return None
    try:
        return date(year, mon, int(m.group(1))).isoformat()
    except ValueError:
        return None


def import_csv(path: Path, conn: sqlite3.Connection) -> int:
    n = 0
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            conn.execute(
                "INSERT INTO applications (company, role, status, deadline, applied_on, fit, notes, "
                "next_action, source_section, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    r["company"], r["role"], r.get("status") or "not_started",
                    r.get("deadline") or None, r.get("applied_on") or None,
                    int(r["fit"]) if r.get("fit") else None, r.get("notes", ""),
                    r.get("next_action", ""), "csv", db.now_iso(),
                ),
            )
            n += 1
    conn.commit()
    return n


def import_markdown(path: Path, conn: sqlite3.Connection, year: int = 2026) -> int:
    section = ""
    n = 0
    header: list[str] | None = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section, header = line[3:].strip(), None
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        role = re.sub(r"[`*]", "", cells[0])
        company, _, title = role.partition(" — ")
        text = " ".join(cells)
        fit_m = re.search(r"fit\s*(\d)\s*/\s*5", text, re.IGNORECASE)
        conn.execute(
            "INSERT INTO applications (company, role, status, deadline, fit, notes, source_section, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                company.strip(), (title or company).strip(), _status_for(section, text),
                parse_deadline(text, year), int(fit_m.group(1)) if fit_m else None,
                cells[-1][:500], section[:60], db.now_iso(),
            ),
        )
        n += 1
    conn.commit()
    return n
