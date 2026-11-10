from fastapi.testclient import TestClient

from convohub import config, db


def test_health_does_not_leak_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-secret")
    from convohub.main import app

    with TestClient(app) as client:
        res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["openrouter_key_set"] is True
    assert "sk-test-secret" not in res.text


def test_schema_creates_tables(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    with db.closing(db.connect(path)) as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"conversations", "messages", "chat_context"} <= names
