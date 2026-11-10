"""Shared import steps used by the web API and the MCP server."""

from .. import library
from ..text import SOURCES, clean_pasted, detect_source, guess_title
from .links import LinkResult


def import_text(conn, text: str, title: str | None = None, source: str | None = None) -> int:
    """Save pasted text as a conversation. Raises ValueError if it is empty."""
    cleaned = clean_pasted(text)
    if not cleaned:
        raise ValueError("متن خالیه.")
    if not (source in SOURCES and source != "native"):
        source = detect_source(text)
    return library.create_conversation(
        conn, title=(title or "").strip() or guess_title(cleaned), source=source,
        import_method="paste", raw_text=cleaned,
    )


def save_link(conn, result: LinkResult) -> int:
    return library.create_conversation(
        conn, title=result.title or guess_title(result.raw_text), source=result.source,
        import_method="link", source_url=result.url, raw_text=result.raw_text, messages=result.messages,
    )
