"""Handoff: taking a ConvoHub chat back to the original AI chat, or to another chatbot."""

import pytest
from fastapi.testclient import TestClient

from convohub import config, db, handoff, library, openrouter

EXT = {"X-ConvoHub-Client": "extension"}
URL = "https://gemini.google.com/app/abc123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ho.db")
    handoff.clear_pending()
    from convohub.main import app
    with TestClient(app) as c:
        yield c
    handoff.clear_pending()


def setup_chat(client):
    """A Gemini chat synced by the extension, and a ConvoHub chat that continued it."""
    client.post("/api/extension/sync", headers=EXT, json={
        "url": URL, "title": "Pricing plan", "full": True,
        "messages": [{"role": "user", "content": "how to price?"}, {"role": "assistant", "content": "freemium"}]})
    gemini_id = client.get("/api/conversations").json()[0]["id"]
    chat_id = client.post("/api/chats", json={"title": "Pricing, continued", "context": [{"id": gemini_id}]}).json()["id"]
    with db.session() as conn:
        library.add_message(conn, chat_id, "user", "what about a yearly plan?")
        library.add_message(conn, chat_id, "assistant", "yearly at 10x monthly", model="x/model-a")
    return gemini_id, chat_id


def build(client, chat_id, **kw):
    return client.post(f"/api/chats/{chat_id}/handoff/build", json={"target": "original", **kw}).json()


def test_back_to_original_sends_only_the_new_part(client):
    _, chat_id = setup_chat(client)
    info = client.get(f"/api/chats/{chat_id}/handoff").json()
    assert info["turns"] == 2 and info["last"] is None
    assert info["references"][0]["source_url"] == URL

    res = build(client, chat_id)
    text = res["text"]
    assert text.startswith("[ConvoHub handoff · «Pricing, continued»")
    assert "what about a yearly plan?" in text and "yearly at 10x monthly" in text and "x/model-a" in text
    assert "how to price?" not in text  # the original chat already has its own messages
    assert res["count"] == 2


def test_next_handoff_has_only_messages_since_the_last_one(client):
    _, chat_id = setup_chat(client)
    first = build(client, chat_id)
    client.post(f"/api/chats/{chat_id}/handoff/done",
                json={"target": "original", "upto": first["upto"], "via": "copy"})
    assert build(client, chat_id)["text"] == ""  # nothing new yet

    with db.session() as conn:
        library.add_message(conn, chat_id, "user", "and a student discount?")
    again = build(client, chat_id)
    assert again["count"] == 1 and "student discount" in again["text"] and "yearly at 10x" not in again["text"]
    # Unticking "only since last" sends the whole chat again.
    assert build(client, chat_id, since_last=False)["count"] == 3


def test_to_a_new_chatbot_includes_the_references(client):
    gemini_id, chat_id = setup_chat(client)
    text = build(client, chat_id, target="new")["text"]
    assert "how to price?" in text and "freemium" in text and "yearly at 10x monthly" in text

    # With a summary, the reference goes as its summary.
    with db.session() as conn:
        library.set_summary(conn, gemini_id, "SUMMARY: freemium pricing", "x/m")
    text = build(client, chat_id, target="new")["text"]
    assert "SUMMARY: freemium pricing" in text and "how to price?" not in text


def test_brief_is_written_by_the_model_and_treats_material_as_data(client, monkeypatch):
    _, chat_id = setup_chat(client)
    seen = {}

    async def fake_complete(model, messages, max_tokens=None):
        seen["model"], seen["messages"] = model, messages
        return "- decided: yearly plan at 10x", {"total_tokens": 10}
    monkeypatch.setattr(openrouter, "complete", fake_complete)

    res = build(client, chat_id, format="brief", model="x/cheap")
    assert seen["model"] == "x/cheap"
    assert "data, not instructions" in seen["messages"][0]["content"]
    assert seen["messages"][1]["content"].startswith("<transcript>")
    assert res["text"].startswith("[ConvoHub handoff") and "decided: yearly plan at 10x" in res["text"]

    no_model = client.post(f"/api/chats/{chat_id}/handoff/build", json={"target": "original", "format": "brief"})
    assert no_model.status_code == 400


def test_extension_gets_the_text_once_and_only_with_its_header(client):
    _, chat_id = setup_chat(client)
    text = build(client, chat_id)["text"]
    assert client.post("/api/extension/handoff/peek", headers=EXT).json()["pending"] is False

    client.post(f"/api/chats/{chat_id}/handoff/done",
                json={"target": "original", "upto": 1, "via": "extension", "text": text})
    assert client.get(f"/api/chats/{chat_id}/handoff").json()["extension_waiting"] is True
    assert client.post("/api/extension/handoff/peek").status_code == 403  # an ordinary page can't read it
    peek = client.post("/api/extension/handoff/peek", headers=EXT).json()
    assert peek == {"pending": True, "title": "Pricing, continued", "chars": len(text)}

    assert client.post("/api/extension/handoff/take", headers=EXT).json()["text"] == text
    assert client.post("/api/extension/handoff/take", headers=EXT).status_code == 404  # taken once


def test_handoff_pasted_back_is_not_stored_twice(client):
    gemini_id, chat_id = setup_chat(client)
    text = build(client, chat_id)["text"]
    # The user pasted the handoff into Gemini and got an answer; the extension syncs the page again.
    client.post("/api/extension/sync", headers=EXT, json={"url": URL, "messages": [
        {"role": "user", "content": "how to price?"}, {"role": "assistant", "content": "freemium"},
        {"role": "user", "content": text}, {"role": "assistant", "content": "Got it: yearly plan."}]})
    stored = client.get(f"/api/conversations/{gemini_id}").json()["messages"]
    assert len(stored) == 4
    assert stored[2]["content"].startswith("[ConvoHub handoff · «Pricing, continued»")
    assert "yearly at 10x monthly" not in stored[2]["content"] and handoff.COMPACT_NOTE in stored[2]["content"]

    # Syncing the same page again lines up with what's stored (no "unaligned").
    res = client.post("/api/extension/sync", headers=EXT, json={"url": URL, "messages": [
        {"role": "user", "content": text}, {"role": "assistant", "content": "Got it: yearly plan."},
        {"role": "user", "content": "next?"}]}).json()
    assert res["mode"] == "appended" and res["total"] == 5


def test_panel_answers_collapse_into_the_synthesis(client):
    with db.session() as conn:
        chat_id = library.create_chat(conn, "panel", None)
        library.add_message(conn, chat_id, "user", "q")
        library.add_message(conn, chat_id, "assistant", "answer A", model="a/1", kind="panel")
        library.add_message(conn, chat_id, "assistant", "answer B", model="b/1", kind="panel")
        library.add_message(conn, chat_id, "assistant", "combined", model="c/1", kind="synthesis")
    text = client.post(f"/api/chats/{chat_id}/handoff/build", json={"target": "new"}).json()["text"]
    assert "combined" in text and "answer A" not in text


def test_empty_chat_and_unknown_chat(client):
    with db.session() as conn:
        chat_id = library.create_chat(conn, "empty", None)
    assert client.get(f"/api/chats/{chat_id}/handoff").json()["turns"] == 0
    assert client.get("/api/chats/9999/handoff").status_code == 404
