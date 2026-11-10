"""Parse uploaded files into one or more conversations.

Supported:
- .txt / .md: one conversation, treated like a paste.
- ChatGPT export (conversations.json): list of objects with a "mapping" tree.
- Claude export (conversations.json): list of objects with "chat_messages".
"""

import json
from dataclasses import dataclass, field

from .. import library
from ..text import clean_pasted, detect_source, guess_title

MAX_FILE_BYTES = 200 * 1024 * 1024


class ImportFileError(Exception):
    pass


@dataclass
class ParsedConversation:
    title: str
    source: str
    raw_text: str
    messages: list[dict] = field(default_factory=list)


def parse_file(filename: str, data: bytes) -> list[ParsedConversation]:
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError("فایل خیلی بزرگه (بیشتر از ۲۰۰ مگابایت).")
    text = _decode(data)
    name = filename.lower()

    if name.endswith(".json"):
        try:
            obj = json.loads(text)
        except ValueError as exc:
            raise ImportFileError("فایل JSON خرابه یا کامل نیست.") from exc
        convs = _parse_chatgpt(obj) or _parse_claude(obj)
        if convs is None:
            raise ImportFileError("این فرمت JSON رو نمی‌شناسم. فعلاً خروجی ChatGPT و Claude پشتیبانی میشه.")
        if not convs:
            raise ImportFileError("توی فایل مکالمه‌ای پیدا نشد.")
        return convs

    if name.endswith((".txt", ".md", ".markdown")):
        cleaned = clean_pasted(text)
        if not cleaned:
            raise ImportFileError("فایل خالیه.")
        stem = filename.rsplit(".", 1)[0]
        return [ParsedConversation(title=stem or guess_title(cleaned), source=detect_source(text), raw_text=cleaned)]

    raise ImportFileError("فرمت فایل پشتیبانی نمیشه. فایل .txt، .md یا .json بده.")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("cp1256", errors="replace")  # old Windows Persian/Arabic encoding


def _finish(title: str, source: str, messages: list[dict]) -> ParsedConversation:
    messages = [m for m in messages if m["content"].strip()]
    return ParsedConversation(
        title=(title or "").strip() or "مکالمه‌ی بدون عنوان",
        source=source,
        raw_text=library.render_messages(messages),
        messages=messages,
    )


def _parse_chatgpt(obj) -> list[ParsedConversation] | None:
    if isinstance(obj, dict):
        obj = [obj]
    if not isinstance(obj, list) or not obj or not all(isinstance(c, dict) and "mapping" in c for c in obj):
        return None
    out = []
    for conv in obj:
        mapping = conv.get("mapping") or {}
        # Walk from current_node back to the root: that is the branch the user last saw.
        node_id, chain = conv.get("current_node"), []
        while node_id and node_id in mapping:
            chain.append(mapping[node_id])
            node_id = mapping[node_id].get("parent")
        messages = []
        for node in reversed(chain):
            msg = node.get("message") or {}
            role = (msg.get("author") or {}).get("role")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content") or {}
            parts = content.get("parts") or []
            text = "\n".join(p for p in parts if isinstance(p, str))
            if text.strip():
                messages.append({"role": role, "content": text})
        out.append(_finish(conv.get("title"), "chatgpt", messages))
    return [c for c in out if c.messages]


def _parse_claude(obj) -> list[ParsedConversation] | None:
    if isinstance(obj, dict):
        obj = [obj]
    if not isinstance(obj, list) or not obj or not all(isinstance(c, dict) and "chat_messages" in c for c in obj):
        return None
    out = []
    for conv in obj:
        messages = []
        for m in conv.get("chat_messages") or []:
            role = {"human": "user", "assistant": "assistant"}.get(m.get("sender"))
            if not role:
                continue
            text = m.get("text") or ""
            if not text and isinstance(m.get("content"), list):
                text = "\n".join(b.get("text", "") for b in m["content"] if isinstance(b, dict))
            messages.append({"role": role, "content": text})
        out.append(_finish(conv.get("name"), "claude", messages))
    return [c for c in out if c.messages]
