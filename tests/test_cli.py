from jobagent import cli, tools


def test_init_and_import_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOBAGENT_DB", str(tmp_path / "c.db"))
    cli.main(["init"])
    cli.main(["import", "data/sample_applications.csv"])
    assert "imported 7 rows" in capsys.readouterr().out
    assert tools.list_applications()["count"] == 7


def test_pending_approve_and_rollback_flow(database, capsys):
    change = tools.propose_update(1, {"status": "submitted"}, "applied")
    cli.main(["pending"])
    assert "Northwind Analytics" in capsys.readouterr().out
    cli.main(["approve", str(change["change_id"])])
    assert "approved" in capsys.readouterr().out
    cli.main(["rollback", str(change["change_id"])])
    assert "rolled_back" in capsys.readouterr().out


def test_reject_via_cli(database, capsys):
    change = tools.propose_update(2, {"status": "skipped"})
    cli.main(["reject", str(change["change_id"])])
    assert "rejected" in capsys.readouterr().out
