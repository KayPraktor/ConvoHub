"""Interface language (fa/en): the setting, server texts, prompts and handoff text that follow it."""

import asyncio
import json
import re
import string
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convohub import config, db, handoff, i18n, library, openrouter, prompting
from convohub.agent import runner
from convohub.messages import MESSAGES

PKG = Path(__file__).resolve().parent.parent / "convohub"
PERSIAN = re.compile("[؀-ۿ]")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "lang.db")
    from convohub.main import app
    with TestClient(app) as c:
        yield c


def set_lang(client, lang):
    res = client.put("/api/settings/lang", json={"lang": lang})
    assert res.status_code == 200 and res.json()["lang"] == lang


# ---------- the setting ----------

def test_new_install_has_no_choice_and_speaks_english(client):
    assert client.get("/api/settings/lang").json() == {"lang": None, "available": ["fa", "en"]}
    assert client.get("/api/health").json()["lang"] == "en"


def test_choose_language(client):
    set_lang(client, "fa")
    assert client.get("/api/settings/lang").json()["lang"] == "fa"
    assert client.get("/api/health").json()["lang"] == "fa"
    set_lang(client, "en")
    assert client.get("/api/health").json()["lang"] == "en"
    bad = client.put("/api/settings/lang", json={"lang": "de"})
    assert bad.status_code == 400 and bad.json()["detail"] == MESSAGES["api.bad_lang"]["en"]


