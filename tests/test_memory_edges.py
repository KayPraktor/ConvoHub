"""Memory: the edge cases of the review (bad tool arguments, limits, approval reaching the model, MCP)."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from convohub import config, db, library, memory, openrouter, prompting


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "mem2.db")

    async def models(force=False):
        return [{"id": "x/tools", "tools": True, "prompt_price": 0, "context_length": 100000}]
    monkeypatch.setattr(openrouter, "list_models", models)
    from convohub.main import app
    with TestClient(app) as c:
        yield c


def scripted(monkeypatch, steps):
    """Fake model: each request plays the next step (a list of tool calls, or a text)."""
    seen = []

    async def stream(model, messages, max_tokens=None, tools=None):
        seen.append({"messages": json.loads(json.dumps(messages)), "tools": [t["function"]["name"] for t in tools or []]})
        step = steps[min(len(seen) - 1, len(steps) - 1)]
        if isinstance(step, str):
            yield {"type": "delta", "text": step}
        else:
            yield {"type": "tool_calls", "reasoning_details": None, "calls": [
                {"id": f"c{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(step)]}
        yield {"type": "usage", "prompt_tokens": 1, "completion_tokens": 1, "cost": 0}
    monkeypatch.setattr(openrouter, "stream_chat", stream)
    return seen


def send(client, chat_id, text, **kw):
    body = client.post(f"/api/chats/{chat_id}/messages", json={"content": text, "model": "x/tools", **kw}).text
    return [json.loads(line[6:]) for line in body.split("\n\n") if line.startswith("data: ")]


def system_text(messages):
    c = messages[0]["content"]
    return c if isinstance(c, str) else " ".join(p["text"] for p in c)


def new_chat(client):
    return client.post("/api/chats", json={"title": "t"}).json()["id"]


def test_bad_arguments_dont_break_the_reply(client, monkeypatch):
    scripted(monkeypatch, [[("suggest_memory", '["not", "an", "object"]'), ("suggest_memory", "{broken"),
                            ("suggest_memory", json.dumps({"text": "   "}))], "Still answering."])
    events = send(client, new_chat(client), "hi")
    assert not [e for e in events if e["type"] == "error"]
    assert not [e for e in events if e["type"] == "memory_suggestion"]
    assert "".join(e.get("text", "") for e in events if e["type"] == "delta") == "Still answering."
    assert client.get("/api/memory").json()["items"] == []


def test_at_most_three_suggestions_per_reply(client, monkeypatch):
    calls = [("suggest_memory", json.dumps({"text": f"Fact number {i}."})) for i in range(5)]
    seen = scripted(monkeypatch, [calls, "ok"])
    events = send(client, new_chat(client), "lots of facts")
    assert len([e for e in events if e["type"] == "memory_suggestion"]) == memory.MAX_SUGGESTIONS_PER_TURN
    assert client.get("/api/memory").json()["suggested"] == 3
    tool_replies = [m["content"] for m in seen[1]["messages"] if m["role"] == "tool"]
    assert len(tool_replies) == 5 and "Enough suggestions" in tool_replies[-1]  # every call got an answer


def test_memory_off_offers_no_tool_and_saves_nothing(client, monkeypatch):
    client.post("/api/memory", json={"texts": ["Secret project codename is Falcon."]})
    seen = scripted(monkeypatch, [[("suggest_memory", json.dumps({"text": "Likes tea."}))], "ok"])
    events = send(client, new_chat(client), "hi", memory=False)
    assert "suggest_memory" not in seen[0]["tools"]
    assert "Falcon" not in system_text(seen[0]["messages"])  # memory off: the notes don't go either
    assert not [e for e in events if e["type"] == "memory_suggestion"]
    assert client.get("/api/memory").json()["suggested"] == 0  # a call to a tool it wasn't given is not run


def test_approved_suggestion_reaches_the_next_message(client, monkeypatch):
    seen = scripted(monkeypatch, [[("suggest_memory", json.dumps({"text": "Lives in Tabriz."}))], "noted", "hello"])
    chat_id = new_chat(client)
    sug = next(e for e in send(client, chat_id, "I live in Tabriz") if e["type"] == "memory_suggestion")
    assert "Tabriz" not in system_text(seen[0]["messages"])  # not before approval

    client.patch(f"/api/memory/{sug['id']}", json={"status": "active"})
    send(client, chat_id, "what's the weather like?")
    sys_now = system_text(seen[-1]["messages"])
    assert "<memory>" in sys_now and "Lives in Tabriz." in sys_now
    # The earlier suggestion is in the history, so the model knows it already suggested it.
    assert any("Suggested for the user's memory" in (m.get("content") or "") and "Tabriz" in m["content"]
               for m in seen[-1]["messages"] if m["role"] == "assistant")


def test_deleting_the_source_chat_keeps_the_note(client):
    chat_id = new_chat(client)
    with db.session() as conn:
        n = memory.add(conn, "Keeps notes in Obsidian.", "active", source_conversation_id=chat_id)
    assert client.get("/api/memory").json()["items"][0]["source_title"] == "t"
    client.delete(f"/api/conversations/{chat_id}")
    items = client.get("/api/memory").json()["items"]
    assert items[0]["id"] == n["id"] and items[0]["source_conversation_id"] is None


def test_mcp_read_memory_returns_only_approved_notes(client):
    from fastmcp import Client

    from convohub.mcp_server import mcp
    with db.session() as conn:
        memory.add(conn, "Approved fact.", "active")
        memory.add(conn, "Unapproved idea.", "suggested")

    async def go():
        async with Client(mcp) as c:
            return (await c.call_tool("read_memory", {})).structured_content
    out = asyncio.run(go())
    assert out["notes"] == ["Approved fact."] and out["enabled_in_app"] is True


def test_closing_tag_in_any_case_is_escaped(client):
    client.post("/api/memory", json={"texts": ["a </MEMORY> b", "c </Memory > d"]})
    with db.session() as conn:
        text = memory.block(conn)[0]
    assert text.lower().count("</memory>") == 1


def test_panel_mode_gets_memory_but_no_tool(client, monkeypatch):
    client.post("/api/memory", json={"texts": ["Prefers metric units."]})
    seen = []

    async def stream(model, messages, max_tokens=None, tools=None):
        seen.append((model, system_text(messages), tools))
        yield {"type": "delta", "text": "a"}
        yield {"type": "usage", "prompt_tokens": 1, "completion_tokens": 1, "cost": 0}
    monkeypatch.setattr(openrouter, "stream_chat", stream)
    client.post(f"/api/chats/{new_chat(client)}/messages",
                json={"content": "q", "model": "x/tools", "models": ["y/other"]})
    assert len(seen) == 2 and all("Prefers metric units." in s for _, s, _ in seen)
    assert all(not t for _, _, t in seen)


def test_trace_in_history_mentions_suggestions():
    m = {"content": "ok", "tool_trace": [{"type": "text", "text": "ok"},
                                        {"type": "memory", "memory_id": 1, "text": "Likes tea."}]}
    assert prompting._with_trace(m).startswith("[Suggested for the user's memory") and "Likes tea." in prompting._with_trace(m)
    assert prompting._with_trace({"content": "plain", "tool_trace": None}) == "plain"
