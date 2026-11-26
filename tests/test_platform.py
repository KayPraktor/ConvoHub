"""The macOS (and Linux) code paths, tested on any machine by switching sys.platform and faking subprocesses.

Tests marked skipif need the real operating system; the CI run on a Mac runs them.
"""

import importlib
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convohub import __main__ as launcher
from convohub import api, config, keystore, osinfo, remote
from convohub.agent import fs, runner
from convohub.agent.fs import Sandbox
from convohub.messages import MESSAGES


# ---------- data folder per platform ----------

@pytest.mark.parametrize("platform, env, expected", [
    ("win32", {"LOCALAPPDATA": "/L"}, Path("/L/ConvoHub")),
    ("win32", {}, Path("/home/u/AppData/Local/ConvoHub")),
    ("darwin", {"LOCALAPPDATA": "/L", "XDG_DATA_HOME": "/x"}, Path("/home/u/Library/Application Support/ConvoHub")),
    ("linux", {"XDG_DATA_HOME": "/xdg"}, Path("/xdg/ConvoHub")),
    ("linux", {"XDG_DATA_HOME": "relative/ignored"}, Path("/home/u/.local/share/ConvoHub")),
    ("linux", {}, Path("/home/u/.local/share/ConvoHub")),
])
def test_frozen_data_dir_per_platform(platform, env, expected):
    assert config.frozen_data_dir(platform, env, Path("/home/u")) == expected


def _reload_frozen_mac(monkeypatch, tmp_path, data_dir=None):
    app = tmp_path / "Applications" / "ConvoHub.app" / "Contents"
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app / "MacOS" / "ConvoHub"))
    monkeypatch.setattr(sys, "_MEIPASS", str(app / "Frameworks"), raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))         # Path.home() on macOS/Linux
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))  # ... and on a Windows test machine
    if data_dir:
        monkeypatch.setenv("CONVOHUB_DATA_DIR", str(data_dir))
    else:
        monkeypatch.delenv("CONVOHUB_DATA_DIR", raising=False)
    return app, importlib.reload(config)


def test_frozen_mac_app_paths(monkeypatch, tmp_path):
    try:
        app, fresh = _reload_frozen_mac(monkeypatch, tmp_path)
        data = tmp_path / "home" / "Library" / "Application Support" / "ConvoHub"
        assert fresh.MAC_APP and fresh.DATA_DIR == data and fresh.DB_PATH == data / "convohub.db"
        assert fresh.APP_DIR == (app / "MacOS").resolve()
        assert fresh.STATIC_DIR == app / "Frameworks" / "convohub" / "static"
        assert fresh.BUNDLED_EXTENSION_DIR == app / "Frameworks" / "extension"
        assert fresh.EXTENSION_DIR == data / "extension"  # loadable in Chrome; outside the .app package
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_frozen_mac_app_data_dir_override(monkeypatch, tmp_path):
    try:
        _, fresh = _reload_frozen_mac(monkeypatch, tmp_path, data_dir=tmp_path / "portable")
        assert fresh.DATA_DIR == tmp_path / "portable"
        assert fresh.EXTENSION_DIR == tmp_path / "portable" / "extension"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_source_run_keeps_the_extension_next_to_the_code():
    assert not config.FROZEN and not config.MAC_APP
    assert config.EXTENSION_DIR == config.BUNDLED_EXTENSION_DIR == config.APP_DIR / "extension"


# ---------- the extension folder of the macOS app ----------

