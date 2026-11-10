"""SQLite storage for the conversation library."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    title              TEXT    NOT NULL,
    source             TEXT    NOT NULL CHECK (source IN ('gemini','claude','grok','chatgpt','native','other')),
    import_method      TEXT    NOT NULL CHECK (import_method IN ('paste','link','file','extension','native')),
    source_url         TEXT,
    raw_text           TEXT    NOT NULL DEFAULT '',
    summary            TEXT,
    summary_model      TEXT,
    summary_updated_at TEXT,
    model              TEXT,   -- native chats: the last model used
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Turns with roles, when we know them (native chats always; imports only if parsed).
CREATE TABLE IF NOT EXISTS messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id   INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    position          INTEGER NOT NULL,
    role              TEXT    NOT NULL CHECK (role IN ('user','assistant','system')),
    content           TEXT    NOT NULL,
    model             TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost              REAL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, position);

-- Which library conversations a native chat sees as context.
CREATE TABLE IF NOT EXISTS chat_context (
    chat_id         INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    use_summary     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, conversation_id)
);

-- Search index over normalized title + body. rowid = conversations.id.
-- Trigram tokenizer gives substring matching, which works for Persian without a stemmer.
CREATE VIRTUAL TABLE IF NOT EXISTS conv_fts USING fts5(title, body, tokenize = 'trigram');

-- App settings as JSON values (agent folders, MCP servers, skill folders).
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Every tool call the agent made or tried to make.
CREATE TABLE IF NOT EXISTS agent_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    tool       TEXT NOT NULL,
    args       TEXT NOT NULL,          -- JSON
    status     TEXT NOT NULL,          -- ok | error | denied | blocked
    approval   TEXT,                   -- auto | approved | denied
    result     TEXT,                   -- short preview
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agent_log_chat ON agent_log(chat_id, id);
"""

# Columns added after phase 0; older databases get them via ALTER TABLE.
_ADDED_COLUMNS = {
    "conversations": {"summary_model": "TEXT", "summary_updated_at": "TEXT", "model": "TEXT"},
    "messages": {"prompt_tokens": "INTEGER", "completion_tokens": "INTEGER", "cost": "REAL",
                 "tool_trace": "TEXT",   # JSON list of agent tool calls in this turn
                 "kind": "TEXT"},        # NULL normal | 'panel' (one of several models) | 'synthesis' 
}


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path | None = None) -> None:
    with closing(connect(db_path)) as conn:
        conn.executescript(SCHEMA)
        for table, cols in _ADDED_COLUMNS.items():
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        conn.commit()


@contextmanager
def closing(conn: sqlite3.Connection):
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def session(db_path: Path | None = None):
    """A connection that commits on success and rolls back on error."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
