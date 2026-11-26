"""Interface language: Persian (fa) or English (en).

The choice is stored in the settings table (`ui_lang`) and drives everything the user reads: the web UI,
server error messages, the launcher's pop-ups, handoff text and the browser extension.

- A new install has no choice yet: the web UI picks one from the browser language and saves it.
- An install that already has conversations but no choice keeps Persian (the language it always had).
  db.init_db settles this once (remember_install), so it never changes afterwards.
- Before the database exists (the launcher on a first start) the language is the default, and nothing is created.

Server-side texts live in messages.py as {key: {"fa": ..., "en": ...}}; use t("key", name=value).
"""

from __future__ import annotations

import json

from . import config, db

LANGS = ("fa", "en")
DEFAULT = "en"
_SETTING_KEY = "ui_lang"
_cache: dict[str, str | None] = {}  # per database file (tests use many)


def stored(conn=None) -> str | None:
    """The saved choice, or None if the user never chose (and this isn't an older Persian install)."""
    key = str(config.DB_PATH)
    if key in _cache:
        return _cache[key]
    own = conn is None
    if own:
        if not config.DB_PATH.is_file():
            # First start (the launcher runs before the database exists): don't create the folder or the
            # file here, and don't remember the answer, so the real choice is read once the DB exists.
            return None
        try:
            conn = db.connect()
        except Exception:
            return None
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (_SETTING_KEY,)).fetchone()
        if row:
            value = json.loads(row["value"])
            lang = value if value in LANGS else None
        else:
            # Installs from before the English version: they have data and always were Persian.
            has_data = conn.execute("SELECT 1 FROM conversations LIMIT 1").fetchone() is not None
            lang = "fa" if has_data else None
    except Exception:  # tables not created yet (the launcher before init): ask again later
        return None
    finally:
        if own:
            conn.close()
    _cache[key] = lang
    return lang


def remember_install(conn, db_path=None) -> None:
    """Called when this version first initializes a database (db.init_db).

    Settles the "older install" question once, so it can't change later: a database that already has
    conversations but no choice is saved as Persian; an empty one gets an explicit "not chosen yet" (null),
    so conversations imported before the user picks a language don't turn it into Persian.
    """
    if conn.execute("SELECT 1 FROM settings WHERE key = ?", (_SETTING_KEY,)).fetchone():
        return
    has_data = conn.execute("SELECT 1 FROM conversations LIMIT 1").fetchone() is not None
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                 (_SETTING_KEY, json.dumps("fa" if has_data else None)))
    _cache.pop(str(db_path or config.DB_PATH), None)


def current(conn=None) -> str:
    return stored(conn) or DEFAULT


def set_lang(conn, lang: str) -> str:
    if lang not in LANGS:
        raise ValueError(f"unknown language {lang!r}")
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_SETTING_KEY, json.dumps(lang)),
    )
    _cache[str(config.DB_PATH)] = lang
    return lang


def reset_cache() -> None:
    _cache.clear()


def t(key: str, lang: str | None = None, **kwargs) -> str:
    """The text for `key` in the current language, with {placeholders} filled in."""
    from .messages import MESSAGES
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    text = entry.get(lang or current()) or entry.get(DEFAULT) or next(iter(entry.values()))
    return text.format(**kwargs) if kwargs else text


def platform_key(key: str) -> str:
    """`key` + "_mac" on macOS when that variant exists (texts about Windows-only things), else `key`."""
    from . import osinfo
    from .messages import MESSAGES
    if osinfo.is_mac() and f"{key}_mac" in MESSAGES:
        return f"{key}_mac"
    return key


def tp(key: str, lang: str | None = None, **kwargs) -> str:
    """Like t(), but picks the macOS variant of the text on a Mac (see platform_key)."""
    return t(platform_key(key), lang, **kwargs)
