"""The extension's and the link importer's ChatGPT rules against a copy of ChatGPT's 2026 page structure.

Runs in the local Chrome (headless); the page is served by request interception, nothing goes to chatgpt.com.
"""

from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from convohub.importers import links  # noqa: E402

EXTRACT_JS = (Path(__file__).parent.parent / "extension" / "extract.js").read_text(encoding="utf-8")

PAGE = """<!doctype html><html><head><title>Test chat</title></head><body>
<main><ol data-conversation-transcript>
  <li data-message-role="user"><div data-user-message-bubble><p data-user-message-copy>سؤال اول</p></div>
    <button aria-label="copy">کپی</button></li>
  <li data-message-role="assistant">
    <h4 aria-label="ChatGPT گفت:">ChatGPT گفت:</h4>
    <div data-cot><span data-cot-label>Worked for 9s</span></div>
    <div data-assistant-markdown-root><p>جواب اول <button>Source Chip</button></p><p>ادامه</p></div>
    <div data-message-actions><button>کپی کردن پاسخ</button></div>
  </li>
  <li data-message-role="user"><div data-user-message-bubble><p>سؤال دوم</p></div></li>
  <li data-message-role="assistant"><div data-assistant-markdown-root><p>جواب دوم</p></div></li>
</ol></main></body></html>"""


def _open(url):
    pw = playwright.sync_playwright().start()
    try:
        browser = pw.chromium.launch(channel="chrome", headless=True)
    except Exception:
        pw.stop()
        pytest.skip("Chrome not available")
    page = browser.new_page()
    page.route("https://chatgpt.com/**", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8",
                                                            body=PAGE))
    page.goto(url)
    return pw, browser, page


def test_extension_reads_new_chatgpt_layout():
    pw, browser, page = _open("https://chatgpt.com/c/test-1")
    try:
        page.evaluate(EXTRACT_JS)
        data = page.evaluate("window.convohubExtract.extract()")
    finally:
        browser.close()
        pw.stop()
    assert data["source"] == "chatgpt"
    assert [(m["role"], m["content"]) for m in data["messages"]] == [
        ("user", "سؤال اول"), ("assistant", "جواب اول\n\nادامه"), ("user", "سؤال دوم"), ("assistant", "جواب دوم")]


def test_link_importer_reads_new_chatgpt_layout():
    pw, browser, page = _open("https://chatgpt.com/share/test-1")
    try:
        data = page.evaluate(links._EXTRACT_JS)
    finally:
        browser.close()
        pw.stop()
    assert [m["role"] for m in data["messages"]] == ["user", "assistant", "user", "assistant"]
    joined = "\n".join(m["content"] for m in data["messages"])
    for noise in ("Worked for", "Source Chip", "کپی", "ChatGPT گفت"):
        assert noise not in joined


SHADOW_PAGE = """<!doctype html><html><head><title>Shadow chat</title></head><body><chat-thread></chat-thread>
<script>
  const host = document.querySelector('chat-thread');
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = '<ol data-conversation-transcript>' +
    '<li data-message-role="user"><div data-user-message-bubble>سلام از داخل shadow</div></li>' +
    '<li data-message-role="assistant"><div data-assistant-markdown-root><p>جواب</p></div></li></ol>';
</script></body></html>"""


def test_extension_reads_messages_inside_shadow_dom():
    pw = playwright.sync_playwright().start()
    try:
        browser = pw.chromium.launch(channel="chrome", headless=True)
    except Exception:
        pw.stop()
        pytest.skip("Chrome not available")
    try:
        page = browser.new_page()
        page.route("https://chatgpt.com/**", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8",
                                                                body=SHADOW_PAGE))
        page.goto("https://chatgpt.com/c/shadow-1")
        page.evaluate(EXTRACT_JS)
        data = page.evaluate("window.convohubExtract.extract()")
        report = page.evaluate("window.convohubExtract.diagnose()")
    finally:
        browser.close()
        pw.stop()
    assert [m["role"] for m in data["messages"]] == ["user", "assistant"]
    assert report["shadowRoots"] == 1 and report["matches"]["user"] >= 1 and report["matches"]["assistant"] >= 1
    assert "data-message-role=user" in report["roleLikeValues"]
    assert "سلام" not in str(report)  # structure only, never message text


def test_diagnose_report_is_saved(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from convohub import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "d.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    from convohub.main import app
    with TestClient(app) as c:
        res = c.post("/api/extension/diagnose", json={"host": "chatgpt.com", "matches": {"user": 0}},
                     headers={"X-ConvoHub-Client": "extension"})
    assert res.status_code == 200
    assert '"host": "chatgpt.com"' in (tmp_path / "extension-diagnose.json").read_text(encoding="utf-8")


# The logged-in ChatGPT app (seen 2026-11-10): no data-message-role; a hidden h4 label per turn, the user
# bubble, and the answer in [data-markdown-text-style="assistant-message"] with source chips inside.
APP_PAGE = """<!doctype html><html><head><title>Chat - ChatGPT</title></head><body><main>
<div data-content-search-unit-key="fallback-turn-1:0:user">
  <div><div data-user-message-bubble="true"><div class="whitespace-pre-wrap">سؤال من</div></div>
  <div class="turn-action-controls"><button aria-label="Copy message"></button></div></div></div>
<div data-content-search-unit-key="fallback-turn-1:1:assistant">
  <h4 class="sr-only" data-conversation-role="assistant">ChatGPT said:</h4>
  <div><div data-markdown-text-style="assistant-message">
    <p>جواب مدل <span data-chatgpt-copy-reference="0" data-markdown-copy="contents">Some Source</span></p>
    <blockquote><p>نقل قول</p></blockquote>
  </div></div></div>
</main></body></html>"""


def test_extension_reads_logged_in_chatgpt_app():
    pw = playwright.sync_playwright().start()
    try:
        browser = pw.chromium.launch(channel="chrome", headless=True)
    except Exception:
        pw.stop()
        pytest.skip("Chrome not available")
    try:
        page = browser.new_page()
        page.route("https://chatgpt.com/**", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8",
                                                                body=APP_PAGE))
        page.goto("https://chatgpt.com/c/app-1")
        page.evaluate(EXTRACT_JS)
        data = page.evaluate("window.convohubExtract.extract()")
    finally:
        browser.close()
        pw.stop()
    assert [(m["role"], m["content"]) for m in data["messages"]] == [
        ("user", "سؤال من"), ("assistant", "جواب مدل\n\nنقل قول")]
