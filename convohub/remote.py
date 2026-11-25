"""Remote connector: a READ-ONLY MCP server on a temporary public HTTPS address, for apps whose MCP client runs
in the cloud (Gemini's "Connect to an MCP server" only takes an https:// URL that Google's servers call).

How it stays contained:
- Off by default. On only while the user keeps it on in the UI, and always off when ConvoHub closes.
- Its own local server on its own port: only this MCP app goes through the tunnel, never ConvoHub's API
  (settings, agent, imports, approvals).
- Read-only tools: list / search / read conversations and read memory. Nothing can be added or changed.
- A random secret in the URL path, new every time it is turned on. Anything else gets 404.
- The tunnel is Cloudflare's free "quick tunnel" (cloudflared; ConvoHub can install it for the user, from
  Cloudflare's official GitHub release, signature checked); its address also changes every time.
This is an exception to "everything stays local" that the user chose (DECISIONS #71).
"""

import functools
import hmac
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from . import config

PORT = int(os.getenv("CONVOHUB_REMOTE_PORT", str(config.PORT + 2)))
URL_WAIT_S = 45
_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
SIGNER = "Cloudflare"  # the Authenticode signer the downloaded file must have


def own_cloudflared() -> Path:
    """Where ConvoHub keeps the cloudflared it installed itself (no admin rights needed)."""
    return config.DATA_DIR / "bin" / "cloudflared.exe"


def find_cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found:
        return found
    candidates = [own_cloudflared()]
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(env):
            candidates.append(Path(os.environ[env]) / "cloudflared" / "cloudflared.exe")
    return next((str(p) for p in candidates if p.exists()), None)


# ---------- installing cloudflared for the user (one click in the UI) ----------

class InstallError(Exception):
    pass


def signature_ok(path: Path) -> tuple[bool, str]:
    """Windows Authenticode check: a valid signature whose signer is Cloudflare."""
    if sys.platform != "win32":
        return True, "not checked (not Windows)"
    ps = ("$s = Get-AuthenticodeSignature -LiteralPath $env:CH_FILE; "
          "\"$($s.Status)`t$($s.SignerCertificate.Subject)\"")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=60, env={**os.environ, "CH_FILE": str(path)},
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"signature check failed: {exc}"
    status, _, subject = out.partition("\t")
    return status == "Valid" and SIGNER.lower() in subject.lower(), f"{status} / {subject}"


def install_cloudflared(progress=None, url: str = CLOUDFLARED_URL, dest: Path | None = None) -> str:
    """Download cloudflared from Cloudflare's GitHub release, check its signature, put it in DATA_DIR/bin.

    progress(done_bytes, total_bytes) is called while downloading. Returns the installed path.
    """
    import httpx
    dest = dest or own_cloudflared()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(30, read=120)) as r:
            if r.status_code != 200:
                raise InstallError(f"دانلود نشد (کد {r.status_code}).")
            total = int(r.headers.get("content-length") or 0)
            done = 0
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        if done < 1_000_000:
            raise InstallError("فایل دانلودشده ناقصه.")
        ok, detail = signature_ok(part)
        if not ok:
            raise InstallError(f"امضای فایل دانلودشده معتبر نیست، پس نصب نشد. ({detail})")
        part.replace(dest)
        return str(dest)
    except httpx.HTTPError as exc:
        raise InstallError("به GitHub وصل نشد. اینترنت یا VPN رو چک کن و دوباره امتحان کن.") from exc
    finally:
        if part.exists():
            part.unlink(missing_ok=True)


# ---------- is the address reachable from the internet? ----------

def _public_ips(host: str) -> list[str]:
    """The host's addresses as the world sees them (Cloudflare's public DNS over HTTPS), else the local DNS."""
    import socket

    import httpx
    try:
        r = httpx.get("https://1.1.1.1/dns-query", params={"name": host, "type": "A"},
                      headers={"accept": "application/dns-json"}, timeout=8)
        ips = [a["data"] for a in r.json().get("Answer", []) if a.get("type") == 1]
        if ips:
            return ips
    except (httpx.HTTPError, ValueError):
        pass
    try:
        return [socket.gethostbyname(host)]
    except OSError:
        return []