def test_older_install_with_conversations_stays_persian(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    db.init_db()
    with db.session() as conn:  # what a database from before the English version looks like
        library.create_conversation(conn, title="x", source="other", import_method="paste", raw_text="hi")
        conn.execute("DELETE FROM settings WHERE key = 'ui_lang'")
    i18n.reset_cache()
    assert i18n.stored() == "fa"  # also before the server initializes it (the launcher)

    i18n.reset_cache()
    from convohub.main import app
    with TestClient(app) as c:
        assert c.get("/api/settings/lang").json()["lang"] == "fa"
    with db.closing(db.connect()) as conn:  # settled for good
        assert json.loads(conn.execute("SELECT value FROM settings WHERE key = 'ui_lang'").fetchone()[0]) == "fa"


def test_importing_before_choosing_does_not_switch_to_persian(client):
    client.post("/api/import/paste", json={"text": "some conversation text"})
    i18n.reset_cache()  # e.g. the next start of the app
    assert client.get("/api/settings/lang").json()["lang"] is None


def test_no_database_yet_means_english_and_nothing_is_created(tmp_path, monkeypatch):
    folder = tmp_path / "not-yet"
    monkeypatch.setattr(config, "DB_PATH", folder / "convohub.db")
    from convohub import __main__ as launcher
    assert i18n.current() == "en"
    assert launcher.t("launcher.not_running") == "ConvoHub isn't running."
    assert not folder.exists()


# ---------- server texts ----------

def test_error_messages_follow_the_language(client):
    set_lang(client, "en")
    assert client.get("/api/conversations/999").json()["detail"] == "Not found."
    assert client.post("/api/import/paste", json={"text": "   "}).json()["detail"] == "The text is empty."
    set_lang(client, "fa")
    assert client.get("/api/conversations/999").json()["detail"] == MESSAGES["api.not_found"]["fa"]
    assert client.post("/api/import/paste", json={"text": "   "}).json()["detail"] == MESSAGES["import.empty_text"]["fa"]


def _fake_stream(monkeypatch):
    async def stream_chat(model, messages, max_tokens=None, tools=None):
        await asyncio.sleep(0)
        yield {"type": "delta", "text": "ok"}
        yield {"type": "usage", "prompt_tokens": 1, "completion_tokens": 1, "cost": 0}

    async def list_models(force=False):
        return []
    monkeypatch.setattr(openrouter, "stream_chat", stream_chat)
    monkeypatch.setattr(openrouter, "list_models", list_models)


def test_new_chat_title_follows_the_language_and_is_renamed_in_any(client, monkeypatch):
    _fake_stream(monkeypatch)
    set_lang(client, "fa")
    fa_chat = client.post("/api/chats", json={}).json()["id"]
    assert client.get(f"/api/chats/{fa_chat}").json()["chat"]["title"] == MESSAGES["api.new_chat_title"]["fa"]

    set_lang(client, "en")
    en_chat = client.post("/api/chats", json={}).json()["id"]
    assert client.get(f"/api/chats/{en_chat}").json()["chat"]["title"] == "New chat"

    # The chat made in Persian still gets its title from the first message after switching to English.
    client.post(f"/api/chats/{fa_chat}/messages", json={"content": "Pricing for the yearly plan", "model": "x/m"})
    assert client.get(f"/api/chats/{fa_chat}").json()["chat"]["title"] == "Pricing for the yearly plan"
    named = client.post("/api/chats", json={"title": "Mine"}).json()["id"]
    client.post(f"/api/chats/{named}/messages", json={"content": "hello there", "model": "x/m"})
    assert client.get(f"/api/chats/{named}").json()["chat"]["title"] == "Mine"


# ---------- prompts name the buttons the user sees ----------

def test_prompts_use_the_ui_labels(client):
    set_lang(client, "en")
    assert "“Agent mode”" in runner.read_prompt() and "“continue”" in runner.agent_prompt()
    assert "“Agent mode”" in prompting.chat_mode_note()
    set_lang(client, "fa")
    assert "«حالت ایجنت»" in runner.read_prompt() and "«ادامه بده»" in runner.agent_prompt()
    assert "«حالت ایجنت»" in prompting.chat_mode_note()
    assert "usually Persian" not in prompting.SYSTEM_BASE + prompting.SUMMARY_PROMPT + handoff.BRIEF_PROMPT


# ---------- handoff text ----------

def _chat(client):
    gem = client.post("/api/import/paste", json={"text": "how to price? freemium", "title": "Gem"}).json()["ids"][0]
    chat = client.post("/api/chats", json={"title": "Pricing", "context": [{"id": gem}]}).json()["id"]
    with db.session() as conn:
        library.add_message(conn, chat, "user", "yearly plan?")
        library.add_message(conn, chat, "assistant", "10x monthly", model="x/a")
    return chat


def _build(client, chat, target):
    return client.post(f"/api/chats/{chat}/handoff/build", json={"target": target}).json()["text"]


def test_handoff_text_follows_the_language_and_compacts_in_both(client):
    chat = _chat(client)
    set_lang(client, "en")
    en = _build(client, chat, "original")
    assert "**Me:**" in en and "**Assistant (x/a):**" in en and "--- Start: conversation continued ---" in en
    en_new = _build(client, chat, "new")
    assert "## Background: “Gem”" in en_new and "## Recent conversation" in en_new
    assert not PERSIAN.search(en + en_new)

    set_lang(client, "fa")
    fa = _build(client, chat, "original")
    assert "**من:**" in fa and "**دستیار (x/a):**" in fa and "--- شروع ادامه‌ی گفتگو ---" in fa
    fa_new = _build(client, chat, "new")
    assert "## پیش‌زمینه: «Gem»" in fa_new and "## گفتگوی اخیر" in fa_new

    # A handoff synced back from the chat site is shortened, whichever language it was made in;
    # the note is in the current language.
    for text in (en, fa):
        short = handoff.compact(text)
        assert short == text.split("\n", 1)[0] + "\n" + MESSAGES["handoff.compact_note"]["fa"]
    set_lang(client, "en")
    assert handoff.compact(fa).endswith("\n(The full text of this part is in ConvoHub.)")
    assert handoff.compact("just a message") == "just a message"


# ---------- the message table itself ----------

def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def test_every_message_has_both_languages_with_the_same_placeholders():
    for key, entry in MESSAGES.items():
        assert set(entry) == {"fa", "en"}, key
        assert entry["fa"].strip() and entry["en"].strip(), key
        assert _placeholders(entry["fa"]) == _placeholders(entry["en"]), key
        assert not PERSIAN.search(entry["en"]), key


def test_mac_variants_match_their_base_key():
    macs = [k for k in MESSAGES if k.endswith("_mac")]
    assert macs
    for key in macs:
        base = key[: -len("_mac")]
        assert base in MESSAGES, key
        for lang in i18n.LANGS:
            assert _placeholders(MESSAGES[key][lang]) == _placeholders(MESSAGES[base][lang]), key


def test_platform_texts_pick_the_mac_variant_only_on_a_mac(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert i18n.tp("link.no_browser") == MESSAGES["link.no_browser_mac"]["en"]
    assert i18n.tp("link.timeout") == MESSAGES["link.timeout"]["en"]  # no variant: the common text
    assert i18n.tp("settings.whole_drive", "fa", path="/") == MESSAGES["settings.whole_drive_mac"]["fa"].format(path="/")
    monkeypatch.setattr("sys.platform", "win32")
    assert i18n.tp("link.no_browser") == MESSAGES["link.no_browser"]["en"]
    assert "D:\\Projects\\MyApp" in i18n.tp("settings.path_not_absolute", path="x")


def _js_keys(path: Path) -> dict[str, set[str]]:
    text = path.read_text(encoding="utf-8")
    fa, en = text.index("  fa: {"), text.index("  en: {")
    keys = lambda part: set(re.findall(r'^\s*"([^"]+)":', part, re.M))  # noqa: E731
    return {"fa": keys(text[fa:en]), "en": keys(text[en:])}


@pytest.mark.parametrize("name", ["app.js", "html.js"])
def test_ui_mac_variants_exist_in_both_languages_with_a_base_key(name):
    keys = _js_keys(PKG / "static" / "locales" / name)
    macs = {lang: {k for k in ks if k.endswith(".mac")} for lang, ks in keys.items()}
    assert macs["fa"] and macs["fa"] == macs["en"]
    for lang, ks in keys.items():
        assert all(k[: -len(".mac")] in ks for k in macs[lang]), lang


def test_every_key_used_in_the_code_exists():
    used = set()
    for path in PKG.rglob("*.py"):
        used |= set(re.findall(r"""\btp?\(\s*["']([a-z_]+\.[a-z0-9_]+)["']""", path.read_text(encoding="utf-8")))
    used |= {f"openrouter.status_{code}" for code in openrouter._KNOWN_STATUS}
    assert used and not (used - set(MESSAGES)), sorted(used - set(MESSAGES))


# Persian that is not user-facing text: it matches or normalizes text, so it must stay as it is.
ALLOWED_PERSIAN = {
    "text.py": ("_ARABIC_TO_PERSIAN = ", "_DIACRITICS = "),   # search normalization of Persian/Arabic letters
    "links.py": ("_BOT_WALL = ",),                           # detecting a Persian bot-check page
}


def test_no_persian_text_outside_messages_py():
    found = []
    for path in PKG.rglob("*.py"):
        if path.name == "messages.py":
            continue
        allowed = ALLOWED_PERSIAN.get(path.name, ())
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if PERSIAN.search(line) and not line.strip().startswith(allowed or ("\0",)):
                found.append(f"{path.relative_to(PKG)}:{n}: {line.strip()[:80]}")
    assert not found, "\n".join(found)


def test_stop_shortcut_name_in_both_languages():
    from convohub import shortcut
    assert shortcut.stop_names() == {"ConvoHub - Stop", MESSAGES["shortcut.stop_name"]["fa"]}
