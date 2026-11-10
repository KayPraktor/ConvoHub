"""Text helpers: cleaning pasted chats, detecting the source, normalizing Persian, token estimates."""

import re

# Lines that the AI apps add around a copied page. Matched on the whole (stripped) line.
_HEADER_LINES = {
    "conversation with gemini",
}
_FOOTER_PATTERNS = [
    re.compile(r"^gemini is ai and can make mistakes.*$", re.I),
    re.compile(r"^chatgpt can make mistakes.*$", re.I),
    re.compile(r"^claude (is ai and )?can make mistakes.*$", re.I),
    re.compile(r"^grok can make mistakes.*$", re.I),
]

_SOURCE_MARKERS = [
    ("gemini", re.compile(r"conversation with gemini|gemini is ai and can make mistakes|gemini\.google\.com", re.I)),
    ("chatgpt", re.compile(r"chatgpt can make mistakes|chatgpt\.com", re.I)),
    ("claude", re.compile(r"claude (is ai and )?can make mistakes|claude\.ai/", re.I)),
    ("grok", re.compile(r"grok can make mistakes|grok\.com", re.I)),
]

SOURCES = ("gemini", "claude", "grok", "chatgpt", "native", "other")


def clean_pasted(text: str) -> str:
    """Remove app chrome (header/footer lines) and squeeze blank lines. Content is kept as-is."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    lines = [ln.rstrip() for ln in text.split("\n")]

    while lines and (not lines[0].strip() or lines[0].strip().lower() in _HEADER_LINES):
        lines.pop(0)
    while lines and (not lines[-1].strip() or any(p.match(lines[-1].strip()) for p in _FOOTER_PATTERNS)):
        lines.pop()

    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def detect_source(text: str) -> str:
    head_and_tail = text[:2000] + "\n" + text[-2000:]
    for name, pattern in _SOURCE_MARKERS:
        if pattern.search(head_and_tail):
            return name
    return "other"


def guess_title(text: str, max_len: int = 60) -> str:
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.lower() in _HEADER_LINES:
            continue
        line = re.sub(r"https?://\S+", "", line).strip()
        if len(line) < 3:
            continue
        return line if len(line) <= max_len else line[: max_len - 1].rstrip() + "…"
    return "مکالمه‌ی بدون عنوان"


_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "‌": None, "‏": None, "‎": None})
_DIACRITICS = re.compile(r"[ً-ٰٟ]")


def normalize_for_search(text: str) -> str:
    """Make Persian/Arabic spelling variants and case match each other."""
    text = text.translate(_ARABIC_TO_PERSIAN)
    text = _DIACRITICS.sub("", text)
    return text.lower()


def estimate_tokens(text: str) -> int:
    """Rough token count. Latin text is ~4 chars/token, Persian is denser (~2.5 chars/token)."""
    if not text:
        return 0
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = len(text) - ascii_chars
    return int(ascii_chars / 4 + other / 2.5) + 1