def check_reachable(url: str) -> tuple[bool, str]:
    """One MCP 'initialize' to the public URL, the way Gemini's servers would send it."""
    import httpx
    host = url.split("/")[2]
    ips = _public_ips(host)
    if not ips:
        return False, "هنوز آماده نیست (معمولاً کمتر از یه دقیقه طول می‌کشه)."
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "convohub-check", "version": "1"}}}
    target = url.replace(host, ips[0], 1)
    try:
        with httpx.Client(timeout=15) as client:
            # Connect to the IP the public DNS gave, but speak TLS for the real name (certificate checked for it).
            req = client.build_request("POST", target, json=body, extensions={"sni_hostname": host},
                                       headers={"Host": host, "Accept": "application/json, text/event-stream"})
            r = client.send(req)
    except Exception as exc:  # network trouble of any kind: "not yet", never a crash
        return False, f"وصل نشد ({type(exc).__name__})."
    if r.status_code == 200 and "protocolVersion" in r.text:
        return True, "از اینترنت در دسترسه."
    return False, f"جواب {r.status_code} اومد."


# ---------- the read-only MCP app ----------

READ_ONLY = ("list_conversations", "search_conversations", "read_conversation", "read_memory")


def build_mcp(on_call=None):
    """A FastMCP server with only the read tools of convohub.mcp_server. on_call(name, args) logs each call."""
    from fastmcp import FastMCP

    from . import mcp_server

    remote = FastMCP("convohub", instructions=mcp_server.INSTRUCTIONS.replace(
        "read_memory returns", "This connection is read-only. read_memory returns"))
    def logged(name, fn):
        @functools.wraps(fn)  # same name, docstring and signature as the local tool
        def call(*args, **kwargs):
            if on_call:
                on_call(name, kwargs or ({"args": list(args)} if args else {}))
            return fn(*args, **kwargs)
        return call

    for name in READ_ONLY:
        remote.tool(annotations=mcp_server.READ_ONLY_HINTS)(logged(name, getattr(mcp_server, name)))
    return remote


class _SecretPath:
    """ASGI wrapper: only /<secret>/... reaches the MCP app (with the secret stripped); everything else is 404."""

    def __init__(self, app, secret: str):
        self.app = app
        self.prefix = f"/{secret}"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":  # lifespan
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        head, _, rest = path[1:].partition("/")
        if not hmac.compare_digest(("/" + head).encode(), self.prefix.encode()):
            await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"Not found"})
            return
        scope = {**scope, "path": "/" + rest, "raw_path": ("/" + rest).encode()}
        return await self.app(scope, receive, send)


def build_app(secret: str, on_call=None):
    mcp = build_mcp(on_call)
    # Requests arrive through the tunnel with the tunnel's Host; the secret path is the gate instead.
    inner = mcp.http_app(path="/mcp", stateless_http=True, host_origin_protection=False)
    return _SecretPath(inner, secret)


# ---------- turning it on and off ----------

