"""Which browser extension may use /api/extension/.

Only the user's own ConvoHub extension (its ID is saved in settings) is accepted, not any chrome-extension://.
The first time an unknown extension calls, its ID is remembered as "pending" and the ConvoHub page offers a
one-click "accept"; the user can also paste the ID from chrome://extensions.
"""

import json
import re
import time

from . import db

KEY = "extension_id"
ID_RE = re.compile(r"^[a-z0-9-]{8,64}$")

_pending: dict = {"id": None, "at": 0.0}


class PairingError(ValueError):
    pass


def paired_id() -> str | None:
    with db.session() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (KEY,)).fetchone()
    return json.loads(row["value"]) if row else None


def note_pending(ext_id: str) -> None:
    if ID_RE.match(ext_id):
        _pending.update(id=ext_id, at=time.time())


def status() -> dict:
    paired = paired_id()
    pending = _pending["id"] if _pending["id"] and _pending["id"] != paired else None
    return {"paired": paired, "pending": pending}


def set_paired(ext_id: str | None) -> dict:
    ext_id = (ext_id or "").strip().lower() or None
    if ext_id and not ID_RE.match(ext_id):
        raise PairingError("ID افزونه معتبر نیست (از صفحه‌ی chrome://extensions کپی کن).")
    with db.session() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (KEY, json.dumps(ext_id)),
        )
    if ext_id == _pending["id"]:
        _pending.update(id=None, at=0.0)
    return status()
