"""Conversations sent by the browser extension, from the chat page the user has open in their own browser.

The extension only reads the page DOM (no cookies, tokens or private endpoints; CLAUDE.md hard constraint #1).
The same conversation is sent again whenever new messages appear, so we merge instead of duplicating.
"""

import re
from urllib.parse import urlparse

from .. import handoff, library
from ..text import guess_title

# host, path regex (must capture the whole conversation path), source
_PATTERNS = [
    (r"gemini\.google\.com", r"^(/u/\d+)?/app/[\w-]+", "gemini"),
    (r"(www\.)?chatgpt\.com", r"^(/g/[\w-]+)?/c/[\w-]+", "chatgpt"),
    (r"(www\.)?claude\.ai", r"^/chat/[\w-]+", "claude"),
    (r"(www\.)?grok\.com", r"^/(c|chat)/[\w-]+", "grok"),
]


class SyncError(ValueError):
    pass


def canonical(url: str) -> tuple[str, str] | None:
    """(source, canonical url) for a supported conversation page; query and fragment dropped."""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return None
    if p.scheme != "https":
        return None
    for host, path, source in _PATTERNS:
        if re.fullmatch(host, p.hostname or ""):
            m = re.match(path, p.path)
            if m:
                return source, f"https://{p.hostname}{m.group(0)}"
    return None


def _key(m: dict) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", m["content"]).strip()
    return m["role"], text[:200]


def merge(old: list[dict], new: list[dict]) -> tuple[list[dict], str]:
    """Merge a fresh read of the page into what we stored.

    Pages often hold only the latest turns (older ones load when you scroll up), and the last answer may
    have been stored while it was still being written. So we find where the stored history ends inside the
    new read and append from there. Returns (messages, mode): mode is unchanged / appended / unaligned.
    """
    if not old:
        return new, "appended" if new else "unchanged"
    if not new:
        return old, "unchanged"
    old_keys = [_key(m) for m in old]
    new_keys = [_key(m) for m in new]

    # Find the stored last message in the new read (search from the end: the most recent match).
    for i in range(len(new) - 1, -1, -1):
        if new_keys[i] != old_keys[-1]:
            continue
        if len(old) >= 2 and i >= 1 and new_keys[i - 1] != old_keys[-2]:
            continue  # same text in two places; require the one before to match too
        merged = old[:-1] + new[i:]  # new[i] may be the finished version of a partial answer
        changed = len(merged) != len(old) or merged[len(old) - 1]["content"] != old[-1]["content"]
        return merged, "appended" if changed else "unchanged"
    return old, "unaligned"


def sync(conn, url: str, title: str | None, messages: list[dict], full: bool) -> dict:
    """Create or update the conversation for this page.

    full=True means the extension loaded the whole history (the user pressed the button): if it can't be
    aligned with what we have, the page wins.
    """
    found = canonical(url)
    if not found:
        raise SyncError("این صفحه یه مکالمه‌ی پشتیبانی‌شده نیست.")
    source, curl = found
    messages = [{"role": m["role"], "content": m["content"].strip()} for m in messages
                if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    for m in messages:  # a handoff pasted from ConvoHub: don't store its content twice
        if m["role"] == "user":
            m["content"] = handoff.compact(m["content"])
    if not messages:
        raise SyncError("پیامی توی صفحه پیدا نشد.")

    row = conn.execute(
        "SELECT id FROM conversations WHERE source_url = ? AND import_method = 'extension'", (curl,)
    ).fetchone()
    if not row:
        conv_id = library.create_conversation(
            conn, title=(title or "").strip() or guess_title(messages[0]["content"]), source=source,
            import_method="extension", source_url=curl, raw_text=library.render_messages(messages),
            messages=messages,
        )
        return {"id": conv_id, "mode": "created", "added": len(messages), "total": len(messages)}

    conv_id = row["id"]
    old = [{"role": m["role"], "content": m["content"]} for m in library.get_messages(conn, conv_id)]
    merged, mode = merge(old, messages)
    if mode == "unaligned" and full:
        merged, mode = messages, "replaced"
    if mode in ("appended", "replaced"):
        library.replace_content(conn, conv_id, library.render_messages(merged), merged)
    return {"id": conv_id, "mode": mode, "added": max(0, len(merged) - len(old)), "total": len(merged)}


def status(conn, url: str) -> dict:
    found = canonical(url)
    if not found:
        return {"supported": False, "known": False}
    row = conn.execute(
        "SELECT c.id, c.title, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS n "
        "FROM conversations c WHERE c.source_url = ? AND c.import_method = 'extension'", (found[1],)
    ).fetchone()
    return {"supported": True, "known": bool(row), "id": row["id"] if row else None,
            "title": row["title"] if row else None, "messages": row["n"] if row else 0}