def _kill_stale(exe: str) -> None:
    """A tunnel to our port left over from a crash (ConvoHub killed, not closed): stop it before starting anew."""
    if sys.platform != "win32":
        return
    target = f"--url http://127.0.0.1:{PORT}"  # matches our own command line only
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | "
             "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return
    for line in out.splitlines():
        pid, _, cmd = line.partition("\t")
        if cmd.rstrip().endswith(target) and pid.strip().isdigit():
            subprocess.run(["taskkill", "/PID", pid.strip(), "/F"], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

class Remote:
    def __init__(self):
        self.lock = threading.Lock()
        self.install = {"state": "idle", "done": 0, "total": 0, "error": None}  # idle/downloading/done/error
        self._reset()

    def _reset(self):
        self.secret = None
        self.public = None       # https://xxx.trycloudflare.com
        self.proc = None
        self.server = None
        self.thread = None
        self.started_at = None
        self.calls = deque(maxlen=30)
        self.error = None
        self.reachable = None    # None: not checked yet / checking; True / False after the check
        self.reach_detail = ""

    @property
    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None and self.public)

    def _log_call(self, name: str, args: dict):
        short = {k: (v if not isinstance(v, str) or len(v) < 80 else v[:80] + "…") for k, v in args.items()}
        self.calls.appendleft({"at": time.strftime("%H:%M:%S"), "tool": name, "args": short})

    def status(self) -> dict:
        url = f"{self.public}/{self.secret}/mcp" if self.running else None
        return {"running": self.running, "url": url, "started_at": self.started_at, "calls": list(self.calls),
                "error": self.error, "cloudflared": bool(find_cloudflared()), "port": PORT,
                "install": dict(self.install), "reachable": self.reachable if self.running else None,
                "reach_detail": self.reach_detail if self.running else ""}

    # ---------- one-click install of cloudflared ----------

    def start_install(self) -> dict:
        with self.lock:
            if self.install["state"] != "downloading" and not find_cloudflared():
                self.install = {"state": "downloading", "done": 0, "total": 0, "error": None}
                threading.Thread(target=self._install, daemon=True).start()
        return self.status()

    def _install(self):
        def progress(done, total):
            self.install.update(done=done, total=total)
        try:
            install_cloudflared(progress)
            self.install.update(state="done", error=None)
        except InstallError as exc:
            self.install.update(state="error", error=str(exc))
        except Exception as exc:  # report, never crash the app
            self.install.update(state="error", error=f"{type(exc).__name__}: {exc}")

    # ---------- is it reachable from the internet? (checked in the background after it turns on) ----------

    def _watch_reachable(self, url: str, tries: int = 15, wait_s: float = 4):
        for _ in range(tries):
            if not self.running or self.status()["url"] != url:
                return  # turned off or restarted meanwhile
            ok, detail = check_reachable(url)
            self.reachable, self.reach_detail = (True, detail) if ok else (None, detail)
            if ok:
                return
            time.sleep(wait_s)
        if self.running and self.status()["url"] == url:
            self.reachable = False
            self.reach_detail = ("هنوز از اینترنت در دسترس نیست: " + self.reach_detail +
                                 " شاید اینترنت یا VPN اجازه نمیده؛ خاموش و دوباره روشنش کن.")

    def start(self) -> dict:
        with self.lock:
            if self.running:
                return self.status()
            self.stop_locked()
            exe = find_cloudflared()
            if not exe:
                self.error = "ابزار تونل Cloudflare (cloudflared) هنوز نصب نیست. اول «نصب خودکار» رو بزن."
                return self.status()
            _kill_stale(exe)
            self.secret = secrets.token_urlsafe(24)
            self._start_server()
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            # An empty config of our own: otherwise cloudflared reads ~/.cloudflared/config.yml, whose ingress rules
            # (from the user's other tunnels) answer our requests with 404 before they reach us.
            empty_cfg = config.DATA_DIR / "remote-tunnel.yml"
            empty_cfg.parent.mkdir(parents=True, exist_ok=True)
            empty_cfg.write_text("# ConvoHub's temporary tunnel: intentionally empty\n", encoding="utf-8")
            self.proc = subprocess.Popen(
                [exe, "tunnel", "--config", str(empty_cfg), "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=flags)
            found, lines = threading.Event(), []

            def read():
                for line in self.proc.stdout:  # keeps draining so cloudflared never blocks on a full pipe
                    lines.append(line)
                    m = _URL_RE.search(line)
                    if m and not self.public:
                        self.public = m.group(0)
                        found.set()
            threading.Thread(target=read, daemon=True).start()
            if not found.wait(URL_WAIT_S):
                tail = " ".join(lines[-3:]).strip()[:300]
                self.stop_locked()
                self.error = ("تونل Cloudflare بالا نیومد. شاید اینترنت یا VPN اجازه نمیده؛ یه بار دیگه امتحان کن."
                              + (f"\n{tail}" if tail else ""))
                return self.status()
            self.started_at = time.strftime("%Y-%m-%d %H:%M")
            self.error = None
            url = self.status()["url"]
            threading.Thread(target=self._watch_reachable, args=(url,), daemon=True).start()
            return self.status()

    def _start_server(self):
        import uvicorn
        app = build_app(self.secret, self._log_call)
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning",
                                                    log_config=None, lifespan="on"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        for _ in range(100):  # wait until it listens
            if self.server.started:
                return
            time.sleep(0.05)

    def stop(self) -> dict:
        with self.lock:
            self.stop_locked()
            return self.status()

    def stop_locked(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(5)
        error, calls = self.error, self.calls
        self._reset()
        self.error, self.calls = error, calls


remote = Remote()
