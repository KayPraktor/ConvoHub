"""Data access for the conversation library and native chats."""

import json
import sqlite3

from .text import normalize_for_search

ROLE_LABELS = {"user": "User", "assistant": "Assistant", "system": "System"}

_LIST_COLUMNS = """
    c.id, c.title, c.source, c.import_method, c.source_url, c.created_at, c.updated_at,
    c.model, length(c.raw_text) AS chars, c.summary IS NOT NULL AS has_summary
"""


# ---------- conversations ----------

def create_conversation(
    conn: sqlite3.Connection,
    *,
    title: str,
    source: str,
    import_method: str,
    raw_text: str = "",
    source_url: str | None = None,
    messages: list[dict] | None = None,
    model: str | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO conversations (title, source, import_method, source_url, raw_text, model)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (title, source, import_method, source_url, raw_text, model),
    )
    conv_id = cur.lastrowid
    if messages:
        _insert_messages(conn, conv_id, messages)
    reindex(conn, conv_id)
    return conv_id


def replace_content(conn, conv_id: int, raw_text: str, messages: list[dict] | None = None) -> None:
    """Used by 'read again' for link imports."""
    conn.execute(
        "UPDATE conversations SET raw_text = ?, updated_at = datetime('now') WHERE id = ?",
        (raw_text, conv_id),
    )
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    if messages:
        _insert_messages(conn, conv_id, messages)
    reindex(conn, conv_id)


def _insert_messages(conn, conv_id: int, messages: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO messages (conversation_id, position, role, content) VALUES (?, ?, ?, ?)",
        [(conv_id, i, m["role"], m["content"]) for i, m in enumerate(messages)],
    )


def list_conversations(conn) -> list[dict]:
    rows = conn.execute(f"SELECT {_LIST_COLUMNS} FROM conversations c ORDER BY c.updated_at DESC, c.id DESC")
    return [dict(r) for r in rows]


def get_conversation(conn, conv_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if not row:
        return None
    conv = dict(row)
    conv["messages"] = get_messages(conn, conv_id)
    return conv


def get_messages(conn, conv_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT id, position, role, content, model, prompt_tokens, completion_tokens, cost, tool_trace, kind,
                  created_at
           FROM messages WHERE conversation_id = ? ORDER BY position""",
        (conv_id,),
    )
    out = []
    for r in rows:
        m = dict(r)
        m["tool_trace"] = json.loads(m["tool_trace"]) if m["tool_trace"] else None
        out.append(m)
    return out


def conversation_text(conn, conv_id: int) -> str:
    """Full text of a conversation as it is sent to a model."""
    row = conn.execute("SELECT source, raw_text FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if not row:
        return ""
    if row["source"] != "native":
        return row["raw_text"]
    return render_messages(get_messages(conn, conv_id))


def _label(m: dict) -> str:
    if m.get("kind") == "panel":
        return f"Assistant ({m.get('model')})"
    if m.get("kind") == "synthesis":
        return f"Synthesis ({m.get('model')})"
    return ROLE_LABELS[m["role"]]


def render_messages(messages: list[dict]) -> str:
    return "\n\n".join(f"{_label(m)}:\n{m['content']}" for m in messages)


def rename(conn, conv_id: int, title: str) -> bool:
    cur = conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conv_id))
    if cur.rowcount:
        reindex(conn, conv_id)
    return cur.rowcount > 0


def delete(conn, conv_id: int) -> bool:
    conn.execute("DELETE FROM conv_fts WHERE rowid = ?", (conv_id,))
    cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    return cur.rowcount > 0


def set_summary(conn, conv_id: int, summary: str, model: str) -> None:
    conn.execute(
        "UPDATE conversations SET summary = ?, summary_model = ?, summary_updated_at = datetime('now') WHERE id = ?",
        (summary, model, conv_id),
    )


# ---------- search ----------

def reindex(conn, conv_id: int) -> None:
    row = conn.execute("SELECT title FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    conn.execute("DELETE FROM conv_fts WHERE rowid = ?", (conv_id,))
    if row:
        body = conversation_text(conn, conv_id)
        conn.execute(
            "INSERT INTO conv_fts (rowid, title, body) VALUES (?, ?, ?)",
            (conv_id, normalize_for_search(row["title"]), normalize_for_search(body)),
        )


def search(conn, query: str, limit: int = 50) -> list[dict]:
    terms = [t for t in normalize_for_search(query).split() if t]
    if not terms:
        return []

    long_terms = [t for t in terms if len(t) >= 3]
    short_terms = [t for t in terms if len(t) < 3]
    where, params = [], []
    if long_terms:
        where.append("conv_fts MATCH ?")
        params.append(" AND ".join('"' + t.replace('"', '""') + '"' for t in long_terms))
    for t in short_terms:
        where.append("(f.title LIKE ? OR f.body LIKE ?)")
        params += [f"%{t}%", f"%{t}%"]

    rows = conn.execute(
        f"""SELECT {_LIST_COLUMNS}, f.body AS _body
            FROM conv_fts f JOIN conversations c ON c.id = f.rowid
            WHERE {' AND '.join(where)}
            ORDER BY c.updated_at DESC LIMIT ?""",
        (*params, limit),
    )
    results = []
    for r in rows:
        item = dict(r)
        item["snippet"] = _snippet(item.pop("_body"), terms[0])
        results.append(item)
    return results


def _snippet(body: str, term: str, width: int = 70) -> str:
    i = body.find(term)
    if i < 0:
        return ""
    start, end = max(0, i - width), min(len(body), i + len(term) + width)
    text = body[start:end].replace("\n", " ")
    return ("…" if start else "") + text + ("…" if end < len(body) else "")


# ---------- native chats ----------

def create_chat(conn, title: str, model: str | None) -> int:
    return create_conversation(conn, title=title, source="native", import_method="native", model=model)


def add_message(conn, chat_id: int, role: str, content: str, *, model=None, prompt_tokens=None,
                completion_tokens=None, cost=None, tool_trace: list | None = None, kind: str | None = None) -> int:
    pos = conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM messages WHERE conversation_id = ?", (chat_id,)
    ).fetchone()[0]
    cur = conn.execute(
        """INSERT INTO messages (conversation_id, position, role, content, model, prompt_tokens, completion_tokens,
                                 cost, tool_trace, kind)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (chat_id, pos, role, content, model, prompt_tokens, completion_tokens, cost,
         json.dumps(tool_trace, ensure_ascii=False) if tool_trace else None, kind),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now'), model = COALESCE(?, model) WHERE id = ?",
        (model, chat_id),
    )
    reindex(conn, chat_id)
    return cur.lastrowid


def get_context(conn, chat_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT cc.conversation_id AS id, cc.use_summary, c.title, c.source, c.summary IS NOT NULL AS has_summary
           FROM chat_context cc JOIN conversations c ON c.id = cc.conversation_id
           WHERE cc.chat_id = ? ORDER BY c.id""",
        (chat_id,),
    )
    return [dict(r) for r in rows]


def set_context(conn, chat_id: int, items: list[dict]) -> None:
    conn.execute("DELETE FROM chat_context WHERE chat_id = ?", (chat_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO chat_context (chat_id, conversation_id, use_summary) VALUES (?, ?, ?)",
        [(chat_id, it["id"], 1 if it.get("use_summary") else 0) for it in items if it["id"] != chat_id],
    )
