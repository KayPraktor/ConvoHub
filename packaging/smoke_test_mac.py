"""Smoke test for the built macOS app. CI runs it after packaging/build_mac.sh; it works on any Mac too:

    uv run --no-sync python packaging/smoke_test_mac.py [dist/ConvoHub.app]

It runs the app's own programs (not the source code) with a throwaway data folder on a spare port and checks the
server, the web interface, the launcher, --stop and the MCP program. It never touches a real ConvoHub: port 28765
is refused, and the data folder is a new temporary one unless CONVOHUB_DATA_DIR is set.
"""

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
APP = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist" / "ConvoHub.app").resolve()
MACOS = APP / "Contents" / "MacOS"
LAUNCHER, MCP_EXE = MACOS / "ConvoHub", MACOS / "convohub-mcp"

PORT = int(os.environ.get("CONVOHUB_PORT") or 28799)
DATA = Path(os.environ.get("CONVOHUB_DATA_DIR") or tempfile.mkdtemp(prefix="convohub-smoke-")).resolve()
URL = f"http://127.0.0.1:{PORT}"
ENV = {**os.environ, "CONVOHUB_DATA_DIR": str(DATA), "CONVOHUB_PORT": str(PORT),
       "BROWSER": "true"}  # webbrowser.open runs /usr/bin/true instead of opening Safari on the build machine
ENV.pop("OPENROUTER_API_KEY", None)
SERVE_LOG = DATA / "smoke-serve-output.log"

_serve_proc: subprocess.Popen | None = None


class SmokeFailure(Exception):
    pass


def check(ok: bool, what: str) -> None:
    if not ok:
        raise SmokeFailure(what)
    print(f"  ok  {what}")


def port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def health() -> dict | None:
    try:
        r = httpx.get(f"{URL}/api/health", timeout=2)
        return r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def wait_for_health(timeout: float = 60, proc: subprocess.Popen | None = None) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = health()
        if info and info.get("ok"):
            return info
        if proc is not None and proc.poll() is not None:
            raise SmokeFailure(f"the server exited early with code {proc.returncode}")
        time.sleep(0.5)
    raise SmokeFailure(f"no answer from {URL}/api/health within {timeout:.0f}s")


def wait_until(condition, timeout: float, what: str) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.3)
    raise SmokeFailure(what)


def pid_alive(pid: int) -> bool:
    # Our own child (the --serve server of phase 1) stays a zombie until reaped, and kill(pid, 0) still
    # succeeds on a zombie: ask Popen instead, which also reaps it.
    if _serve_proc is not None and _serve_proc.pid == pid:
        return _serve_proc.poll() is None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, env=ENV, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SmokeFailure(f"{' '.join(args)} did not exit within {timeout:.0f}s") from exc


def stop_and_check(pid: int) -> None:
    res = run([str(LAUNCHER), "--stop", "--quiet"], timeout=60)
    check(res.returncode == 0, f"ConvoHub --stop --quiet exited normally (code {res.returncode})")
    wait_until(lambda: not port_open(), 30, f"port {PORT} still in use after --stop")
    check(True, f"port {PORT} is free again")
    wait_until(lambda: not pid_alive(pid), 30, f"server process {pid} still running after --stop")
    check(True, f"server process {pid} has exited")


def check_server(info: dict) -> None:
    check(info.get("version") == VERSION, f"/api/health version is {info.get('version')!r} (pyproject: {VERSION})")

    r = httpx.get(f"{URL}/", timeout=10)
    check(r.status_code == 200 and "<html" in r.text.lower(), f"GET / returns the page ({r.status_code})")
    r = httpx.get(f"{URL}/static/app.js", timeout=10)
    check(r.status_code == 200 and len(r.content) > 1000, f"GET /static/app.js ({r.status_code}, {len(r.content)} bytes)")

    r = httpx.put(f"{URL}/api/settings/lang", json={"lang": "en"}, timeout=10)
    check(r.status_code == 200 and r.json().get("lang") == "en", f"PUT /api/settings/lang en ({r.status_code})")
    check((health() or {}).get("lang") == "en", "the language is saved (health says en)")

    r = httpx.post(f"{URL}/api/memory", json={"texts": ["smoke"]}, timeout=10)
    check(r.status_code == 200, f"POST /api/memory ({r.status_code})")
    r = httpx.get(f"{URL}/api/memory", timeout=10)
    check(r.status_code == 200 and "smoke" in r.text, "GET /api/memory lists the new note")

    r = httpx.get(f"{URL}/api/integrations", timeout=10)
    check(r.status_code == 200, f"GET /api/integrations ({r.status_code})")
    info = r.json()
    cmd = info.get("mcp_command") or [""]
    check(Path(cmd[0]).resolve() == MCP_EXE.resolve(), f"the MCP command is the app's convohub-mcp ({cmd[0]})")
    ext = Path(info.get("extension_dir") or "")
    check(bool(info.get("extension_dir_exists")) and (ext / "manifest.json").is_file(),
          f"the browser extension folder exists ({ext})")