def _extension(folder: Path, version: str, files: dict[str, str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps({"manifest_version": 3, "version": version}), encoding="utf-8")
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def test_extension_is_copied_when_missing_and_left_alone_when_current(tmp_path):
    src = _extension(tmp_path / "bundle" / "extension", "1.0", {"content.js": "v1", "icons/a.txt": "i"})
    data = tmp_path / "data"
    data.mkdir()
    (data / "convohub.db").write_text("db", encoding="utf-8")
    dest = data / "extension"

    assert config.sync_extension(src, dest) is True
    assert (dest / "content.js").read_text(encoding="utf-8") == "v1" and (dest / "icons" / "a.txt").exists()
    assert not (data / "extension.new").exists()

    (dest / "content.js").write_text("touched", encoding="utf-8")  # same version: nothing is replaced
    assert config.sync_extension(src, dest) is False
    assert (dest / "content.js").read_text(encoding="utf-8") == "touched"
    assert (data / "convohub.db").read_text(encoding="utf-8") == "db"


def test_extension_is_replaced_when_the_version_differs(tmp_path):
    data = tmp_path / "data"
    dest = _extension(data / "extension", "1.0", {"content.js": "v1", "old.js": "gone soon"})
    (data / "convohub.db").write_text("db", encoding="utf-8")
    (data / "backups").mkdir()
    src = _extension(tmp_path / "bundle" / "extension", "2.0", {"content.js": "v2"})

    assert config.sync_extension(src, dest) is True
    assert json.loads((dest / "manifest.json").read_text(encoding="utf-8"))["version"] == "2.0"
    assert (dest / "content.js").read_text(encoding="utf-8") == "v2" and not (dest / "old.js").exists()
    assert sorted(p.name for p in data.iterdir()) == ["backups", "convohub.db", "extension"]  # nothing else touched


def test_extension_sync_does_nothing_without_a_bundle_or_for_the_same_folder(tmp_path):
    dest = tmp_path / "data" / "extension"
    assert config.sync_extension(tmp_path / "nothing-here", dest) is False and not dest.exists()
    same = _extension(tmp_path / "ext", "1.0", {})
    assert config.sync_extension(same, same) is False
    assert config.sync_extension() is False  # from source / Windows: the folder is used where it is


def test_server_start_syncs_the_extension(tmp_path, monkeypatch):
    src = _extension(tmp_path / "bundle" / "extension", "3.1", {"content.js": "x"})
    monkeypatch.setattr(config, "BUNDLED_EXTENSION_DIR", src)
    monkeypatch.setattr(config, "EXTENSION_DIR", tmp_path / "data" / "extension")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "data" / "s.db")
    from convohub.main import app
    with TestClient(app) as c:
        assert (tmp_path / "data" / "extension" / "content.js").exists()
        info = c.get("/api/integrations").json()
        assert info["extension_dir"] == str(tmp_path / "data" / "extension") and info["extension_dir_exists"]


# ---------- the OpenRouter key in the macOS Keychain (fake `security` tool) ----------

class FakeSecurity:
    """Plays /usr/bin/security: `-i` reads commands from stdin; find/delete get plain arguments."""

    def __init__(self, broken=False):
        self.items, self.calls, self.broken = {}, [], broken

    def __call__(self, argv, input=None, **kw):
        self.calls.append((list(argv), input))
        if self.broken:
            raise OSError("no security tool")
        assert argv[0] == keystore.SECURITY
        args = argv[1:]
        out, code = "", 0
        if args == ["-i"]:
            for line in (input or "").splitlines():
                words = [w for w in shlex.split(line) if w != "-U"]  # -U: update if it exists
                if words and words[0] == "add-generic-password":
                    opts = dict(zip(words[1::2], words[2::2]))
                    self.items[(opts["-a"], opts["-s"])] = opts["-w"]
        elif args[0] == "find-generic-password":
            item = (args[args.index("-a") + 1], args[args.index("-s") + 1])
            if item in self.items:
                out = self.items[item] + "\n"
            else:
                code = 44
        elif args[0] == "delete-generic-password":
            code = 0 if self.items.pop((args[args.index("-a") + 1], args[args.index("-s") + 1]), None) else 44
        return subprocess.CompletedProcess(argv, code, out, "")


