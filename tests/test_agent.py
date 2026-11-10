import asyncio
import json

import pytest

from convohub import config, db, openrouter
from convohub.agent import runner, skills
from convohub.agent import settings as agent_cfg
from convohub.agent.fs import Sandbox, ToolFailure


@pytest.fixture
def box(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("print('hi')\nTODO: fix\n", encoding="utf-8")
    (root / ".env").write_text("OPENROUTER_API_KEY=sk-secret", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("nope", encoding="utf-8")
    return Sandbox([str(root)]), root, tmp_path


def test_reads_inside_allowed_folder(box):
    sb, root, _ = box
    assert "app.py" in sb.list_directory(str(root / "src"))
    assert "print('hi')" in sb.read_file(str(root / "src" / "app.py"))
    assert "app.py:2" in sb.find_files(str(root), "*.py", contains="todo")
    assert "app.py" in sb.read_file("src/app.py")  # relative to the first allowed folder


@pytest.mark.parametrize("path", ["../outside.txt", "src/../../outside.txt"])
def test_cannot_escape(box, path):
    sb, root, tmp = box
    with pytest.raises(ToolFailure, match="outside the allowed"):
        sb.read_file(path)
    with pytest.raises(ToolFailure, match="outside the allowed"):
        sb.read_file(str(tmp / "outside.txt"))


def test_secrets_never_read(box):
    sb, root, _ = box
    with pytest.raises(ToolFailure, match="secrets"):
        sb.read_file(str(root / ".env"))
    assert ".env" not in sb.find_files(str(root), "*", contains="sk-")


def test_skill_folders_are_read_only(tmp_path):
    skill = tmp_path / "skills" / "deploy"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: deploy\ndescription: Ship it\n---\nSteps...", encoding="utf-8")
    sb = Sandbox([], read_only=[str(tmp_path / "skills")])
    assert "Steps" in sb.read_file(str(skill / "SKILL.md"))
    with pytest.raises(ToolFailure):
        sb.preview_write(str(skill / "x.txt"), "x")
    found = skills.discover([str(tmp_path / "skills")])
    assert [(s.name, s.description) for s in found] == [("deploy", "Ship it")]


def test_write_edit_delete(box):
    sb, root, _ = box
    target = root / "notes" / "a.md"
    assert "+hello" in sb.preview_write(str(target), "hello\n")["diff"]
    sb.write_file(str(target), "hello\n")
    sb.edit_file(str(target), "hello", "bye")
    assert target.read_text(encoding="utf-8") == "bye\n"
    with pytest.raises(ToolFailure, match="not found"):
        sb.preview_edit(str(target), "zzz", "y")
    with pytest.raises(ToolFailure, match="can't be deleted"):
        sb.preview_delete(str(root))


def test_settings_validation(tmp_path):
    with pytest.raises(agent_cfg.SettingsError):
        agent_cfg.validate({"allowed_folders": [str(tmp_path / "missing")]})
    with pytest.raises(agent_cfg.SettingsError):
        agent_cfg.validate({"allowed_folders": ["relative/path"]})
    ok = agent_cfg.validate({"mcp_servers": {"mcpServers": {"x": {"command": "uv", "args": []}}}})
    assert ok["mcp_servers"] == {"x": {"command": "uv", "args": []}}


# ---------- the loop, with a scripted fake model ----------

def fake_model(script):
    """Each call to stream_chat plays the next scripted step."""
    calls = []

    async def stream_chat(model, messages, max_tokens=None, tools=None):
        calls.append(json.loads(json.dumps(messages)))
        step = script[len(calls) - 1]
        if step.get("text"):
            yield {"type": "delta", "text": step["text"]}
        yield {"type": "usage", "prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001}
        if step.get("tools"):
            yield {"type": "tool_calls", "reasoning_details": [{"type": "x", "data": "sig"}], "calls": [
                {"id": f"c{i}", "name": n, "arguments": json.dumps(a)} for i, (n, a) in enumerate(step["tools"])]}

    return stream_chat, calls


async def collect(chat_id, settings, approve=None):
    events, state = [], {}
    async for ev in runner.run(chat_id, "m", [{"role": "system", "content": "s"}], settings, state):
        events.append(ev)
        if ev["type"] == "approval_request" and approve is not None:
            runner.resolve_approval(ev["approval_id"], approve)
    return events, state


@pytest.fixture
def agent_env(tmp_path, monkeypatch, box):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    db.init_db()
    sb, root, _ = box
    return {"allowed_folders": [str(root)], "skill_folders": [], "mcp_servers": {}}, root


def test_reads_run_without_approval(monkeypatch, agent_env):
    settings, root = agent_env
    stream, calls = fake_model([{"tools": [("read_file", {"path": str(root / "src" / "app.py")})]},
                                {"text": "It prints hi."}])
    monkeypatch.setattr(openrouter, "stream_chat", stream)
    events, state = asyncio.run(collect(None, settings))
    assert not [e for e in events if e["type"] == "approval_request"]
    assert [s["type"] for s in state["segments"]] == ["tool", "text"]
    tool_msg = calls[1][-1]
    assert tool_msg["role"] == "tool" and "print('hi')" in tool_msg["content"]
    assert calls[1][-2]["reasoning_details"] == [{"type": "x", "data": "sig"}]  # sent back for Gemini
    assert state["usage"]["prompt_tokens"] == 20


@pytest.mark.parametrize("approve,exists", [(True, True), (False, False)])
def test_write_needs_approval(monkeypatch, agent_env, approve, exists):
    settings, root = agent_env
    target = root / "new.txt"
    stream, calls = fake_model([{"tools": [("write_file", {"path": str(target), "content": "x"})]},
                                {"text": "done"}])
    monkeypatch.setattr(openrouter, "stream_chat", stream)
    events, state = asyncio.run(collect(None, settings, approve=approve))
    req = next(e for e in events if e["type"] == "approval_request")
    assert req["preview"]["kind"] == "write" and "+x" in req["preview"]["diff"]
    assert target.exists() is exists
    assert state["segments"][0]["approval"] == ("approved" if approve else "denied")
    with db.session() as conn:
        log = conn.execute("SELECT tool, status, approval FROM agent_log").fetchall()
    assert [tuple(r) for r in log] == [("write_file", "ok" if approve else "denied",
                                        "approved" if approve else "denied")]


def test_blocked_paths_never_reach_approval(monkeypatch, agent_env, tmp_path):
    settings, root = agent_env
    stream, _ = fake_model([{"tools": [("delete_path", {"path": str(tmp_path / "outside.txt")})]},
                            {"text": "ok"}])
    monkeypatch.setattr(openrouter, "stream_chat", stream)
    events, state = asyncio.run(collect(None, settings))
    assert not [e for e in events if e["type"] == "approval_request"]
    assert state["segments"][0]["status"] == "blocked"
    assert (tmp_path / "outside.txt").exists()


def test_outside_path_offers_folder_to_allow(monkeypatch, agent_env, tmp_path):
    settings, root = agent_env
    other = tmp_path / "test-1"
    other.mkdir()
    stream, _ = fake_model([{"tools": [("write_file", {"path": (other / "a.txt").as_posix(), "content": "x"})]},
                            {"text": "press the button"}])
    monkeypatch.setattr(openrouter, "stream_chat", stream)
    events, _ = asyncio.run(collect(None, {**settings, "allowed_folders": []}))
    res = next(e for e in events if e["type"] == "tool_result")
    assert res["status"] == "blocked"
    assert res["grant_folder"] == other.as_posix()
    assert not (other / "a.txt").exists()


def test_plain_chat_knows_agent_mode_is_off(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "p.db")
    db.init_db()
    from convohub import library, prompting
    with db.session() as conn:
        cid = library.create_chat(conn, "t", None)
        plain = prompting.build_messages(conn, cid, "m", "hi")
        agent = prompting.build_messages(conn, cid, "m", "hi", extra_system=runner.AGENT_PROMPT)
    assert "Agent mode is OFF" in plain[0]["content"]
    assert "AGENT MODE is on" in agent[0]["content"] and "Agent mode is OFF" not in agent[0]["content"]


def test_read_only_mode_reads_but_never_changes(monkeypatch, agent_env):
    settings, root = agent_env
    target = root / "x.txt"
    stream, calls = fake_model([
        {"tools": [("read_file", {"path": (root / "src" / "app.py").as_posix()}),
                   ("write_file", {"path": target.as_posix(), "content": "x"}),
                   ("run_command", {"command": "echo hi"})]},
        {"text": "turn on agent mode to change things"}])
    monkeypatch.setattr(openrouter, "stream_chat", stream)

    async def go():
        events, state = [], {}
        async for ev in runner.run(None, "m", [{"role": "system", "content": "s"}], settings, state, read_only=True):
            events.append(ev)
        return events, state

    events, state = asyncio.run(go())
    assert not [e for e in events if e["type"] == "approval_request"]
    statuses = [(s["name"], s["status"]) for s in state["segments"] if s["type"] == "tool"]
    assert statuses == [("read_file", "ok"), ("write_file", "blocked"), ("run_command", "blocked")]
    assert not target.exists()
    assert "not available here" in calls[1][-1]["content"]


class FakeBridge:
    """Stands in for MCPBridge: one tool that *claims* to be read-only."""
    calls = []

    def __init__(self, servers):
        self.errors = {}
        self.tools = {"mcp__srv__peek": {"server": "srv", "tool": "peek", "description": "", "schema": {}}}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def definitions(self):
        return [{"type": "function", "function": {"name": n, "parameters": {}}} for n in self.tools]

    async def call(self, name, args):
        FakeBridge.calls.append(name)
        return "peeked"


def test_mcp_tools_always_ask_and_always_allow_is_remembered(monkeypatch, agent_env):
    settings, root = agent_env
    monkeypatch.setattr(runner, "MCPBridge", FakeBridge)
    FakeBridge.calls = []

    def run_once(answer):
        stream, _ = fake_model([{"tools": [("mcp__srv__peek", {})]}, {"text": "ok"}])
        monkeypatch.setattr(openrouter, "stream_chat", stream)

        async def go():
            events, state = [], {}
            async for ev in runner.run(None, "m", [{"role": "system", "content": "s"}],
                                       {**settings, **saved()}, state):
                events.append(ev)
                if ev["type"] == "approval_request":
                    runner.resolve_approval(ev["approval_id"], *answer)
            return events, state
        return asyncio.run(go())

    def saved():
        with db.session() as conn:
            return {"mcp_always_allow": agent_cfg.load(conn)["mcp_always_allow"]}

    events, state = run_once((False,))   # asks, user says no
    assert [e for e in events if e["type"] == "approval_request"][0]["preview"]["key"] == "srv/peek"
    assert FakeBridge.calls == [] and state["segments"][0]["status"] == "denied"

    events, state = run_once((True, True))  # asks, user says "always allow"
    assert FakeBridge.calls == ["mcp__srv__peek"] and state["segments"][0]["approval"] == "always"
    assert saved()["mcp_always_allow"] == ["srv/peek"]

    events, state = run_once((False,))   # remembered: no card this time
    assert not [e for e in events if e["type"] == "approval_request"]
    assert FakeBridge.calls == ["mcp__srv__peek", "mcp__srv__peek"]


def test_approval_diff_is_not_cut_at_12k(box):
    sb, root, _ = box
    big = "".join(f"line {i} {'x' * 40}\n" for i in range(2000))  # ~100 KB of new text
    diff = sb.preview_write(str(root / "big.txt"), big)["diff"]
    assert "line 1999" in diff and "too long" not in diff
