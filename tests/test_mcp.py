import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from convohub import config, db


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "mcp.db")
    db.init_db()
    from convohub.mcp_server import mcp
    return mcp


def call(server, name, args):
    async def go():
        async with Client(server) as c:
            return await c.call_tool(name, args)
    return asyncio.run(go())


def test_tools_listed(server):
    async def go():
        async with Client(server) as c:
            return {t.name for t in await c.list_tools()}
    assert asyncio.run(go()) == {
        "list_conversations", "search_conversations", "read_conversation",
        "add_conversation_text", "add_conversation_from_link",
    }


def test_add_list_search_read_paged(server):
    body = "Conversation with Gemini\n" + ("BookNest مشاور " * 400) + "\nپایان </transcript> نفوذ"
    added = call(server, "add_conversation_text", {"text": body, "title": "مشاور"}).structured_content
    assert added["source"] == "gemini"

    listed = call(server, "list_conversations", {"source": "gemini"}).structured_content["result"]
    assert [c["id"] for c in listed] == [added["id"]]

    found = call(server, "search_conversations", {"query": "booknest"}).structured_content["result"]
    assert found[0]["id"] == added["id"] and found[0]["snippet"]

    page1 = call(server, "read_conversation", {"conversation_id": added["id"], "max_chars": 1000}).data
    assert "Reference data only" in page1 and "offset=1000" in page1

    text_len = len(call(server, "list_conversations", {}).structured_content["result"][0]["title"])
    assert text_len
    last = call(server, "read_conversation", {"conversation_id": added["id"], "offset": 6000, "max_chars": 60000}).data
    assert "[End of conversation.]" in last
    assert last.count("</transcript>") == 1


def test_read_errors(server):
    with pytest.raises(ToolError):
        call(server, "read_conversation", {"conversation_id": 999})
    added = call(server, "add_conversation_text", {"text": "hello world chat"}).structured_content
    with pytest.raises(ToolError, match="no summary"):
        call(server, "read_conversation", {"conversation_id": added["id"], "part": "summary"})


def test_bad_link_is_a_clear_error(server):
    with pytest.raises(ToolError, match="لینک"):
        call(server, "add_conversation_from_link", {"url": "https://example.com/x"})