@pytest.fixture
def mac_keychain(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "k.db")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(keystore, "_use_keychain", lambda: True)
    fake = FakeSecurity()
    monkeypatch.setattr(keystore.subprocess, "run", fake)
    return fake


KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # fake, built at runtime


def test_keychain_save_load_delete_never_puts_the_key_in_argv(mac_keychain, tmp_path):
    keystore.save_key(KEY)
    assert mac_keychain.items == {("convohub", "ConvoHub OpenRouter key"): KEY}
    assert not (tmp_path / keystore.KEY_FILE_NAME).exists()
    assert keystore.load_key() == KEY and keystore.status()["hint"] == keystore.mask(KEY)
    for argv, _ in mac_keychain.calls:
        assert KEY not in " ".join(argv)  # never visible in the process list
    stdin = next(inp for argv, inp in mac_keychain.calls if argv[1:] == ["-i"])
    assert stdin == ('add-generic-password -U -a "convohub" -s "ConvoHub OpenRouter key" '
                     f'-l "ConvoHub OpenRouter key" -w "{KEY}"\n')

    keystore.delete_key()
    assert mac_keychain.items == {} and keystore.load_key() is None and not keystore.status()["set"]


def test_keychain_save_removes_a_stale_fallback_file(mac_keychain, tmp_path):
    (tmp_path / keystore.KEY_FILE_NAME).write_bytes(keystore._protect(b"sk-or-v1-old-old-old-old"))
    assert keystore.load_key() == "sk-or-v1-old-old-old-old"
    keystore.save_key(KEY)
    assert not (tmp_path / keystore.KEY_FILE_NAME).exists() and keystore.load_key() == KEY


def test_keychain_failure_falls_back_to_a_private_file_that_wins(mac_keychain, tmp_path, monkeypatch):
    keystore.save_key("sk-or-v1-older-key-in-keychain")
    mac_keychain.broken = True  # e.g. the Keychain is locked or `security` is missing
    keystore.save_key(KEY)
    path = tmp_path / keystore.KEY_FILE_NAME
    assert path.exists() and keystore.load_key() == KEY  # the newer file shadows the older Keychain item
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600
    mac_keychain.broken = False
    keystore.delete_key()
    assert not path.exists() and mac_keychain.items == {} and keystore.load_key() is None


def test_keychain_unreadable_after_save_counts_as_failure(mac_keychain, tmp_path, monkeypatch):
    real = mac_keychain.__call__

    def ignores_add(argv, input=None, **kw):  # `security -i` "succeeds" but nothing is stored
        if argv[1:] == ["-i"]:
            return subprocess.CompletedProcess(argv, 0, "", "")
        return real(argv, input=input, **kw)
    monkeypatch.setattr(keystore.subprocess, "run", ignores_add)
    keystore.save_key(KEY)
    assert (tmp_path / keystore.KEY_FILE_NAME).exists() and keystore.load_key() == KEY


def test_keys_that_cant_be_quoted_safely_use_the_file(mac_keychain, tmp_path):
    odd = 'sk-or-v1-has"quote\\and-more'
    keystore.save_key(odd)
    assert not any(argv[1:] == ["-i"] for argv, _ in mac_keychain.calls)
    assert keystore.load_key() == odd and (tmp_path / keystore.KEY_FILE_NAME).exists()


def test_keychain_is_used_only_on_a_mac(monkeypatch):
    monkeypatch.delenv("CONVOHUB_NO_KEYCHAIN", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert keystore._use_keychain()
    monkeypatch.setenv("CONVOHUB_NO_KEYCHAIN", "1")
    assert not keystore._use_keychain()
    monkeypatch.delenv("CONVOHUB_NO_KEYCHAIN")
    for other in ("win32", "linux"):
        monkeypatch.setattr(sys, "platform", other)
        assert not keystore._use_keychain()


@pytest.mark.skipif(sys.platform != "darwin" or os.environ.get("CONVOHUB_TEST_KEYCHAIN") != "1",
                    reason="real login Keychain: macOS with CONVOHUB_TEST_KEYCHAIN=1 only")
def test_real_keychain_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "real.db")
    monkeypatch.delenv("CONVOHUB_NO_KEYCHAIN", raising=False)
    monkeypatch.setattr(keystore, "KEYCHAIN_SERVICE", "ConvoHub test key (safe to delete)")
    try:
        keystore.save_key(KEY)
        assert not (tmp_path / keystore.KEY_FILE_NAME).exists(), "the Keychain wasn't used"
        assert keystore.load_key() == KEY
    finally:
        keystore.delete_key()
    assert keystore.load_key() is None


