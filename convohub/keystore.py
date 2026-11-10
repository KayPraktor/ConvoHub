"""The OpenRouter key entered in the UI, stored next to the database but NOT inside it.

- On Windows it is encrypted with DPAPI (CryptProtectData), so only this Windows user on this machine can
  read the file; copying it elsewhere is useless.
- Backups copy the database only, so the key never ends up in a backup file.
- It is never logged and never sent back to the browser in full (only a masked hint).
"""

import os
import sys
from pathlib import Path

from . import config

KEY_FILE_NAME = "openrouter.key"


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
else:  # not the target platform; keep the file private instead
    def _protect(data: bytes) -> bytes:
        return data

    def _unprotect(data: bytes) -> bytes:
        return data


def save_key(key: str) -> None:
    path = _key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_protect(key.strip().encode("utf-8")))
    if sys.platform != "win32":
        os.chmod(path, 0o600)


def load_key() -> str | None:
    path = _key_path()
    if not path.exists():
        return None
    try:
        return _unprotect(path.read_bytes()).decode("utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        return None  # e.g. the file was copied from another Windows user: treat as "no key"


def delete_key() -> None:
    _key_path().unlink(missing_ok=True)


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
