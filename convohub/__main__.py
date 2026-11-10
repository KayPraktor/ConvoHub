"""Start ConvoHub (or just open it, if it is already running), or stop it.

    uv run python -m convohub              start the server and open the browser (start.bat does this)
    pythonw -m convohub                    same, without a console window (the desktop shortcut)
    python -m convohub --no-browser        don't open the browser
    python -m convohub --stop              stop a running ConvoHub (add --quiet: no message box)
    ConvoHub.exe [--stop] [--quiet]        the same, in the installed app
"""

import sys
import threading
import time
import webbrowser

from . import config

URL = f"http://{config.HOST}:{config.PORT}"
HEADLESS = sys.stdout is None  # started with pythonw: no console to print to


def _log_to_file() -> None:
    """pythonw has no console; keep server messages in data/convohub.log instead of losing them."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = open(config.DATA_DIR / "convohub.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} starting ConvoHub ---")


QUIET = "--quiet" in sys.argv  # the installer stops a running copy without any pop-up


def _message(text: str) -> None:
    if QUIET:
        print(text)
        return
    if HEADLESS and sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "ConvoHub", 0x40)
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


def main() -> None:
    args = sys.argv[1:]
    if HEADLESS:
        _log_to_file()
    else:
        # A console using an old code page (cp1252...) would crash on the Persian messages below.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")

    if "--stop" in args:
        if running() != "convohub":
            _message("ConvoHub روشن نیست.")
        elif stop():
            _message("ConvoHub خاموش شد.")
        else:
            _message("نتونستم ConvoHub رو خاموش کنم.")
        return

    state = running()
    if state == "convohub":
        # Already running (maybe from the other shortcut or start.bat): don't start a second server.
        if "--no-browser" not in args:
            webbrowser.open(URL)
        return
    if state == "other":
        _message(f"پورت {config.PORT} دست یه برنامه‌ی دیگه‌ست. اون برنامه رو ببند یا "
                 "CONVOHUB_PORT رو توی فایل .env عوض کن.")
        return

    import uvicorn

    from .main import app
    server = uvicorn.Server(uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="warning",
                                           log_config=None if HEADLESS else uvicorn.config.LOGGING_CONFIG))
    app.state.server = server  # lets /api/shutdown stop it
    if "--no-browser" not in args:
        threading.Thread(target=_open_when_ready, daemon=True).start()
    print(f"ConvoHub running at {URL}  (Ctrl+C or the «خاموش» button to stop)")
    server.run()


if __name__ == "__main__":
    main()
