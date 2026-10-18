import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jobagent import db, importer


@pytest.fixture()
def database(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("JOBAGENT_DB", str(path))
    db.init_db(path)
    conn = db.connect_rw(path)
    importer.import_csv(ROOT / "data" / "sample_applications.csv", conn)
    conn.close()
    return path
