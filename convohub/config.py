"""Paths and settings. Secrets are never printed or logged.

Two ways to run:
- From source (developers, `uv run python -m convohub`): data lives in <project>/data, the key can come
  from <project>/.env as before.
- Installed (ConvoHub-Setup.exe, a PyInstaller build): the program folder is read-only territory, so data
  lives in the user's profile (%LOCALAPPDATA%\\ConvoHub) and survives reinstalling or updating the app.
CONVOHUB_DATA_DIR overrides the data folder in both cases (handy for tests and portable setups).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

FROZEN = getattr(sys, "frozen", False)  # True inside the PyInstaller build

if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent             # where ConvoHub.exe is installed
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))         # PyInstaller's unpacked files
    ROOT_DIR = APP_DIR
    STATIC_DIR = BUNDLE_DIR / "convohub" / "static"
    _default_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ConvoHub"
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent           # the project folder
    APP_DIR = ROOT_DIR
    STATIC_DIR = Path(__file__).resolve().parent / "static"
    _default_data = ROOT_DIR / "data"

EXTENSION_DIR = APP_DIR / "extension"  # the unpacked browser extension (installed next to the app)
DATA_DIR = Path(os.environ["CONVOHUB_DATA_DIR"]) if os.environ.get("CONVOHUB_DATA_DIR") else _default_data
DB_PATH = DATA_DIR / "convohub.db"

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
