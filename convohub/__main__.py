"""Start ConvoHub (or just open it, if it is already running), or stop it.

    uv run python -m convohub              start the server and open the browser (start.bat does this)
    pythonw -m convohub                    same, without a console window (the desktop shortcut)
    python -m convohub --no-browser        don't open the browser
    python -m convohub --serve             run the server here and never open the browser
    python -m convohub --stop              stop a running ConvoHub (add --quiet: no message box)
    ConvoHub.exe [--stop] [--quiet]        the same, in the installed Windows app

macOS app (ConvoHub.app): clicking it runs `ConvoHub` with no arguments. That process starts the server as a
separate background process (`ConvoHub --serve`), waits until it answers, opens the browser and exits.
macOS won't launch a second copy of an app that is still running, so the clicked process must end quickly:
then the next click can open the browser again.
"""

import os
import subprocess
import sys
import threading
import time
import webbrowser

from . import config
from .i18n import t  # reads the saved language straight from the DB; never creates it (see i18n.stored)

URL = f"http://{config.HOST}:{config.PORT}"
# No console to print to: started with pythonw, or the macOS app (Finder gives it no terminal; its background
# server's output would be lost too). Messages then go to a log file and to message boxes.
HEADLESS = sys.stdout is None or config.MAC_APP
QUIET = "--quiet" in sys.argv  # the installer stops a running copy without any pop-up
SERVE = "--serve" in sys.argv  # the background server: it never shows message boxes (the launcher does)
START_TIMEOUT_S = 30.0


def _log_path():
    return config.DATA_DIR / "convohub.log"


def _log_to_file() -> None:
    """pythonw has no console; keep server messages in data/convohub.log instead of losing them."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = open(_log_path(), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} starting ConvoHub ---")


def _mac_dialog(text: str) -> bool:
    """A macOS message box. The text is passed as an argument, never pasted into the AppleScript source."""
    script = ["-e", "on run argv",
              "-e", 'display dialog (item 1 of argv) with title "ConvoHub" buttons {"OK"} default button 1',
              "-e", "end run"]
    try:
        subprocess.run(["osascript", *script, text], capture_output=True, timeout=600)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _message(text: str) -> None:
    if QUIET or SERVE:
        print(text)
        return
    if HEADLESS and sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "ConvoHub", 0x40)
    elif HEADLESS and sys.platform == "darwin" and _mac_dialog(text):
        print(text)  # also in the log
    else:
        print(text)


def running() -> str:
    """'convohub' if ConvoHub answers on our port, 'other' if something else uses it, '' if it's free."""
    import socket

    import httpx
    try:
        r = httpx.get(f"{URL}/api/health", timeout=1.5)
        if r.status_code == 200 and r.json().get("ok") and "version" in r.json():
            return "convohub"
    except (httpx.HTTPError, ValueError):
        pass
    with socket.socket() as s:
        s.settimeout(0.5)
        return "other" if s.connect_ex((config.HOST, config.PORT)) == 0 else ""


def port_problem() -> str:
    """A message for the user if we can't listen on our port, '' if we can.

    Windows can reserve whole port ranges (Hyper-V, WSL, Docker), which makes binding fail with
    'access forbidden' even though nothing is using the port. Without this check the app just didn't open.
    """
    import socket
    with socket.socket() as s:
        try:
            s.bind((config.HOST, config.PORT))
            return ""
        except OSError as exc:
            reserved = sys.platform == "win32" and (getattr(exc, "winerror", None) == 10013 or exc.errno == 13)
    how = t("launcher.port_how")
    if reserved:
        return t("launcher.port_reserved", port=config.PORT, how=how)
    return t("launcher.port_taken", port=config.PORT, how=how)


def _wait_for_exit(pid: int | None, timeout: float = 20.0) -> None:
    """Wait until the server process has really exited, so an installer/uninstaller can replace its files."""
    deadline = time.time() + timeout
    if pid and sys.platform == "win32":
        import ctypes
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            try:
                ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000))
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
            return
    elif pid:
        while time.time() < deadline:
            try:
                os.kill(pid, 0)  # signal 0: only asks whether the process still exists
            except ProcessLookupError:
                return
            except PermissionError:
                pass  # exists, but isn't ours (shouldn't happen): keep waiting
            except OSError:
                break
            time.sleep(0.2)
        return
    while time.time() < deadline and running():  # fallback: wait for the port to be free
        time.sleep(0.3)


def stop() -> bool:
    import httpx
    try:
        pid = httpx.get(f"{URL}/api/health", timeout=3).json().get("pid")
        r = httpx.post(f"{URL}/api/shutdown", timeout=5)
    except (httpx.HTTPError, ValueError):
        return False
    if r.status_code != 200:
        return False
    _wait_for_exit(pid)
    return True


def _open_when_ready() -> None:
    for _ in range(60):
        if running() == "convohub":
            webbrowser.open(URL)
            return
        time.sleep(0.5)


def detach_wanted(args: list[str]) -> bool:
    """True when this process should start the server in the background and exit (the macOS app)."""
    return config.MAC_APP and "--serve" not in args


def start_in_background(open_browser: bool = True, timeout: float = START_TIMEOUT_S) -> bool:
    """Start `<this executable> --serve` as its own background process, wait until it answers, open the browser.

    Returns True when the server answered in time.
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_log_path(), "ab") as log:  # catches anything printed before the server opens the log itself
        proc = subprocess.Popen([sys.executable, "--serve"], start_new_session=True, env=dict(os.environ),
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if running() == "convohub":
            if open_browser:
                webbrowser.open(URL)
            return True
        if proc.poll() is not None:  # it gave up (its reason is in the log)
            break
        time.sleep(0.3)
    _message(t("launcher.start_failed", log=_log_path()))
    return False


def serve(open_browser: bool) -> None:
    """Run the server in this process until it is shut down."""
    import uvicorn

    if config.MAC_APP:
        config.extend_path_for_mac_app()
    from .main import app
    server = uvicorn.Server(uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="warning",
                                           log_config=None if HEADLESS else uvicorn.config.LOGGING_CONFIG))
    app.state.server = server  # lets /api/shutdown stop it
    if open_browser:
        threading.Thread(target=_open_when_ready, daemon=True).start()
    print(f"ConvoHub running at {URL}  (Ctrl+C or the shut-down button to stop)")
    server.run()


def main() -> None:
    args = sys.argv[1:]
    if HEADLESS:
        _log_to_file()
    else:
        # A console using an old code page (cp1252...) would crash on the Persian messages below.
        # (Messages follow the interface language saved in the database; English before the first choice.)
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")

    if "--stop" in args:
        if running() != "convohub":
            _message(t("launcher.not_running"))
        elif stop():
            _message(t("launcher.stopped"))
        else:
            _message(t("launcher.stop_failed"))
        return

    serve_only = "--serve" in args
    want_browser = not serve_only and "--no-browser" not in args
    state = running()
    if state == "convohub":
        # Already running (maybe from the other shortcut or start.bat): don't start a second server.
        if want_browser:
            webbrowser.open(URL)
        return
    if state == "other":
        _message(t("launcher.port_other", port=config.PORT))
        return

    problem = port_problem()
    if problem:
        _message(problem)
        return

    if detach_wanted(args):
        start_in_background(open_browser=want_browser)
        return
    serve(open_browser=want_browser)


if __name__ == "__main__":
    main()
