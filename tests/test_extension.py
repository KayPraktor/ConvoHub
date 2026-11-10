import pytest
from fastapi.testclient import TestClient

from convohub import config
from convohub.importers.extension import canonical, merge

EXT = {"X-ConvoHub-Client": "extension"}
URL = "https://gemini.google.com/app/abc123?hl=fa#x"


def msgs(*pairs):
    return [{"role": r, "content": c} for r, c in pairs]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ext.db")
    from convohub.main import app
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("url,expected", [
    ("https://gemini.google.com/app/abc123?hl=fa", ("gemini", "https://gemini.google.com/app/abc123")),
    ("https://gemini.google.com/u/1/app/abc123", ("gemini", "https://gemini.google.com/u/1/app/abc123")),
    ("https://chatgpt.com/c/6789-ab", ("chatgpt", "https://chatgpt.com/c/6789-ab")),
    ("https://chatgpt.com/g/g-xyz-mygpt/c/6789", ("chatgpt", "https://chatgpt.com/g/g-xyz-mygpt/c/6789")),
    ("https://claude.ai/chat/1234-abcd", ("claude", "https://claude.ai/chat/1234-abcd")),
    ("https://grok.com/c/xyz", ("grok", "https://grok.com/c/xyz")),
    ("https://gemini.google.com/app", None),
    ("http://chatgpt.com/c/1", None),
    ("https://evil.com/app/1", None),
])
def test_canonical(url, expected):
    assert canonical(url) == expected


def test_merge_appends_new_turns_from_a_partial_page():
    old = msgs(("user", "q1"), ("assistant", "a1"), ("user", "q2"), ("assistant", "a2"))
    # The page only has the latest turns loaded, plus one new exchange.
    page = msgs(("user", "q2"), ("assistant", "a2"), ("user", "q3"), ("assistant", "a3"))
    merged, mode = merge(old, page)
    assert mode == "appended" and [m["content"] for m in merged] == ["q1", "a1", "q2", "a2", "q3", "a3"]


def test_merge_finishes_a_partial_answer():
    long = "x" * 250
    old = msgs(("user", "q"), ("assistant", long))  # stored while still being written
    page = msgs(("user", "q"), ("assistant", long + " and the rest"))
    merged, mode = merge(old, page)
    assert mode == "appended" and merged[-1]["content"].endswith("the rest") and len(merged) == 2


def test_merge_unchanged_and_unaligned():
    old = msgs(("user", "q"), ("assistant", "a"))
    assert merge(old, list(old))[1] == "unchanged"
    assert merge(old, msgs(("user", "other"), ("assistant", "thing")))[1] == "unaligned"


def test_sync_creates_then_appends(client):
    first = client.post("/api/extension/sync", headers=EXT, json={
        "url": URL, "title": "مشاور", "messages": msgs(("user", "q1"), ("assistant", "a1")), "full": True}).json()
    assert first["mode"] == "created" and first["total"] == 2

    status = client.get("/api/extension/status", headers=EXT, params={"url": "https://gemini.google.com/app/abc123"}).json()
    assert status["known"] and status["messages"] == 2

    again = client.post("/api/extension/sync", headers=EXT, json={
        "url": URL, "messages": msgs(("assistant", "a1"), ("user", "q2"), ("assistant", "a2"))}).json()
    assert again == {"id": first["id"], "mode": "appended", "added": 2, "total": 4}

    conv = client.get(f"/api/conversations/{first['id']}").json()
    assert conv["import_method"] == "extension" and conv["source"] == "gemini"
    assert [m["content"] for m in conv["messages"]] == ["q1", "a1", "q2", "a2"]
    assert "User:\nq2" in conv["raw_text"]


def test_full_sync_replaces_when_unaligned(client):
    client.post("/api/extension/sync", headers=EXT, json={"url": URL, "messages": msgs(("user", "old"), ("assistant", "x"))})
    res = client.post("/api/extension/sync", headers=EXT, json={
        "url": URL, "messages": msgs(("user", "edited"), ("assistant", "y")), "full": True}).json()
    assert res["mode"] == "replaced"
    partial = client.post("/api/extension/sync", headers=EXT, json={
        "url": URL, "messages": msgs(("user", "zzz"), ("assistant", "w"))}).json()
    assert partial["mode"] == "unaligned"  # an automatic sync never overwrites what it can't align


def test_extension_endpoints_need_the_header(client):
    assert client.get("/api/extension/status", params={"url": URL}).status_code == 403
    assert client.post("/api/extension/sync", json={"url": URL, "messages": []}).status_code == 403


def test_other_websites_are_kept_out(client):
    # A page on another site can't make the browser change things here...
    res = client.post("/api/import/paste", json={"text": "injected"}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403
    res = client.put("/api/agent/settings", json={"allowed_folders": []}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403
    # ...nor point its own domain at 127.0.0.1 (DNS rebinding).
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    # Only the paired extension, and only on its own endpoints.
    mine = {"Origin": "chrome-extension://abcdefghijklmnop", **EXT}
    other = {"Origin": "chrome-extension://zzzzzzzzzzzzzzzz", **EXT}
    body = {"url": URL, "messages": msgs(("user", "q"), ("assistant", "a"))}
    first = client.post("/api/extension/sync", headers=mine, json=body)
    assert first.status_code == 403 and first.json()["unpaired"]
    assert client.get("/api/settings/extension").json() == {"paired": None, "pending": "abcdefghijklmnop"}
    paired = client.put("/api/settings/extension", json={"id": "abcdefghijklmnop"},
                        headers={"Origin": f"http://127.0.0.1:{config.PORT}"})
    assert paired.json() == {"paired": "abcdefghijklmnop", "pending": None}
    assert client.post("/api/extension/sync", headers=mine, json=body).status_code == 200
    assert client.post("/api/extension/sync", headers=other, json=body).status_code == 403
    assert client.post("/api/import/paste", json={"text": "x"}, headers=mine).status_code == 403
    # Another extension can't pair itself: pairing endpoints refuse non-ConvoHub origins.
    assert client.put("/api/settings/extension", json={"id": "zzzzzzzzzzzzzzzz"}, headers=other).status_code == 403
    # ConvoHub's own page still works.
    own = client.post("/api/import/paste", json={"text": "hello there"},
                      headers={"Origin": f"http://127.0.0.1:{config.PORT}"})
    assert own.status_code == 200
