import sqlite3

import pytest

from jobagent import db, tools


def test_schema_lists_statuses_and_editable_fields(database):
    s = tools.get_schema()
    assert "interview" in s["statuses"]
    assert "status" in s["editable_fields"]
    assert "company" in s["columns"]


def test_list_all_and_filter(database):
    assert tools.list_applications()["count"] == 7
    rows = tools.list_applications(status="interview")["applications"]
    assert [r["company"] for r in rows] == ["Kestrel Bio"]


def test_list_rejects_unknown_status(database):
    with pytest.raises(ValueError):
        tools.list_applications(status="hired; DROP TABLE applications")


def test_limit_is_capped(database):
    assert tools.list_applications(limit=10_000)["count"] <= tools.MAX_ROWS


def test_upcoming_deadlines_window_and_status_filter(database):
    out = tools.upcoming_deadlines(days=7, today="2026-10-18")
    companies = [r["company"] for r in out["applications"]]
    assert companies == ["Northwind Analytics", "Aurora Labs", "Fjord Health"]
    assert all(r["status"] in ("not_started", "pending") for r in out["applications"])
    assert out["to"] == "2026-10-25"


def test_search_is_parameterised(database):
    assert tools.search_applications("Kestrel")["count"] == 1
    # classic injection string is treated as plain text, not SQL
    assert tools.search_applications("'; DROP TABLE applications; --")["count"] == 0
    assert tools.list_applications()["count"] == 7


def test_search_rejects_empty_and_long_queries(database):
    with pytest.raises(ValueError):
        tools.search_applications("  ")
    with pytest.raises(ValueError):
        tools.search_applications("x" * 101)


def test_read_connection_cannot_write(database):
    conn = db.connect_ro()
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM applications")
    conn.close()


def test_propose_does_not_change_applications(database):
    before = tools.list_applications(status="not_started")["count"]
    out = tools.propose_update(1, {"status": "submitted"}, "applied today")
    assert out["status"] == "pending_human_approval"
    assert out["previous_values"] == {"status": "not_started"}
    assert tools.list_applications(status="not_started")["count"] == before
    assert len(tools.list_pending()) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"company": "Evil Corp"},
        {"id": 99},
        {"status": "hired"},
        {"deadline": "next week"},
        {"fit": 9},
        {"notes": "x" * 501},
    ],
)
def test_invalid_proposals_are_rejected(database, changes):
    with pytest.raises(ValueError):
        tools.propose_update(1, changes)
    assert tools.list_pending() == []


def test_propose_unknown_application(database):
    with pytest.raises(ValueError):
        tools.propose_update(999, {"status": "submitted"})


def test_approve_then_rollback_restores_previous_values(database):
    change = tools.propose_update(1, {"status": "submitted", "next_action": "wait"})
    tools.approve_change(change["change_id"])
    row = tools.search_applications("Northwind")["applications"][0]
    assert row["status"] == "submitted"
    tools.rollback_change(change["change_id"])
    row = tools.search_applications("Northwind")["applications"][0]
    assert row["status"] == "not_started"


def test_cannot_approve_twice_or_rollback_unapproved(database):
    change = tools.propose_update(1, {"status": "submitted"})
    with pytest.raises(ValueError):
        tools.rollback_change(change["change_id"])
    tools.approve_change(change["change_id"])
    with pytest.raises(ValueError):
        tools.approve_change(change["change_id"])


def test_reject_leaves_data_unchanged(database):
    change = tools.propose_update(1, {"status": "skipped"})
    tools.reject_change(change["change_id"])
    assert tools.search_applications("Northwind")["applications"][0]["status"] == "not_started"


def test_draft_followup_never_sends(database):
    out = tools.draft_followup(3)
    assert out["sent"] is False
    assert "Lumen Robotics" in out["draft"]


def test_audit_log_records_agent_and_human_actions(database):
    tools.list_applications()
    change = tools.propose_update(1, {"status": "submitted"})
    tools.approve_change(change["change_id"])
    conn = db.connect_ro()
    rows = conn.execute("SELECT actor, tool FROM audit_log").fetchall()
    conn.close()
    pairs = {(r["actor"], r["tool"]) for r in rows}
    assert ("agent", "list_applications") in pairs
    assert ("agent", "propose_update") in pairs
    assert ("human", "approve_change") in pairs
