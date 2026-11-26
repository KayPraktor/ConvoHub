"""Which operating system ConvoHub runs on, and what its parts are called (for prompts and messages).

Functions, not constants, so tests can switch sys.platform with monkeypatch.
"""

import os
import sys
from pathlib import Path


def name() -> str:
    """'win32', 'darwin' (macOS) or 'linux' (any other Unix)."""
    if sys.platform == "win32":
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def is_windows() -> bool:
    return name() == "win32"


def is_mac() -> bool:
    return name() == "darwin"


def user_shell() -> str:
    """The shell the agent's commands run in outside Windows: the user's own login shell (macOS: zsh)."""
    return os.environ.get("SHELL") or ("/bin/zsh" if is_mac() else "/bin/sh")


# ---------- words for the model (English; the prompts are English) ----------

def computer() -> str:
    return {"win32": "Windows computer", "darwin": "Mac"}.get(name(), "Linux computer")


def shell_label() -> str:
    """The shell named in the run_command tool description."""
    if is_windows():
        return "PowerShell"
    return f"{Path(user_shell()).name} shell"


def trash() -> str:
    return {"win32": "Recycle Bin", "darwin": "Trash"}.get(name(), "trash")


def example_path() -> str:
    """An absolute path with forward slashes, the way the model should write paths."""
    return {"win32": "C:/Users/me/project/file.py",
            "darwin": "/Users/me/project/file.py"}.get(name(), "/home/me/project/file.py")