# ---------- the launcher: the macOS app starts its server in the background ----------

def test_detach_only_for_the_mac_app_without_serve(monkeypatch):
    monkeypatch.setattr(config, "MAC_APP", True)
    assert launcher.detach_wanted([]) and launcher.detach_wanted(["--no-browser"])
    assert not launcher.detach_wanted(["--serve"])
    monkeypatch.setattr(config, "MAC_APP", False)
    assert not launcher.detach_wanted([]) and not launcher.detach_wanted(["--serve"])


class FakePopen:
    instances = []

    def __init__(self, argv, **kw):
        self.argv, self.kw, self.code = argv, kw, None
        FakePopen.instances.append(self)

    def poll(self):
        return self.code


@pytest.fixture
def fake_start(tmp_path, monkeypatch):
    FakePopen.instances = []
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(launcher.subprocess, "Popen", FakePopen)
    opened, messages = [], []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    monkeypatch.setattr(launcher, "_message", messages.append)
    monkeypatch.setattr(launcher.time, "sleep", lambda s: None)
    return opened, messages


def test_start_in_background_starts_itself_with_serve_and_opens_the_browser(fake_start, monkeypatch):
    opened, messages = fake_start
    answers = iter(["", "", "convohub"])
    monkeypatch.setattr(launcher, "running", lambda: next(answers))
    assert launcher.start_in_background() is True
    proc = FakePopen.instances[0]
    assert proc.argv == [sys.executable, "--serve"]
    assert proc.kw["start_new_session"] is True and proc.kw["stdin"] is subprocess.DEVNULL
    assert proc.kw["env"] == dict(os.environ)
    assert opened == [launcher.URL] and messages == []


def test_start_in_background_without_browser(fake_start, monkeypatch):
    opened, _ = fake_start
    monkeypatch.setattr(launcher, "running", lambda: "convohub")
    assert launcher.start_in_background(open_browser=False) is True and opened == []


def test_start_in_background_reports_a_server_that_gave_up(fake_start, monkeypatch):
    opened, messages = fake_start

    def never():
        FakePopen.instances[-1].code = 1  # the server process exited
        return ""
    monkeypatch.setattr(launcher, "running", never)
    assert launcher.start_in_background(timeout=5) is False
    assert opened == [] and len(messages) == 1 and str(config.DATA_DIR / "convohub.log") in messages[0]


@pytest.fixture
def fake_main(monkeypatch):
    monkeypatch.setattr(launcher, "HEADLESS", True)
    monkeypatch.setattr(launcher, "_log_to_file", lambda: None)
    monkeypatch.setattr(launcher, "running", lambda: "")
    monkeypatch.setattr(launcher, "port_problem", lambda: "")
    calls = []
    monkeypatch.setattr(launcher, "start_in_background", lambda open_browser=True: calls.append(("bg", open_browser)))
    monkeypatch.setattr(launcher, "serve", lambda open_browser: calls.append(("serve", open_browser)))
    return calls


