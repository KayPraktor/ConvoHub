"""Remote connector: the read-only MCP app behind a secret path (the Cloudflare tunnel itself isn't run here)."""

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from convohub import config, db, library, memory, remote


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "remote.db")
    db.init_db()
    with db.session() as conn:
        library.create_conversation(conn, title="Pricing plan", source="gemini", import_method="paste",
                                    raw_text="User:\nprice?\n\nAssistant:\nfreemium")
        memory.add(conn, "Approved note.", "active")
        memory.add(conn, "Not approved.", "suggested")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def served(data):
    """The remote app on a real local port, as the tunnel would see it."""
    calls = []
    secret = "s3cret-token-for-tests"
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(remote.build_app(secret, lambda n, a: calls.append(n)),
                                          host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", secret, calls
    server.should_exit = True
    t.join(5)


def test_only_read_tools_and_only_with_the_secret(served):
    from fastmcp import Client
    base, secret, calls = served

    async def go():
        async with Client(f"{base}/{secret}/mcp") as c:
            names = sorted(t.name for t in await c.list_tools())
            mem = (await c.call_tool("read_memory", {})).structured_content
            found = (await c.call_tool("search_conversations", {"query": "freemium"})).structured_content
            return names, mem, found
    names, mem, found = asyncio.run(go())
    assert names == ["list_conversations", "read_conversation", "read_memory", "search_conversations"]
    assert mem["notes"] == ["Approved note."]
    assert found["result"][0]["title"] == "Pricing plan"
    assert calls == ["read_memory", "search_conversations"]

    # Without the secret (or with a wrong one) there is nothing there.
    for path in ("/mcp", "/wrong-secret/mcp", f"/{secret}x/mcp", "/", "/.well-known/oauth-protected-resource"):
        assert httpx.post(base + path, json={}).status_code == 404, path


def test_secret_path_wrapper_strips_prefix():
    seen = {}

    async def inner(scope, receive, send):
        if scope["type"] == "lifespan":
            msg = await receive()
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})
            return
        seen["path"] = scope["path"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    with TestClient(remote._SecretPath(inner, "abc")) as c:
        assert c.get("/abc/mcp").status_code == 200 and seen["path"] == "/mcp"
        assert c.get("/abd/mcp").status_code == 404


def test_api_status_and_missing_cloudflared(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "r2.db")
    monkeypatch.setattr(remote, "find_cloudflared", lambda: None)
    from convohub.main import app
    with TestClient(app) as c:
        s = c.get("/api/remote").json()
        assert s["running"] is False and s["url"] is None and s["cloudflared"] is False
        s = c.post("/api/remote/start").json()
        assert s["running"] is False and "cloudflared" in s["error"]
        assert c.post("/api/remote/stop").json()["running"] is False
        # Another website can't switch it on (origin check).
        assert c.post("/api/remote/start", headers={"Origin": "https://evil.example"}).status_code == 403


def test_new_secret_every_time(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    r = remote.Remote()
    monkeypatch.setattr(r, "_start_server", lambda: None)

    class FakeProc:
        def __init__(self, *a, **k):
            import io
            self.stdout = io.StringIO("INF |  https://abc-def.trycloudflare.com  |\n")
        def poll(self): return None
        def terminate(self): pass
        def wait(self, t=None): return 0
    monkeypatch.setattr(remote, "find_cloudflared", lambda: "cloudflared.exe")
    monkeypatch.setattr(remote, "_kill_stale", lambda exe: None)
    monkeypatch.setattr(remote.subprocess, "Popen", FakeProc)
    first = r.start()["url"]
    assert first.startswith("https://abc-def.trycloudflare.com/") and first.endswith("/mcp")
    r.stop()
    assert r.status()["url"] is None
    second = r.start()["url"]
    assert second != first  # same tunnel address in this fake, but a new secret
    r.stop()


# ---------- one-click install of cloudflared, and the reachability check ----------

class _FakeStream:
    def __init__(self, data: bytes, status: int = 200):
        self.data, self.status_code = data, status
        self.headers = {"content-length": str(len(data))}
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def iter_bytes(self, n):
        for i in range(0, len(self.data), n):
            yield self.data[i:i + n]


def test_install_keeps_only_a_signed_file(tmp_path, monkeypatch):
    import httpx
    payload = b"MZ" + b"\0" * 2_000_000
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStream(payload))
    seen = []
    monkeypatch.setattr(remote, "signature_ok", lambda p: (True, "Valid / CN=Cloudflare, Inc."))
    dest = tmp_path / "bin" / "cloudflared.exe"
    assert remote.install_cloudflared(lambda d, t: seen.append((d, t)), dest=dest) == str(dest)
    assert dest.read_bytes() == payload and seen[-1] == (len(payload), len(payload))
    assert not dest.with_suffix(".part").exists()

    dest.unlink()
    monkeypatch.setattr(remote, "signature_ok", lambda p: (False, "NotSigned"))
    with pytest.raises(remote.InstallError, match="امضا"):
        remote.install_cloudflared(dest=dest)
    assert not dest.exists() and not dest.with_suffix(".part").exists()  # nothing unsigned is left behind


def test_install_rejects_truncated_or_failed_downloads(tmp_path, monkeypatch):
    import httpx
    dest = tmp_path / "cloudflared.exe"
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStream(b"tiny"))
    with pytest.raises(remote.InstallError):
        remote.install_cloudflared(dest=dest)
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStream(b"", status=404))
    with pytest.raises(remote.InstallError, match="404"):
        remote.install_cloudflared(dest=dest)
    assert not dest.exists()


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Authenticode is Windows-only")
def test_real_signature_check_rejects_an_unsigned_file(tmp_path):
    fake = tmp_path / "cloudflared.exe"
    fake.write_bytes(b"MZ" + b"\0" * 4096)
    ok, detail = remote.signature_ok(fake)
    assert not ok


def test_install_runs_in_background_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(remote, "find_cloudflared", lambda: None)

    def fake_install(progress=None, **kw):
        progress(5, 10)
        progress(10, 10)
        return "x"
    monkeypatch.setattr(remote, "install_cloudflared", fake_install)
    r = remote.Remote()
    r.start_install()
    for _ in range(50):
        if r.install["state"] != "downloading":
            break
        time.sleep(0.02)
    assert r.install == {"state": "done", "done": 10, "total": 10, "error": None}

    def failing(progress=None, **kw):
        raise remote.InstallError("به GitHub وصل نشد.")
    monkeypatch.setattr(remote, "install_cloudflared", failing)
    r.start_install()
    for _ in range(50):
        if r.install["state"] != "downloading":
            break
        time.sleep(0.02)
    assert r.install["state"] == "error" and "GitHub" in r.install["error"]


def test_reachability_check_reports_not_ready(monkeypatch):
    monkeypatch.setattr(remote, "_public_ips", lambda host: [])
    ok, detail = remote.check_reachable("https://abc.trycloudflare.com/s/mcp")
    assert not ok and "آماده" in detail
