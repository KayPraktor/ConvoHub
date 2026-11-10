"""Things that matter for other people's installs: data location, the key entered in the UI, connect info."""

import importlib
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from convohub import config, keystore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "lib.db")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from convohub.main import app
    with TestClient(app) as c:
        yield c


def test_data_dir_override_and_default():
    env = {**os.environ, "CONVOHUB_DATA_DIR": "C:/somewhere/else"}
    code = "from convohub import config; print(config.DATA_DIR.as_posix(), config.DB_PATH.name)"
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         cwd=str(config.ROOT_DIR)).stdout.strip()
    assert out == "C:/somewhere/else convohub.db"
    env.pop("CONVOHUB_DATA_DIR")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         cwd=str(config.ROOT_DIR)).stdout.strip()
    assert out.startswith((config.ROOT_DIR / "data").as_posix())  # from source: <project>/data


def test_key_saved_encrypted_and_never_returned(client, tmp_path, monkeypatch):
    from convohub import openrouter

    async def ok(key):
        return True, ""
    monkeypatch.setattr(openrouter, "check_key", ok)

    assert client.get("/api/settings/key").json() == {"set": False, "source": None, "hint": None}
    key = "sk-or-v1-" + "0123456789abcdef" * 2  # fake, built at runtime
    res = client.put("/api/settings/key", json={"key": key}).json()
    assert res["set"] and res["source"] == "saved" and key not in str(res) and res["hint"].endswith("cdef")

    raw = (tmp_path / keystore.KEY_FILE_NAME).read_bytes()
    assert key.encode() not in raw  # encrypted on disk (DPAPI on Windows)
    assert config.openrouter_key() == key
    assert client.get("/api/health").json()["openrouter_key_set"] is True
    assert key not in client.get("/api/settings/key").text

    # Backups copy the database only, so the key never ends up in one.
    made = client.post("/api/backups").json()["created"]
    assert key.encode() not in open(made["path"], "rb").read()

    assert client.delete("/api/settings/key").json()["set"] is False
    assert config.openrouter_key() is None


def test_env_key_wins_over_saved(client, monkeypatch):
    keystore.save_key("sk-or-v1-saved-one-1234567890")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-from-env-abcdefghij")
    st = client.get("/api/settings/key").json()
    assert st["source"] == "env" and config.openrouter_key() == "sk-or-v1-from-env-abcdefghij"


def test_rejected_key_is_not_saved(client, monkeypatch):
    from convohub import openrouter

    async def bad(key):
        return False, "OpenRouter این کلید رو قبول نکرد."
    monkeypatch.setattr(openrouter, "check_key", bad)
    res = client.put("/api/settings/key", json={"key": "sk-or-v1-wrongwrongwrong"})
    assert res.status_code == 400 and client.get("/api/settings/key").json()["set"] is False
    assert client.put("/api/settings/key", json={"key": "not a key at all"}).status_code == 400


def test_integrations_use_this_machines_paths(client):
    info = client.get("/api/integrations").json()
    root = config.ROOT_DIR.as_posix()
    assert root in info["claude_code"] and info["claude_code"].startswith("claude mcp add convohub --scope user -- ")
    assert root in info["hermes"] and '"mcp"' not in info["opencode"]
    assert info["extension_dir"] == str(config.EXTENSION_DIR) and info["extension_dir_exists"]
    assert info["installed"] is False


def test_frozen_build_uses_appdata_and_bundled_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ConvoHub" / "ConvoHub.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "ConvoHub" / "_internal"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.delenv("CONVOHUB_DATA_DIR", raising=False)
    try:
        fresh = importlib.reload(config)
        assert fresh.DATA_DIR == tmp_path / "Local" / "ConvoHub"
        assert fresh.EXTENSION_DIR == tmp_path / "ConvoHub" / "extension"
        assert fresh.STATIC_DIR == tmp_path / "ConvoHub" / "_internal" / "convohub" / "static"
    finally:
        monkeypatch.undo()
        importlib.reload(config)