@pytest.mark.parametrize("mac_app, argv, expected", [
    (True, [], ("bg", True)),
    (True, ["--no-browser"], ("bg", False)),
    (True, ["--serve"], ("serve", False)),
    (False, [], ("serve", True)),              # Windows and from source: as before
    (False, ["--no-browser"], ("serve", False)),
    (False, ["--serve"], ("serve", False)),
])
def test_main_chooses_where_the_server_runs(fake_main, monkeypatch, mac_app, argv, expected):
    monkeypatch.setattr(config, "MAC_APP", mac_app)
    monkeypatch.setattr(sys, "argv", ["convohub", *argv])
    launcher.main()
    assert fake_main == [expected]


def test_main_only_opens_the_browser_when_already_running(fake_main, monkeypatch):
    monkeypatch.setattr(launcher, "running", lambda: "convohub")
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    for mac_app in (True, False):
        monkeypatch.setattr(config, "MAC_APP", mac_app)
        monkeypatch.setattr(sys, "argv", ["ConvoHub"])
        launcher.main()
        monkeypatch.setattr(sys, "argv", ["ConvoHub", "--serve"])  # a second background server: just exits
        launcher.main()
    assert fake_main == [] and opened == [launcher.URL, launcher.URL]


def test_mac_message_box_passes_the_text_as_an_argument(monkeypatch):
    runs = []
    monkeypatch.setattr(launcher.subprocess, "run", lambda argv, **kw: runs.append(argv))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(launcher, "HEADLESS", True)
    monkeypatch.setattr(launcher, "QUIET", False)
    monkeypatch.setattr(launcher, "SERVE", False)
    text = 'Port 1 is "busy" \\ end tell'
    launcher._message(text)
    assert runs == [["osascript", "-e", "on run argv",
                     "-e", 'display dialog (item 1 of argv) with title "ConvoHub" buttons {"OK"} default button 1',
                     "-e", "end run", text]]
    for flag in ("QUIET", "SERVE"):  # the installer's --quiet and the background server never pop up
        monkeypatch.setattr(launcher, flag, True)
        launcher._message("x")
        monkeypatch.setattr(launcher, flag, False)
    assert len(runs) == 1


def test_mac_message_box_falls_back_to_printing(monkeypatch, capsys):
    def missing(argv, **kw):
        raise OSError("no osascript")
    monkeypatch.setattr(launcher.subprocess, "run", missing)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(launcher, "HEADLESS", True)
    monkeypatch.setattr(launcher, "QUIET", False)
    monkeypatch.setattr(launcher, "SERVE", False)
    launcher._message("hello")
    assert "hello" in capsys.readouterr().out


def test_wait_for_exit_polls_the_pid_outside_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    seen = []

    def fake_kill(pid, sig):  # never the real os.kill here (on Windows it would end the process)
        seen.append((pid, sig))
        if len(seen) >= 3:
            raise ProcessLookupError
    monkeypatch.setattr(launcher.os, "kill", fake_kill)
    monkeypatch.setattr(launcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(launcher, "running", lambda: pytest.fail("must not fall back to the port check"))
    launcher._wait_for_exit(4242, timeout=5)
    assert seen == [(4242, 0)] * 3


@pytest.mark.skipif(sys.platform == "win32", reason="os.kill(pid, 0) is a real existence check only on POSIX")
def test_wait_for_exit_returns_when_a_real_process_ends():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    threading.Thread(target=proc.wait, daemon=True).start()  # reap it, like launchd does for the real server
    start = time.time()
    launcher._wait_for_exit(proc.pid, timeout=15)
    assert proc.poll() is not None and time.time() - start < 10


def test_port_reserved_message_is_windows_only(monkeypatch):
    import socket

    class Refused(socket.socket):
        def bind(self, addr):
            raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(socket, "socket", Refused)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert "Windows" not in launcher.port_problem()
    monkeypatch.setattr(sys, "platform", "win32")
    assert "Windows" in launcher.port_problem()


# ---------- API: platform, MCP command, opening folders ----------

def test_health_and_integrations_report_the_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "p.db")
    from convohub.main import app
    with TestClient(app) as c:
        assert c.get("/api/health").json()["platform"] == osinfo.name() in ("win32", "darwin", "linux")
        assert c.get("/api/integrations").json()["platform"] == osinfo.name()


