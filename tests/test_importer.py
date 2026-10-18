from jobagent import db, importer

MD = """# Tracker

## Pending — no final decision yet (1)

| Role | Folder | Applied | Notes |
|---|---|---|---|
| Acme — Data Analyst | `x` | 1 Oct | Fit 4/5. Apply by 30 Oct at acme.example. |

## Built, Not Yet Started (1)

| Role | Folder | Status | Notes |
|---|---|---|---|
| Beta — ML Engineer | `y` | **Submitted 18 Oct 2026** | Fit 3/5. |
| Gamma — Analyst | `z` | **Not yet submitted** | Apply by 25 Oct. |
"""


def test_markdown_import_extracts_status_fit_and_deadline(tmp_path):
    p = tmp_path / "t.md"
    p.write_text(MD)
    db_path = db.init_db(tmp_path / "x.db")
    conn = db.connect_rw(db_path)
    assert importer.import_markdown(p, conn, year=2026) == 3
    rows = {r["company"]: dict(r) for r in conn.execute("SELECT * FROM applications")}
    assert rows["Acme"]["status"] == "pending"
    assert rows["Acme"]["fit"] == 4
    assert rows["Acme"]["deadline"] == "2026-10-30"
    assert rows["Beta"]["status"] == "submitted"
    assert rows["Gamma"]["status"] == "not_started"
    assert rows["Gamma"]["deadline"] == "2026-10-25"
    conn.close()


def test_parse_deadline_ignores_missing_or_bad_dates():
    assert importer.parse_deadline("no date here", 2026) is None
    assert importer.parse_deadline("by 31 Feb", 2026) is None
