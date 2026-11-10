import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from convohub import config, db, library, openrouter, panel, prompting


def fake_stream(answers: dict, fail: set = frozenset()):
    seen = []

    async def stream_chat(model, messages, max_tokens=None, tools=None):
        seen.append((model, json.loads(json.dumps(messages))))
        if model in fail:
            raise openrouter.OpenRouterError("down")
        for word in answers[model].split(" "):
            await asyncio.sleep(0)
            yield {"type": "delta", "text": word + " "}
        yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 3, "cost": 0.01}

    return stream_chat, seen


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "panel.db")
    from convohub.main import app
    with TestClient(app) as c:
        yield c


def sse(res):
    return [json.loads(line[5:]) for line in res.text.split("\n\n") if line.startswith("data:")]


def test_panel_runs_models_in_parallel_and_synthesizes(client, monkeypatch):
    stream, seen = fake_stream({"a/x": "answer from x", "b/y": "answer from y", "o/z": "combined"})
    monkeypatch.setattr(openrouter, "stream_chat", stream)
    chat = client.post("/api/chats", json={}).json()["id"]

    events = sse(client.post(f"/api/chats/{chat}/messages",
                             json={"content": "q1", "model": "a/x", "models": ["b/y"], "orchestrator": "o/z"}))
    assert events[0] == {"type": "panel_start", "models": ["a/x", "b/y"], "orchestrator": "o/z"}
    by_slot = {}
    for e in events:
        if e["type"] == "delta":
            by_slot[e["slot"]] = by_slot.get(e["slot"], "") + e["text"]
    assert by_slot == {0: "answer from x ", 1: "answer from y ", "s": "combined "}
    assert events[-1]["type"] == "done" and abs(events[-1]["usage"]["cost"] - 0.03) < 1e-9

    # The orchestrator saw both answers.
    synth_prompt = seen[-1][1][-1]["content"]
    assert seen[-1][0] == "o/z" and "answer from x" in synth_prompt and "answer from y" in synth_prompt

    msgs = client.get(f"/api/chats/{chat}").json()["messages"]
    assert [(m["role"], m["kind"], m["model"]) for m in msgs] == [
        ("user", None, None), ("assistant", "panel", "a/x"), ("assistant", "panel", "b/y"),
        ("assistant", "synthesis", "o/z")]

    # Next turn: every model sees all earlier answers in one assistant turn.
    with db.session() as conn:
        built = prompting.build_messages(conn, chat, "a/x", "q2")
    assert [m["role"] for m in built] == ["system", "user", "assistant", "user"]
    assert "Answer by a/x" in built[2]["content"] and "Answer by b/y" in built[2]["content"]
    assert "synthesis) by o/z" in built[2]["content"]


def test_one_failing_model_does_not_stop_the_others(client, monkeypatch):
    stream, _ = fake_stream({"a/x": "fine"}, fail={"b/y"})
    monkeypatch.setattr(openrouter, "stream_chat", stream)
    chat = client.post("/api/chats", json={}).json()["id"]
    events = sse(client.post(f"/api/chats/{chat}/messages", json={"content": "q", "model": "a/x", "models": ["b/y"]}))
    done = {e["slot"]: e for e in events if e["type"] == "slot_done"}
    assert done[0]["error"] is None and done[1]["error"] == "down"
    msgs = client.get(f"/api/chats/{chat}").json()["messages"]
    assert [(m["kind"], m["model"]) for m in msgs if m["role"] == "assistant"] == [("panel", "a/x")]


def test_too_many_models(client):
    chat = client.post("/api/chats", json={}).json()["id"]
    res = client.post(f"/api/chats/{chat}/messages",
                      json={"content": "q", "model": "a", "models": ["b", "c", "d", "e"]})
    assert res.status_code in (400, 422)


def test_render_labels_panel_answers():
    text = library.render_messages([
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "x", "kind": "panel", "model": "a/x"},
        {"role": "assistant", "content": "z", "kind": "synthesis", "model": "o/z"},
    ])
    assert "Assistant (a/x):\nx" in text and "Synthesis (o/z):\nz" in text