@pytest.mark.parametrize("platform, expected", [("darwin", "darwin"), ("win32", "win32"), ("linux", "linux"),
                                                ("freebsd14", "linux")])
def test_osinfo_name(monkeypatch, platform, expected):
    monkeypatch.setattr(sys, "platform", platform)
    assert osinfo.name() == expected


def test_mcp_command_of_the_frozen_mac_app(monkeypatch, tmp_path):
    macos = tmp_path / "ConvoHub.app" / "Contents" / "MacOS"
    monkeypatch.setattr(config, "FROZEN", True)
    monkeypatch.setattr(config, "APP_DIR", macos)
    monkeypatch.setattr(sys, "platform", "darwin")
    info = api.integrations()
    exe = str(macos / "convohub-mcp")
    assert info["mcp_command"] == [exe] and info["platform"] == "darwin"
    assert json.loads(info["opencode"])["convohub"]["command"] == [exe]
    assert json.loads(info["cline"])["convohub"]["command"] == exe
    assert exe in info["claude_code"] and exe in info["hermes"]

    monkeypatch.setattr(sys, "platform", "win32")  # the Windows installer: unchanged
    assert api._mcp_command() == [str(macos / "convohub-mcp.exe")]
    monkeypatch.setattr(config, "FROZEN", False)  # from source: uv run, on every platform
    assert api._mcp_command()[:3] == ["uv", "run", "--directory"]


@pytest.mark.parametrize("platform, expected", [("darwin", ["open"]), ("linux", ["xdg-open"]), ("win32", None)])
def test_open_folder_command(monkeypatch, tmp_path, platform, expected):
    monkeypatch.setattr(sys, "platform", platform)
    cmd = api.open_folder_command(tmp_path)
    assert cmd == (None if expected is None else [*expected, str(tmp_path)])


def test_open_folder_endpoint_runs_the_command_without_a_shell(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "o.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api, "open_folder_command", lambda p: ["open", str(p)])
    runs = []

    def fake_run(argv, **kw):
        runs.append((argv, kw.get("shell")))
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    from convohub.main import app
    with TestClient(app) as c:
        assert c.post("/api/open-folder", json={"which": "data"}).json() == {"ok": True}
        assert runs == [(["open", str(tmp_path)], None)]

        def failing(argv, **kw):
            raise subprocess.CalledProcessError(1, argv)
        monkeypatch.setattr(subprocess, "run", failing)
        res = c.post("/api/open-folder", json={"which": "data"})
        assert res.status_code == 400 and str(tmp_path) in res.json()["detail"]


# ---------- agent: the shell, the prompts, paths ----------

def test_run_command_shell_per_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("SHELL", raising=False)
    assert fs.shell_command("ls -la") == ["/bin/zsh", "-lc", "ls -la"]
    monkeypatch.setenv("SHELL", "/opt/homebrew/bin/bash")
    assert fs.shell_command("ls") == ["/opt/homebrew/bin/bash", "-lc", "ls"]
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("SHELL")
    assert fs.shell_command("ls") == ["/bin/sh", "-lc", "ls"]
    monkeypatch.setattr(sys, "platform", "win32")
    assert fs.shell_command("dir") == ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                       "[Console]::OutputEncoding=[Text.Encoding]::UTF8; dir"]


def test_run_command_on_a_mac_uses_the_shell_and_utf8(tmp_path, monkeypatch):
    sb = Sandbox([str(tmp_path)])
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setenv("LANG", "C")
    monkeypatch.delenv("LC_ALL", raising=False)
    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, **kw)
        return subprocess.CompletedProcess(argv, 0, "héllo\n".encode(), b"")
    monkeypatch.setattr(fs.subprocess, "run", fake_run)
    out = sb.run_command("echo héllo", None)
    assert seen["argv"] == ["/bin/zsh", "-lc", "echo héllo"] and seen["timeout"] == fs.COMMAND_TIMEOUT_S
    assert seen["env"]["LANG"] == "en_US.UTF-8" and seen["stdin"] is subprocess.DEVNULL
    assert Path(seen["cwd"]) == tmp_path.resolve()
    assert "[exit code 0]" in out and "héllo" in out