async def _mcp_session() -> tuple[list[str], str]:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    transport = StdioTransport(command=str(MCP_EXE), args=[],
                               env={"CONVOHUB_DATA_DIR": str(DATA), "CONVOHUB_PORT": str(PORT)})
    async with Client(transport, timeout=60) as client:
        tools = [t.name for t in await client.list_tools()]
        result = await client.call_tool("read_memory", {})
        text = " ".join(getattr(c, "text", "") for c in result.content)
    return tools, text


def check_mcp() -> None:
    try:
        tools, memory_text = asyncio.run(asyncio.wait_for(_mcp_session(), timeout=120))
    except SmokeFailure:
        raise
    except Exception as exc:  # any failure of the MCP program fails the smoke test
        raise SmokeFailure(f"MCP over stdio failed: {type(exc).__name__}: {exc}") from exc
    check("read_memory" in tools, f"convohub-mcp lists its tools ({', '.join(sorted(tools))})")
    check("smoke" in memory_text, "convohub-mcp read_memory returns the note added through the server")


def phase_serve() -> None:
    global _serve_proc
    print(f"\n[1] ConvoHub --serve  (port {PORT}, data {DATA})")
    with open(SERVE_LOG, "ab") as log:
        _serve_proc = subprocess.Popen([str(LAUNCHER), "--serve"], env=ENV, stdout=log, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
    info = wait_for_health(60, _serve_proc)
    check(True, "the server answers /api/health")
    check_server(info)
    check_mcp()
    stop_and_check(info["pid"])
    try:
        _serve_proc.wait(timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise SmokeFailure("the --serve process did not exit after --stop") from exc
    _serve_proc = None


def phase_launcher() -> None:
    print("\n[2] ConvoHub with no arguments (the launcher: starts the server in the background and exits)")
    started = time.time()
    res = run([str(LAUNCHER)], timeout=90)
    check(True, f"the launcher exited by itself after {time.time() - started:.1f}s (code {res.returncode})")
    info = wait_for_health(60)
    check(info.get("version") == VERSION, f"the background server answers, version {info.get('version')}")
    res = run([str(LAUNCHER)], timeout=60)  # second start while running: just opens the browser, no second server
    check(res.returncode == 0 and (health() or {}).get("pid") == info["pid"], "starting again reuses the running server")
    stop_and_check(info["pid"])


def cleanup() -> None:
    """Best effort: never leave a server running on the build machine."""
    if health():
        try:
            httpx.post(f"{URL}/api/shutdown", timeout=5)
        except httpx.HTTPError:
            pass
    if _serve_proc is not None and _serve_proc.poll() is None:
        _serve_proc.kill()


def print_logs() -> None:
    for log in (DATA / "convohub.log", SERVE_LOG):
        print(f"\n----- {log} -----")
        try:
            print(log.read_text(encoding="utf-8", errors="replace")[-20000:] or "(empty)")
        except OSError:
            print("(missing)")


def main() -> int:
    print(f"Smoke test: {APP}  (ConvoHub {VERSION})")
    if PORT == 28765:
        print("Refusing to run on port 28765: that's the real ConvoHub's port. Set CONVOHUB_PORT to a spare port.")
        return 2
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        for exe in (LAUNCHER, MCP_EXE):
            check(exe.is_file() and os.access(exe, os.X_OK), f"{exe.relative_to(APP)} is in the app")
        check((APP / "Contents" / "Resources" / "extension" / "manifest.json").is_file(),
              "the browser extension is bundled (Contents/Resources/extension)")
        check(not port_open(), f"port {PORT} is free before starting")
        phase_serve()
        phase_launcher()
    except Exception as exc:  # noqa: BLE001 - report anything, with the server logs
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        cleanup()
        print_logs()
        return 1
    finally:
        cleanup()
    print("\nSmoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
