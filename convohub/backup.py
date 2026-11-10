"""Backups of the library database.

Uses SQLite's own backup API, so the copy is consistent even while the app is writing.
A backup is taken automatically once a day while the app runs; the newest KEEP automatic ones are kept.
The backup folder can be anywhere (another drive, or a Google Drive / OneDrive synced folder).
"""

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from . import config

KEEP_AUTO = 14
AUTO_EVERY = timedelta(hours=24)
NAME_RE = re.compile(r"^convohub-(\d{8}-\d{6})(-auto)?\.db$")
SETTING_KEY = "backup_folder"


class BackupError(ValueError):
    pass


def default_folder() -> Path:
    return config.DB_PATH.parent / "backups"  # next to the database (tests use a temp folder)


def folder(conn) -> Path:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    return Path(json.loads(row["value"])) if row and json.loads(row["value"]) else default_folder()


def set_folder(conn, raw: str | None) -> Path:
    raw = (raw or "").strip().strip('"')
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            raise BackupError("مسیر باید کامل باشه، مثل D:\\Backups\\ConvoHub")
        if not p.is_dir():
            raise BackupError(f"این پوشه وجود نداره: {raw}")
        value = str(p.resolve())
    else:
        value = ""
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, json.dumps(value, ensure_ascii=False)),
    )
    return folder(conn)


def list_backups(target: Path) -> list[dict]:
    if not target.is_dir():
        return []
    items = []
    for f in target.iterdir():
        m = NAME_RE.match(f.name)
        if not (m and f.is_file()):
            continue
        try:
            created = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
        except ValueError:
            continue  # looks like ours but isn't; leave it alone
        items.append({"name": f.name, "size": f.stat().st_size, "created": created.isoformat(sep=" "),
                      "auto": bool(m.group(2))})
    return sorted(items, key=lambda i: i["name"].split("-auto")[0], reverse=True)


def create(conn, target: Path, auto: bool = False) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    name = f"convohub-{datetime.now():%Y%m%d-%H%M%S}{'-auto' if auto else ''}.db"
    dest = target / name
    out = sqlite3.connect(dest)
    try:
        conn.backup(out)  # consistent snapshot, safe while the app is running
    finally:
        out.close()
    check = sqlite3.connect(dest)
    try:
        n = check.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    finally:
        check.close()
    if auto:
        prune(target)
    return {"name": name, "size": dest.stat().st_size, "conversations": n, "path": str(dest)}


def prune(target: Path, keep: int = KEEP_AUTO) -> None:
    """Delete the oldest automatic backups beyond `keep`. Manual backups are never deleted."""
    autos = [i for i in list_backups(target) if i["auto"]]
    for old in autos[keep:]:
        (target / old["name"]).unlink(missing_ok=True)


def auto_if_due(conn) -> dict | None:
    target = folder(conn)
    newest = next(iter(list_backups(target)), None)
    if newest and datetime.now() - datetime.fromisoformat(newest["created"]) < AUTO_EVERY:
        return None
    return create(conn, target, auto=True)


def path_for(conn, name: str) -> Path:
    if not NAME_RE.match(name):
        raise BackupError("اسم فایل بکاپ معتبر نیست.")
    p = folder(conn) / name
    if not p.is_file():
        raise BackupError("این بکاپ پیدا نشد.")
    return p
