import socket
import struct
import sys

import pytest
from fastapi.testclient import TestClient

from convohub import __main__ as launcher
from convohub import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "l.db")
    from convohub.main import app
    with TestClient(app) as c:
        yield c, app


def test_shutdown_stops_the_server(client):
    c, app = client

    class FakeServer:
        should_exit = False

    app.state.server = FakeServer()
    try:
        assert c.post("/api/shutdown").json() == {"ok": True}
        assert app.state.server.should_exit
        # Another website can't switch it off.
        assert c.post("/api/shutdown", headers={"Origin": "https://evil.example"}).status_code == 403
    finally:
        del app.state.server


def test_shutdown_without_launcher(client):
    c, _ = client
    assert c.post("/api/shutdown").status_code == 503


def test_running_detects_a_free_port_and_a_foreign_one(monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(launcher, "URL", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(config, "PORT", port)
    assert launcher.running() == ""
    with socket.socket() as busy:  # something that is not ConvoHub
        busy.bind(("127.0.0.1", port))
        busy.listen()
        assert launcher.running() == "other"


def test_icon_is_a_valid_ico_with_large_image():
    data = (config.STATIC_DIR / "icon.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1) and count >= 4
    sizes = [data[6 + 16 * i] or 256 for i in range(count)]
    assert 256 in sizes and 32 in sizes and 16 in sizes


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcuts")
def test_shortcuts_are_created(tmp_path):
    from convohub import shortcut
    made = shortcut.create(desktop=tmp_path)
    assert [p.name for p in made] == ["ConvoHub.lnk", "ConvoHub - خاموش.lnk"]
    assert all(p.exists() and p.stat().st_size > 0 for p in made)


def test_persian_messages_do_not_crash_an_old_console(tmp_path):
    """Regression: printing the Persian start-up text crashed when the console used cp1252."""
    import subprocess
    env = {**__import__("os").environ, "PYTHONIOENCODING": "cp1252", "CONVOHUB_PORT": "1"}
    out = subprocess.run([sys.executable, "-m", "convohub", "--stop"], capture_output=True, env=env,
                         cwd=str(config.ROOT_DIR), timeout=60)
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")


def test_port_problem_explains_a_blocked_port(monkeypatch):
    import socket

    from convohub import __main__ as launcher
    with socket.socket() as s:  # occupy a free port, then point ConvoHub at it
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        monkeypatch.setattr(launcher.config, "PORT", port)
        msg = launcher.port_problem()
    assert str(port) in msg and "CONVOHUB_PORT" in msg
    monkeypatch.setattr(launcher.config, "PORT", 0)  # any free port
    assert launcher.port_problem() == ""


def test_default_port_is_outside_windows_dynamic_ranges():
    from convohub import config
    if "CONVOHUB_PORT" not in __import__("os").environ:
        assert 15000 < config.PORT < 49152
