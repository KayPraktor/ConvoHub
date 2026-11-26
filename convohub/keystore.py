"""The OpenRouter key entered in the UI, stored next to the database but NOT inside it.

- Windows: encrypted with DPAPI (CryptProtectData) in a file next to the database, so only this Windows user
  on this machine can read it; copying the file elsewhere is useless.
- macOS: in the user's login Keychain, through Apple's `security` tool. The key is written to the tool's
  stdin (`security -i`), never put on a command line, where other processes could see it.
  If the Keychain can't be used, it falls back to the private file (below).
- Elsewhere (and the macOS fallback): a plain file only this user can read (permissions 0600).
- Backups copy the database only, so the key never ends up in a backup file.
- It is never logged and never sent back to the browser in full (only a masked hint).

macOS order, so a leftover copy never shadows the current key:
  load: the fallback file first (it only exists when the last save could not use the Keychain), then the Keychain.
  save: Keychain; when that works the fallback file is removed. Only if it fails is the file written.
  delete: both.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from . import config

KEY_FILE_NAME = "openrouter.key"
KEYCHAIN_ACCOUNT = "convohub"
KEYCHAIN_SERVICE = "ConvoHub OpenRouter key"
SECURITY = "/usr/bin/security"
_TIMEOUT_S = 15
# What may go into a `security -i` command line inside double quotes: printable ASCII without quotes,
# backslashes or spaces (OpenRouter keys are letters, digits and dashes). Anything else uses the file.
_KEYCHAIN_SAFE = re.compile(r"^[!#-&(-\[\]-~]+$")


def _key_path() -> Path:
    return config.DB_PATH.parent / KEY_FILE_NAME


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32

    def _call(fn, data: bytes) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _Blob()
        if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
            raise OSError("Windows could not encrypt/decrypt the key (DPAPI)")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _kernel32.LocalFree(blob_out.pbData)

    def _protect(data: bytes) -> bytes:
        return _call(_crypt32.CryptProtectData, data)

    def _unprotect(data: bytes) -> bytes:
        return _call(_crypt32.CryptUnprotectData, data)
else:  # no DPAPI here; the file is kept private instead (and macOS prefers the Keychain)
    def _protect(data: bytes) -> bytes:
        return data

    def _unprotect(data: bytes) -> bytes:
        return data


# ---------- macOS Keychain ----------

def _use_keychain() -> bool:
    # CONVOHUB_NO_KEYCHAIN=1: tests (and anyone who prefers the file) keep the login Keychain untouched.
    return sys.platform == "darwin" and os.environ.get("CONVOHUB_NO_KEYCHAIN") != "1"


def _security(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess | None:
    """Run Apple's `security` tool. Its output is never printed or logged (it may contain the key)."""
    try:
        return subprocess.run([SECURITY, *args], input=stdin, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None


def _keychain_add_command(key: str) -> str:
    """The `security -i` command line that saves the key (sent on stdin, never as process arguments)."""
    return (f'add-generic-password -U -a "{KEYCHAIN_ACCOUNT}" -s "{KEYCHAIN_SERVICE}" '
            f'-l "{KEYCHAIN_SERVICE}" -w "{key}"\n')


def _keychain_read() -> str | None:
    proc = _security(["find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w"])
    if proc is None or proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _keychain_save(key: str) -> bool:
    if not _KEYCHAIN_SAFE.match(key):
        return False
    proc = _security(["-i"], stdin=_keychain_add_command(key))
    if proc is None:
        return False
    # `security -i` doesn't reliably report a failed command in its exit code: read it back to be sure.
    return _keychain_read() == key


def _keychain_delete() -> None:
    _security(["delete-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE])


# ---------- the file (Windows: DPAPI-encrypted; elsewhere: private) ----------

def _file_save(key: str) -> None:
    path = _key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        # Create it private from the start, so the key is never readable by others even for a moment.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(_protect(key.encode("utf-8")))
        os.chmod(path, 0o600)
        return
    path.write_bytes(_protect(key.encode("utf-8")))


def _file_load() -> str | None:
    path = _key_path()
    if not path.exists():
        return None
    try:
        return _unprotect(path.read_bytes()).decode("utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        return None  # e.g. the file was copied from another Windows user: treat as "no key"


# ---------- public API ----------

def save_key(key: str) -> None:
    key = key.strip()
    if _use_keychain() and _keychain_save(key):
        _key_path().unlink(missing_ok=True)  # an older fallback copy must not shadow the Keychain
        return
    _file_save(key)


def load_key() -> str | None:
    found = _file_load()
    if found or not _use_keychain():
        return found
    return _keychain_read()


def delete_key() -> None:
    _key_path().unlink(missing_ok=True)
    if _use_keychain():
        _keychain_delete()


def mask(key: str | None) -> str | None:
    """'sk-or-…ab12' style hint, never the key itself."""
    if not key:
        return None
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "…"


def status() -> dict:
    env = os.getenv("OPENROUTER_API_KEY", "").strip()
    stored = load_key()
    source = "env" if env else ("saved" if stored else None)
    return {"set": bool(source), "source": source, "hint": mask(env or stored)}