@pytest.mark.skipif(sys.platform == "win32", reason="the real POSIX shell")
def test_run_command_real_shell(tmp_path):
    sb = Sandbox([str(tmp_path)])
    out = sb.run_command("printf 'h\\303\\251llo'; pwd", None)
    assert "[exit code 0]" in out and "héllo" in out and tmp_path.resolve().as_posix() in out


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths")
def test_posix_paths_have_no_drive_letter_check(tmp_path):
    sb = Sandbox([str(tmp_path)])
    (tmp_path / "C:notes.txt").write_text("x", encoding="utf-8")  # a legal file name on macOS
    assert "x" in sb.read_file("C:notes.txt")


def test_agent_texts_on_a_mac(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    for prompt in (runner.agent_prompt(), runner.read_prompt()):
        assert "/Users/me/project/file.py" in prompt
        assert not any(w in prompt for w in ("Windows", "PowerShell", "Recycle", "C:/"))
    assert "user's Mac:" in runner.agent_prompt() and "run_command (zsh shell), delete_path (to Trash)" in runner.agent_prompt()
    defs = {d["function"]["name"]: d["function"]["description"] for d in runner._defs(runner.CHANGE_TOOLS)}
    assert defs["run_command"].startswith("Run a zsh shell command in an allowed folder")
    assert defs["delete_path"].startswith("Move a file or folder to the Trash.")


def test_agent_texts_on_windows_are_unchanged(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    prompt = runner.agent_prompt()
    assert "You can use tools on the user's Windows computer:" in prompt
    assert "run_command (PowerShell), delete_path (to Recycle Bin)" in prompt
    assert "C:/Users/me/project/file.py" in prompt and "C:/Users/me/project/file.py" in runner.read_prompt()
    defs = {d["function"]["name"]: d["function"]["description"] for d in runner._defs(runner.CHANGE_TOOLS)}
    assert defs["run_command"] == "Run a PowerShell command in an allowed folder (timeout 120s). Needs the user's approval."
    assert defs["delete_path"] == "Move a file or folder to the Recycle Bin. Always needs the user's approval."


def test_trash_name_per_platform(monkeypatch):
    for platform, word in (("win32", "Recycle Bin"), ("darwin", "Trash"), ("linux", "trash")):
        monkeypatch.setattr(sys, "platform", platform)
        assert osinfo.trash() == word


# ---------- the online address: cloudflared on a Mac ----------

def test_cloudflared_candidates_on_a_mac(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert remote.cloudflared_candidates() == [Path("/opt/homebrew/bin/cloudflared"),
                                               Path("/usr/local/bin/cloudflared"),
                                               tmp_path / "bin" / "cloudflared"]
    assert remote.own_cloudflared() == tmp_path / "bin" / "cloudflared"


def test_find_cloudflared_prefers_path_then_candidates(monkeypatch, tmp_path):
    first, second = tmp_path / "a" / "cloudflared", tmp_path / "b" / "cloudflared"
    monkeypatch.setattr(remote, "cloudflared_candidates", lambda: [first, second])
    monkeypatch.setattr(remote.shutil, "which", lambda name: None)
    assert remote.find_cloudflared() is None
    second.parent.mkdir()
    second.write_text("bin", encoding="utf-8")
    assert remote.find_cloudflared() == str(second)
    monkeypatch.setattr(remote.shutil, "which", lambda name: "/somewhere/on/PATH/cloudflared")
    assert remote.find_cloudflared() == "/somewhere/on/PATH/cloudflared"


def test_no_one_click_install_on_a_mac(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(remote, "find_cloudflared", lambda: None)
    monkeypatch.setattr(remote, "install_cloudflared", lambda *a, **k: pytest.fail("must not download"))
    monkeypatch.setattr(sys, "platform", "darwin")
    r = remote.Remote()
    s = r.start_install()
    assert s["can_install"] is False and s["install"]["state"] == "idle" and s["cloudflared"] is False
    assert s["install_hint"] == MESSAGES["remote.install_unavailable_mac"]["en"]
    assert "brew install cloudflared" in s["install_hint"]
    assert r.start()["error"] == MESSAGES["remote.no_cloudflared_mac"]["en"]

    monkeypatch.setattr(sys, "platform", "win32")  # Windows keeps the one-click install
    s = r.status()
    assert s["can_install"] is True and s["install_hint"] == ""


def test_stale_tunnel_matching_is_limited_to_our_own_tunnel(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "Application Support" / "ConvoHub")
    cfg = remote.tunnel_config()
    ours = f"/opt/homebrew/bin/cloudflared tunnel --config {cfg} --no-autoupdate --url http://127.0.0.1:{remote.PORT}"
    ps = "\n".join([
        f"  101 {ours}",
        "  102 /usr/local/bin/cloudflared tunnel --config /Users/me/.cloudflared/config.yml run my-site",
        f"  103 /opt/homebrew/bin/cloudflared tunnel --config {cfg} --no-autoupdate --url http://127.0.0.1:9",
        f"  104 vim {cfg}",
        f"  105 {ours}",
        "  garbage line",
    ])
    assert remote.stale_tunnel_pids(ps, own_pid=105) == [101]


def test_kill_stale_on_a_mac_signals_only_our_tunnel(monkeypatch, tmp_path):
    import signal
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    cfg = remote.tunnel_config()
    ps = (f"  201 cloudflared tunnel --config {cfg} --no-autoupdate --url http://127.0.0.1:{remote.PORT}\n"
          f"  202 cloudflared tunnel run someone-elses\n")
    monkeypatch.setattr(sys, "platform", "darwin")
    calls, killed = [], []
    monkeypatch.setattr(remote.subprocess, "run",
                        lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, ps, ""))
    monkeypatch.setattr(remote.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    remote._kill_stale("/opt/homebrew/bin/cloudflared")
    assert calls == [["ps", "-axww", "-o", "pid=,command="]] and killed == [(201, signal.SIGTERM)]


# ---------- link import and shortcuts ----------

def test_no_browser_message_per_platform(monkeypatch):
    from convohub.importers import links

    class PWError(Exception):
        pass

    class Chromium:
        def launch(self, **kw):
            raise PWError("not installed")

    class PW:
        chromium = Chromium()
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(links.LinkImportError) as exc:
        links._launch(PW(), PWError)
    assert str(exc.value) == MESSAGES["link.no_browser_mac"]["en"] and "Windows" not in str(exc.value)
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(links.LinkImportError) as exc:
        links._launch(PW(), PWError)
    assert str(exc.value) == MESSAGES["link.no_browser"]["en"]


def test_shortcut_module_imports_everywhere_and_explains_itself_on_a_mac(monkeypatch):
    from convohub import shortcut
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(SystemExit) as exc:
        shortcut.create()
    assert str(exc.value) == MESSAGES["shortcut.windows_only_mac"]["en"]


def test_mac_path_extension_adds_homebrew_once(monkeypatch):
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin", "/usr/local/bin"]))
    config.extend_path_for_mac_app()
    config.extend_path_for_mac_app()
    parts = os.environ["PATH"].split(os.pathsep)
    assert parts[:3] == ["/usr/bin", "/bin", "/usr/local/bin"]
    assert parts.count("/opt/homebrew/bin") == 1 and parts.count("/usr/local/bin") == 1
