import sqlite3

import pytest
from fastapi.testclient import TestClient

from convohub import backup, config, db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "lib.db")
    from convohub.main import app
    with TestClient(app) as c:
        yield c


def test_startup_takes_an_automatic_backup(client, tmp_path):
    info = client.get("/api/backups").json()
    assert info["default"] and info["folder"] == str(tmp_path / "backups")
    assert [i["auto"] for i in info["items"]] == [True]


def test_manual_backup_is_a_working_copy(client, tmp_path):
    client.post("/api/import/paste", json={"text": "Conversation with Gemini\nسلام، یه مکالمه برای بکاپ"})
    made = client.post("/api/backups").json()["created"]
    assert made["conversations"] == 1
    copy = sqlite3.connect(made["path"])
    assert "بکاپ" in copy.execute("SELECT raw_text FROM conversations").fetchone()[0]
    copy.close()

    res = client.get(f"/api/backups/{made['name']}")
    assert res.status_code == 200 and res.content[:15] == b"SQLite format 3"


def test_custom_folder_and_bad_names(client, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert client.put("/api/backups/folder", json={"folder": str(other)}).json()["folder"] == str(other.resolve())
    made = client.post("/api/backups").json()["created"]
    assert made["path"].startswith(str(other.resolve()))
    assert client.put("/api/backups/folder", json={"folder": str(tmp_path / "missing")}).status_code == 400
    assert client.get("/api/backups/..%2Flib.db").status_code == 404
    assert client.get("/api/backups/lib.db").status_code == 404
    assert client.put("/api/backups/folder", json={"folder": ""}).json()["default"]


def test_prune_keeps_manual_backups(tmp_path):
    for i in range(1, 6):
        (tmp_path / f"convohub-2026010{i}-120000-auto.db").write_bytes(b"x")
    (tmp_path / "convohub-20250101-120000.db").write_bytes(b"x")  # manual, oldest
    (tmp_path / "convohub-20260199-120000.db").write_bytes(b"x")  # bad date: ignored, not a crash
    backup.prune(tmp_path, keep=2)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["convohub-20250101-120000.db", "convohub-20260104-120000-auto.db",
                     "convohub-20260105-120000-auto.db", "convohub-20260199-120000.db"]


def test_auto_backup_not_repeated_within_a_day(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "x.db")
    db.init_db()
    with db.session() as conn:
        assert backup.auto_if_due(conn) is not None
        assert backup.auto_if_due(conn) is None
