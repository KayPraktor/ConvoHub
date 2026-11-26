"""Paths and settings. Secrets are never printed or logged.

Two ways to run:
- From source (developers, `uv run python -m convohub`): data lives in <project>/data, the key can come
  from <project>/.env as before.
- Installed (a PyInstaller build): the program folder is read-only territory, so data lives in the user's
  profile and survives reinstalling or updating the app:
    Windows (ConvoHub-Setup.exe)   %LOCALAPPDATA%\\ConvoHub
    macOS   (ConvoHub.app)         ~/Library/Application Support/ConvoHub
    Linux                          $XDG_DATA_HOME/ConvoHub (default ~/.local/share/ConvoHub)
CONVOHUB_DATA_DIR overrides the data folder in all cases (handy for tests and portable setups).
"""

import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

FROZEN = getattr(sys, "frozen", False)  # True inside the PyInstaller build
MAC_APP = bool(FROZEN) and sys.platform == "darwin"  # ConvoHub.app (the executables live in Contents/MacOS)


def frozen_data_dir(platform: str | None = None, env=None, home: Path | None = None) -> Path:
    """The data folder of the installed app on each platform (before CONVOHUB_DATA_DIR is applied)."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    if platform == "win32":
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / "ConvoHub"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "ConvoHub"
    xdg = env.get("XDG_DATA_HOME") or ""
    # The XDG spec ignores a relative XDG_DATA_HOME.
    return (Path(xdg) if xdg.startswith("/") else home / ".local" / "share") / "ConvoHub"


if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent             # where ConvoHub.exe (or Contents/MacOS) is
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))         # PyInstaller's unpacked files
    ROOT_DIR = APP_DIR
    STATIC_DIR = BUNDLE_DIR / "convohub" / "static"
    _default_data = frozen_data_dir()
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent           # the project folder
    APP_DIR = ROOT_DIR
    BUNDLE_DIR = ROOT_DIR
    STATIC_DIR = Path(__file__).resolve().parent / "static"
    _default_data = ROOT_DIR / "data"

DATA_DIR = Path(os.environ["CONVOHUB_DATA_DIR"]) if os.environ.get("CONVOHUB_DATA_DIR") else _default_data
DB_PATH = DATA_DIR / "convohub.db"

# The unpacked browser extension the user loads in Chrome/Edge.
# - Windows installer and source: next to the app (APP_DIR/extension), as before.
# - macOS app: Chrome's "Load unpacked" picker can't open folders inside a .app package, so the copy bundled
#   in the app is synced to the data folder (sync_extension). That path stays the same across app updates,
#   so the extension keeps its ID.
if MAC_APP:
    BUNDLED_EXTENSION_DIR = BUNDLE_DIR / "extension"  # Contents/Frameworks/extension (linked to Resources)
    if not BUNDLED_EXTENSION_DIR.is_dir() and (APP_DIR.parent / "Resources" / "extension").is_dir():
        BUNDLED_EXTENSION_DIR = APP_DIR.parent / "Resources" / "extension"
    EXTENSION_DIR = DATA_DIR / "extension"
else:
    BUNDLED_EXTENSION_DIR = EXTENSION_DIR = APP_DIR / "extension"

if not FROZEN:
    load_dotenv(ROOT_DIR / ".env")  # development: the key may live in .env as before

HOST = "127.0.0.1"  # local only, never exposed to the network
# Outside the ranges Windows hands out (and may reserve) for dynamic ports: 1024-15000 when Hyper-V/WSL/Docker
# lowered it, 49152-65535 by default. 8765 got reserved by Windows on one machine and the app silently failed.
PORT = int(os.getenv("CONVOHUB_PORT", "28765"))


def openrouter_key() -> str | None:
    """The OpenRouter key: from the environment/.env first, else the one saved from the UI.

    Never log or display the result.
    """
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    from . import keystore  # local import: keystore imports this module
    return keystore.load_key()


# ---------- the browser extension folder of the macOS app ----------

def _manifest_version(folder: Path) -> str | None:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError, AttributeError):
        return None


def sync_extension(src: Path | None = None, dest: Path | None = None) -> bool:
    """Copy the extension bundled in the app to `dest` when it's missing or has another manifest version.

    Only does something when the two folders differ (the macOS app); on Windows and from source they are the
    same folder. Replaces the contents of `dest` only, never anything else in the data folder.
    Returns True if it copied.
    """
    src = BUNDLED_EXTENSION_DIR if src is None else src
    dest = EXTENSION_DIR if dest is None else dest
    if Path(os.path.abspath(src)) == Path(os.path.abspath(dest)):
        return False
    version = _manifest_version(src)
    if version is None:  # nothing (valid) bundled: leave whatever is there alone
        return False
    if dest.is_dir() and not dest.is_symlink() and _manifest_version(dest) == version:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.with_name(dest.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(src, staging)  # follows the bundle's symlinks: real files end up in the copy
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    dest.mkdir(exist_ok=True)
    # Swap the contents but keep the folder itself, so a browser that loaded it from this path keeps it.
    for child in list(dest.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    for child in list(staging.iterdir()):
        child.rename(dest / child.name)
    staging.rmdir()
    return True


def extend_path_for_mac_app() -> None:
    """Apps started from Finder get a minimal PATH (/usr/bin:/bin:...). Add the usual tool folders (Homebrew,
    ~/.local/bin for uv) so the user's MCP servers (npx, uvx...) and cloudflared are found."""
    current = os.environ.get("PATH", "").split(os.pathsep) if os.environ.get("PATH") else []
    extra = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", str(Path.home() / ".local" / "bin")]
    os.environ["PATH"] = os.pathsep.join(current + [p for p in extra if p not in current])
