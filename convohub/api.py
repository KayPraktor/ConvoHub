"""JSON API used by the web UI."""

import asyncio
import json
import os
import sys
import time

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import __version__, backup, config, db, extension_pairing, handoff, keystore, library, memory, openrouter, panel, prompting
from .importers import files as file_import
from .importers import links as link_import
from .importers import extension as ext_import
from .importers import paste as paste_import
from .agent import runner as agent_runner
from .agent import settings as agent_cfg
from .agent import skills as agent_skills
from .text import SOURCES, clean_pasted, detect_source, estimate_tokens, guess_title

router = APIRouter(prefix="/api")

NEW_CHAT_TITLE = "گفتگوی جدید"
LINK_TIMEOUT_S = 90


def _not_found():
    raise HTTPException(404, "پیدا نشد.")


def _source_or_detect(source: str | None, text: str) -> str:
    if source and source in SOURCES and source != "native":
        return source
    return detect_source(text)


@router.get("/health")
def health():
    # Only report whether the key exists, never the key itself.
    return {"ok": True, "version": __version__, "openrouter_key_set": config.openrouter_key() is not None,
            "pid": os.getpid()}  # lets `--stop` wait until this process has really exited


# ---------- library ----------

@router.get("/conversations")
def list_conversations(q: str = ""):
    with db.session() as conn:
        return library.search(conn, q) if q.strip() else library.list_conversations(conn)


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int):
    with db.session() as conn:
        conv = library.get_conversation(conn, conv_id)
        if not conv:
            _not_found()
        conv["tokens"] = estimate_tokens(library.conversation_text(conn, conv_id))
        conv["summary_tokens"] = estimate_tokens(conv["summary"] or "")
        return conv


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)


@router.patch("/conversations/{conv_id}")
def rename(conv_id: int, body: RenameIn):
    with db.session() as conn:
        if not library.rename(conn, conv_id, body.title.strip()):
            _not_found()
    return {"ok": True}


@router.delete("/conversations/{conv_id}")
def delete(conv_id: int):
    with db.session() as conn:
        if not library.delete(conn, conv_id):
            _not_found()
    return {"ok": True}


class SummarizeIn(BaseModel):
    model: str


@router.post("/conversations/{conv_id}/summarize")
async def summarize(conv_id: int, body: SummarizeIn):
    with db.session() as conn:
        if not conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conv_id,)).fetchone():
            _not_found()
        transcript = library.conversation_text(conn, conv_id)
    try:
        summary, usage = await openrouter.complete(body.model, prompting.summary_messages(transcript))
    except openrouter.OpenRouterError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not summary.strip():
        raise HTTPException(502, "مدل خلاصه‌ای برنگردوند.")
    with db.session() as conn:
        library.set_summary(conn, conv_id, summary.strip(), body.model)
    return {"summary": summary.strip(), "usage": usage, "tokens": estimate_tokens(summary)}


# ---------- import ----------

class PasteIn(BaseModel):
    text: str = Field(min_length=1)
    title: str | None = None
    source: str | None = None


@router.post("/import/preview")
def import_preview(body: PasteIn):
    cleaned = clean_pasted(body.text)
    return {
        "title": guess_title(cleaned),
        "source": detect_source(body.text),
        "chars": len(cleaned),
        "tokens": estimate_tokens(cleaned),
    }


@router.post("/import/paste")
def import_paste(body: PasteIn):
    try:
        with db.session() as conn:
            conv_id = paste_import.import_text(conn, body.text, body.title, body.source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ids": [conv_id]}


@router.post("/import/file")
async def import_file(file: UploadFile = File(...), source: str | None = Form(None)):
    data = await file.read()
    try:
        parsed = file_import.parse_file(file.filename or "file.txt", data)
    except file_import.ImportFileError as exc:
        raise HTTPException(400, str(exc)) from exc
    ids = []
    with db.session() as conn:
        for p in parsed:
            src = p.source
            if len(parsed) == 1 and source and source in SOURCES and source != "native":
                src = source
            ids.append(library.create_conversation(
                conn, title=p.title, source=src, import_method="file", raw_text=p.raw_text, messages=p.messages,
            ))
    return {"ids": ids}


class LinkIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


async def _fetch_link(url: str) -> link_import.LinkResult:
    try:
        return await asyncio.wait_for(run_in_threadpool(link_import.fetch_link, url), LINK_TIMEOUT_S)
    except TimeoutError as exc:
        raise HTTPException(504, "خوندن لینک بیشتر از ۹۰ ثانیه طول کشید. شبکه یا VPN رو چک کن.") from exc
    except link_import.LinkImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/import/link")
async def import_link(body: LinkIn):
    result = await _fetch_link(body.url)
    with db.session() as conn:
        conv_id = paste_import.save_link(conn, result)
    return {"ids": [conv_id], "messages": len(result.messages)}


@router.post("/conversations/{conv_id}/refresh")
async def refresh_link(conv_id: int):
    with db.session() as conn:
        row = conn.execute("SELECT source_url FROM conversations WHERE id = ? AND import_method = 'link'",
                           (conv_id,)).fetchone()
    if not row:
        _not_found()
    if not row["source_url"]:
        raise HTTPException(400, "این مکالمه از لینک نیومده.")
    result = await _fetch_link(row["source_url"])
    with db.session() as conn:
        library.replace_content(conn, conv_id, result.raw_text, result.messages)
    return {"ok": True, "chars": len(result.raw_text)}


# ---------- models ----------

@router.get("/models")
async def models(refresh: bool = False):
    try:
        return await openrouter.list_models(force=refresh)
    except openrouter.OpenRouterError as exc:
        raise HTTPException(502, str(exc)) from exc


# ---------- chats ----------

class ContextItem(BaseModel):
    id: int
    use_summary: bool = False


class ChatIn(BaseModel):
    title: str | None = None
    model: str | None = None
    context: list[ContextItem] = []


@router.post("/chats")
def create_chat(body: ChatIn):
    with db.session() as conn:
        chat_id = library.create_chat(conn, (body.title or "").strip() or NEW_CHAT_TITLE, body.model)
        library.set_context(conn, chat_id, [c.model_dump() for c in body.context])
    return {"id": chat_id}


def _require_chat(conn, chat_id: int):
    row = conn.execute("SELECT * FROM conversations WHERE id = ? AND source = 'native'", (chat_id,)).fetchone()
    if not row:
        _not_found()
    return row


@router.get("/chats/{chat_id}")
def get_chat(chat_id: int):
    with db.session() as conn:
        chat = dict(_require_chat(conn, chat_id))
        chat.pop("raw_text", None)
        return {"chat": chat, "messages": library.get_messages(conn, chat_id),
                "context": library.get_context(conn, chat_id)}


class ContextIn(BaseModel):
    items: list[ContextItem]


@router.put("/chats/{chat_id}/context")
def set_context(chat_id: int, body: ContextIn):
    with db.session() as conn:
        _require_chat(conn, chat_id)
        library.set_context(conn, chat_id, [c.model_dump() for c in body.items])
        return {"context": library.get_context(conn, chat_id)}


class EstimateIn(BaseModel):
    draft: str = ""
    model: str | None = None
    models: list[str] = Field(default_factory=list)
    memory: bool | None = None  # None: the global setting


@router.post("/chats/{chat_id}/estimate")
async def estimate(chat_id: int, body: EstimateIn):
    with db.session() as conn:
        _require_chat(conn, chat_id)
        mem_text, mem_used, mem_total = _memory_for(conn, chat_id, body.memory, body.draft)
        est = prompting.estimate(conn, chat_id, body.draft, mem_text)
        est["memory_notes"], est["memory_total"] = mem_used, mem_total
    est["model"] = None
    if body.model:
        try:
            m = next((m for m in await openrouter.list_models() if m["id"] == body.model), None)
        except openrouter.OpenRouterError:
            m = None
        if m:
            est["model"] = m
            if m["prompt_price"] is not None:
                est["input_cost"] = est["total_tokens"] * m["prompt_price"]
            est["over_context"] = bool(m["context_length"]) and est["total_tokens"] > m["context_length"]
    extra = [x for x in dict.fromkeys(body.models) if x and x != body.model]
    if extra and "input_cost" in est:
        # Multi-model: every model gets the same input.
        try:
            prices = {m["id"]: m["prompt_price"] for m in await openrouter.list_models()}
        except openrouter.OpenRouterError:
            prices = {}
        est["input_cost"] += sum(est["total_tokens"] * (prices.get(x) or 0) for x in extra)
        est["models_count"] = 1 + len(extra)
    return est


class MessageIn(BaseModel):
    content: str = Field(min_length=1)
    model: str = Field(min_length=1)
    agent: bool = False
    memory: bool | None = None  # None: the global setting
    models: list[str] = Field(default_factory=list, max_length=panel.MAX_MODELS)  # extra models: multi-model mode
    orchestrator: str | None = None


PANEL_PROMPT = """Several AI models answer this chat in parallel; earlier turns may show all their answers,
labelled by model. Give your own best answer to the user's latest message (you may build on or disagree with the
others). You have no access to the user's files in this mode."""


def _memory_for(conn, chat_id: int, wanted: bool | None, new_text: str | None) -> tuple[str, int, int]:
    """The memory block for this chat's next message, if memory is on for it."""
    on = memory.enabled(conn) if wanted is None else wanted
    if not on:
        return "", 0, 0
    return memory.block(conn, memory.chat_query(conn, chat_id, new_text))


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _model_supports_tools(model: str) -> bool:
    try:
        models = await openrouter.list_models()
    except openrouter.OpenRouterError:
        return False  # can't tell: fall back to plain chat, which works with every model
    m = next((x for x in models if x["id"] == model), None)
    return bool(m and m["tools"])


@router.post("/chats/{chat_id}/messages")
async def send_message(chat_id: int, body: MessageIn):
    # Modes: panel (several models in parallel, no tools), agent (toggle on), read-only (toggle off, model can
    # use tools: it may look at allowed folders but change nothing), plain (model has no tool support).
    panel_models = list(dict.fromkeys([body.model, *[m.strip() for m in body.models if m.strip()]]))
    if len(panel_models) > panel.MAX_MODELS:
        raise HTTPException(400, f"حداکثر {panel.MAX_MODELS} مدل با هم.")
    if len(panel_models) > 1:
        mode = "panel"
    elif body.agent:
        mode = "agent"
    else:
        mode = "read" if await _model_supports_tools(body.model) else "plain"
    extra = {"agent": agent_runner.AGENT_PROMPT, "read": agent_runner.READ_PROMPT, "plain": None,
             "panel": PANEL_PROMPT}[mode]

    with db.session() as conn:
        chat = _require_chat(conn, chat_id)
        agent_settings = agent_cfg.load(conn) if mode in ("agent", "read") else None
        mem_on = memory.enabled(conn) if body.memory is None else body.memory
        mem_text, _, _ = _memory_for(conn, chat_id, mem_on, body.content)
        if mem_on and mode in ("agent", "read"):
            extra = extra + "\n\n" + memory.SUGGEST_PROMPT  # the model may suggest notes (the user confirms)
        messages = prompting.build_messages(conn, chat_id, body.model, body.content, extra_system=extra,
                                            memory_text=mem_text)
        library.add_message(conn, chat_id, "user", body.content)
        if chat["title"] == NEW_CHAT_TITLE:
            library.rename(conn, chat_id, guess_title(body.content, 50))

    async def plain():
        state = {"segments": [], "usage": {}}
        async for ev in openrouter.stream_chat(body.model, messages):
            if ev["type"] == "delta":
                if not state["segments"]:
                    state["segments"].append({"type": "text", "text": ""})
                state["segments"][0]["text"] += ev["text"]
                yield ev, state
            elif ev["type"] == "usage":
                state["usage"] = ev

    async def agent():
        state = {}
        async for ev in agent_runner.run(chat_id, body.model, messages, agent_settings, state,
                                         read_only=(mode == "read"), suggest_memory=mem_on):
            yield ev, state

    if mode == "panel":
        return StreamingResponse(_panel_events(chat_id, panel_models, body.orchestrator, messages),
                                 media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def events():
        state, error = {"segments": [], "usage": {}}, None
        try:
            async for ev, state in (plain() if mode == "plain" else agent()):
                yield ": ping\n\n" if ev["type"] == "ping" else _sse(ev)
        except openrouter.OpenRouterError as exc:
            error = str(exc)
        finally:
            # Runs on success, error, and when the user presses stop (client disconnects).
            segments, usage = state.get("segments") or [], state.get("usage") or {}
            text = "\n\n".join(s["text"] for s in segments if s["type"] == "text").strip()
            has_tools = any(s["type"] in ("tool", "memory") for s in segments)
            if text or has_tools:
                if error:
                    text += "\n\n[جواب ناقص ماند]"
                with db.session() as conn:
                    library.add_message(
                        conn, chat_id, "assistant", text, model=body.model,
                        prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
                        cost=usage.get("cost"), tool_trace=segments if has_tools else None,
                    )
        if error:
            yield _sse({"type": "error", "message": error})
        yield _sse({"type": "done", "usage": state.get("usage") or {}})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _panel_events(chat_id: int, models: list[str], orchestrator: str | None, messages: list[dict]):
    state: dict = {}
    try:
        async for ev in panel.run(models, orchestrator, messages, state):
            yield _sse(ev)
    finally:
        # Save every answer that has text, also when the user pressed stop.
        with db.session() as conn:
            for a in state.get("answers", []):
                text = a["text"].strip()
                if not text:
                    continue
                if a["error"]:
                    text += "\n\n[جواب ناقص ماند]"
                u = a["usage"] or {}
                library.add_message(conn, chat_id, "assistant", text, model=a["model"],
                                    prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                                    cost=u.get("cost"), kind="synthesis" if a.get("synthesis") else "panel")
    total = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
    for a in state.get("answers", []):
        for k in total:
            total[k] += (a["usage"] or {}).get(k) or 0
    yield _sse({"type": "done", "usage": total})


# ---------- agent mode ----------

@router.get("/agent/settings")
def get_agent_settings():
    with db.session() as conn:
        s = agent_cfg.load(conn)
    s["skills"] = [{"name": k.name, "description": k.description, "path": str(k.path)}
                   for k in agent_skills.discover(s["skill_folders"])]
    return s


class AgentSettingsIn(BaseModel):
    allowed_folders: list[str] | None = None
    skill_folders: list[str] | None = None
    mcp_servers: dict | None = None
    mcp_always_allow: list[str] | None = None


@router.put("/agent/settings")
def put_agent_settings(body: AgentSettingsIn):
    try:
        with db.session() as conn:
            agent_cfg.save(conn, body.model_dump(exclude_none=True))
    except agent_cfg.SettingsError as exc:
        raise HTTPException(400, str(exc)) from exc
    return get_agent_settings()


class ApprovalIn(BaseModel):
    approved: bool
    always: bool = False  # "always allow" this MCP tool


@router.post("/agent/approvals/{approval_id}")
def answer_approval(approval_id: str, body: ApprovalIn):
    if not agent_runner.resolve_approval(approval_id, body.approved, body.always):
        raise HTTPException(404, "این درخواست دیگه منتظر جواب نیست.")
    return {"ok": True}


@router.get("/chats/{chat_id}/agent-log")
def agent_log(chat_id: int):
    with db.session() as conn:
        rows = conn.execute(
            "SELECT id, tool, args, status, approval, result, created_at FROM agent_log WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        )
        return [{**dict(r), "args": json.loads(r["args"])} for r in rows]


# ---------- handoff: take a chat back to the original AI chat, or to another one ----------

class HandoffIn(BaseModel):
    target: str = Field(pattern="^(original|new)$")
    since_last: bool = True
    format: str = Field("full", pattern="^(full|brief)$")
    model: str | None = None


class HandoffDoneIn(BaseModel):
    target: str = Field(pattern="^(original|new)$")
    format: str = Field("full", pattern="^(full|brief)$")
    upto: int
    via: str = Field(pattern="^(copy|file|extension)$")
    text: str | None = Field(None, max_length=2_000_000)  # only for via=extension


@router.get("/chats/{chat_id}/handoff")
def handoff_info(chat_id: int):
    with db.session() as conn:
        _require_chat(conn, chat_id)
        return {**handoff.info(conn, chat_id), "extension_waiting": bool(handoff.peek_pending())}


@router.post("/chats/{chat_id}/handoff/build")
async def handoff_build(chat_id: int, body: HandoffIn):
    with db.session() as conn:
        _require_chat(conn, chat_id)
        if body.format == "full":
            return handoff.build(conn, chat_id, body.target, body.since_last)
        m = handoff.material(conn, chat_id, body.target, body.since_last)
    if not m["body"]:
        return {"text": "", "tokens": 0, "count": 0, "upto": m["upto"]}
    if not body.model:
        raise HTTPException(400, "برای خلاصه یه مدل انتخاب کن.")
    try:
        brief, usage = await openrouter.complete(body.model, handoff.brief_messages(body.target, m["body"]))
    except openrouter.OpenRouterError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not brief.strip():
        raise HTTPException(502, "مدل خلاصه‌ای برنگردوند.")
    text = handoff.wrap(m["title"], body.target, brief, brief=True)
    return {"text": text, "tokens": estimate_tokens(text), "count": m["count"], "upto": m["upto"], "usage": usage}


@router.post("/chats/{chat_id}/handoff/done")
def handoff_done(chat_id: int, body: HandoffDoneIn):
    with db.session() as conn:
        chat = _require_chat(conn, chat_id)
        if body.via == "extension":
            if not (body.text or "").strip():
                raise HTTPException(400, "متنی برای فرستادن نیست.")
            handoff.set_pending(body.text, chat["title"])
        handoff.record(conn, chat_id, body.target, body.format, body.upto, body.via)
        return handoff.info(conn, chat_id)


@router.delete("/handoff/pending")
def handoff_cancel_pending():
    handoff.clear_pending()
    return {"ok": True}


# ---------- memory: notes about the user, sent to the models ----------

def _memory_state(conn) -> dict:
    items = memory.list_notes(conn)
    active = [n for n in items if n["status"] == "active"]
    text, used, total = memory.block(conn)
    return {"enabled": memory.enabled(conn), "items": items, "active": len(active),
            "suggested": len(items) - len(active), "tokens": estimate_tokens(text) if text else 0,
            "token_cap": memory.TOKEN_CAP, "all_fit": used == total}


class MemoryAddIn(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=50)
    source_conversation_id: int | None = None


class MemoryEditIn(BaseModel):
    text: str | None = None
    status: str | None = Field(None, pattern="^active$")  # approve a suggestion


class MemorySettingsIn(BaseModel):
    enabled: bool


@router.get("/memory")
def memory_list():
    with db.session() as conn:
        return _memory_state(conn)


@router.post("/memory")
def memory_add(body: MemoryAddIn):
    with db.session() as conn:
        added = []
        for text in body.texts:
            try:
                added.append(memory.add(conn, text, "active", body.source_conversation_id))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        return {**_memory_state(conn), "added": added}


@router.patch("/memory/{note_id}")
def memory_edit(note_id: int, body: MemoryEditIn):
    with db.session() as conn:
        try:
            note = memory.update(conn, note_id, body.text, body.status)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not note:
            _not_found()
        return {**_memory_state(conn), "note": note}


@router.delete("/memory/{note_id}")
def memory_delete(note_id: int):
    with db.session() as conn:
        if not memory.delete(conn, note_id):
            _not_found()
        return _memory_state(conn)


@router.put("/memory/settings")
def memory_settings(body: MemorySettingsIn):
    with db.session() as conn:
        memory.set_enabled(conn, body.enabled)
        return _memory_state(conn)


@router.post("/conversations/{conv_id}/memory/extract")
async def memory_extract(conv_id: int, body: SummarizeIn):
    """Suggest notes from a conversation. Nothing is saved: the user picks which ones to keep."""
    with db.session() as conn:
        if not conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conv_id,)).fetchone():
            _not_found()
        conv = conn.execute("SELECT summary FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        transcript = library.conversation_text(conn, conv_id)
    if estimate_tokens(transcript) > 120_000 and conv["summary"]:
        transcript = conv["summary"]  # very long: the summary is enough for lasting facts
    try:
        reply, usage = await openrouter.complete(body.model, memory.extract_messages(transcript))
    except openrouter.OpenRouterError as exc:
        raise HTTPException(502, str(exc)) from exc
    notes = memory.parse_extracted(reply)
    if not notes and reply.strip():
        raise HTTPException(502, "جواب مدل قابل خوندن نبود. یه مدل دیگه امتحان کن.")
    with db.session() as conn:
        existing = [n["text"] for n in memory.list_notes(conn, "active")]
    return {"suggestions": [{"text": t, "known": any(memory._same(t, e) for e in existing)} for t in notes],
            "usage": usage}


# ---------- browser extension ----------

def _require_extension(x_convohub_client: str | None) -> None:
    # A custom header can't be sent by an ordinary web page without a CORS preflight, which this server
    # never approves. So only the extension (or local tools) can call these endpoints.
    if x_convohub_client != "extension":
        raise HTTPException(403, "only the ConvoHub extension can call this")


@router.get("/extension/status")
def extension_status(url: str, x_convohub_client: str | None = Header(None)):
    _require_extension(x_convohub_client)
    with db.session() as conn:
        return ext_import.status(conn, url)


class ExtMessage(BaseModel):
    role: str
    content: str


class ExtSyncIn(BaseModel):
    url: str = Field(max_length=2000)
    title: str | None = Field(None, max_length=500)
    messages: list[ExtMessage] = Field(max_length=5000)
    full: bool = False


@router.post("/extension/sync")
def extension_sync(body: ExtSyncIn, x_convohub_client: str | None = Header(None)):
    _require_extension(x_convohub_client)
    try:
        with db.session() as conn:
            return ext_import.sync(conn, body.url, body.title, [m.model_dump() for m in body.messages], body.full)
    except ext_import.SyncError as exc:
        raise HTTPException(400, str(exc)) from exc


# Both POST: browsers always send Origin on POST, so the pairing check in main.py applies.
@router.post("/extension/handoff/peek")
def extension_handoff_peek(x_convohub_client: str | None = Header(None)):
    _require_extension(x_convohub_client)
    p = handoff.peek_pending()
    return {"pending": bool(p), "title": p["title"] if p else None, "chars": len(p["text"]) if p else 0}


@router.post("/extension/handoff/take")
def extension_handoff_take(x_convohub_client: str | None = Header(None)):
    _require_extension(x_convohub_client)
    p = handoff.take_pending()
    if not p:
        raise HTTPException(404, "متنی منتظر نیست. توی ConvoHub دوباره «بفرست به افزونه» رو بزن.")
    return {"text": p["text"], "title": p["title"]}


# ---------- backups ----------

def _backup_info(conn) -> dict:
    target = backup.folder(conn)
    return {"folder": str(target), "default": target == backup.default_folder(),
            "items": backup.list_backups(target), "keep_auto": backup.KEEP_AUTO}


@router.get("/backups")
def list_backups():
    with db.session() as conn:
        return _backup_info(conn)


@router.post("/backups")
def create_backup():
    with db.session() as conn:
        try:
            made = backup.create(conn, backup.folder(conn))
        except OSError as exc:
            raise HTTPException(500, f"بکاپ گرفته نشد: {exc}") from exc
        return {**_backup_info(conn), "created": made}


class BackupFolderIn(BaseModel):
    folder: str | None = None


@router.put("/backups/folder")
def set_backup_folder(body: BackupFolderIn):
    try:
        with db.session() as conn:
            backup.set_folder(conn, body.folder)
            return _backup_info(conn)
    except backup.BackupError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/backups/{name}")
def download_backup(name: str):
    with db.session() as conn:
        try:
            path = backup.path_for(conn, name)
        except backup.BackupError as exc:
            raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, filename=name, media_type="application/octet-stream")


# ---------- extension pairing (called from the ConvoHub page only) ----------

@router.get("/settings/extension")
def extension_pairing_status():
    return extension_pairing.status()


class PairIn(BaseModel):
    id: str | None = None


@router.put("/settings/extension")
def extension_pairing_set(body: PairIn):
    try:
        return extension_pairing.set_paired(body.id)
    except extension_pairing.PairingError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------- shutdown ----------

@router.post("/shutdown")
def shutdown(request: Request):
    """Stop the server (the «خاموش» button and the "stop" desktop shortcut).

    Only accepted from ConvoHub's own page or from local programs: the origin check in main.py rejects
    POSTs from other websites.
    """
    server = getattr(request.app.state, "server", None)
    if server is None:
        raise HTTPException(503, "این نسخه از بیرون اجرا شده (مثلاً با uvicorn مستقیم)؛ از همونجا ببندش.")
    server.should_exit = True
    return {"ok": True}


@router.post("/extension/diagnose")
def extension_diagnose(report: dict, x_convohub_client: str | None = Header(None)):
    """The extension found no messages: keep its structure-only report (no message text) for debugging."""
    _require_extension(x_convohub_client)
    text = json.dumps({"received": time.strftime("%Y-%m-%d %H:%M:%S"), **report}, ensure_ascii=False, indent=1)
    if len(text) > 300_000:
        raise HTTPException(413, "report too large")
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "extension-diagnose.json").write_text(text, encoding="utf-8")
    return {"ok": True}


# ---------- OpenRouter key (entered in the UI; never sent back in full) ----------

@router.get("/settings/key")
def key_status():
    return keystore.status()


class KeyIn(BaseModel):
    key: str = Field(min_length=10, max_length=400)


@router.put("/settings/key")
async def key_save(body: KeyIn):
    key = body.key.strip()
    if any(c.isspace() for c in key) or not key.isascii():
        raise HTTPException(400, "این شبیه کلید OpenRouter نیست (باید با sk-or- شروع بشه).")
    valid, message = await openrouter.check_key(key)
    if valid is False:
        raise HTTPException(400, message)
    keystore.save_key(key)
    return {**keystore.status(), "warning": message or None}


@router.delete("/settings/key")
def key_delete():
    keystore.delete_key()
    return keystore.status()


# ---------- connecting other tools (MCP) and the browser extension ----------

def _mcp_command() -> list[str]:
    if config.FROZEN:
        return [str(config.APP_DIR / "convohub-mcp.exe")]
    return ["uv", "run", "--directory", config.ROOT_DIR.as_posix(), "python", "-m", "convohub.mcp_server"]


def _quote(arg: str) -> str:
    return f'"{arg}"' if any(c in arg for c in ' &()') else arg


@router.get("/integrations")
def integrations():
    cmd = _mcp_command()
    exe, args = cmd[0], cmd[1:]
    line = " ".join(_quote(a) for a in cmd)
    env = {"CONVOHUB_DATA_DIR": str(config.DATA_DIR)} if os.environ.get("CONVOHUB_DATA_DIR") else None
    opencode = {"convohub": {"type": "local", "command": cmd, "enabled": True, "timeout": 120000,
                             **({"environment": env} if env else {})}}
    cline = {"convohub": {"command": exe, "args": args, "disabled": False, "timeout": 120,
                          **({"env": env} if env else {})}}
    hermes_args = (" --args " + " ".join(_quote(a) for a in args)) if args else ""
    env_flag = "".join(f" -e {k}={_quote(v)}" for k, v in (env or {}).items())        # claude mcp add
    hermes_env = (" --env " + " ".join(f"{k}={_quote(v)}" for k, v in env.items())) if env else ""
    return {
        "mcp_command": cmd,
        "claude_code": f"claude mcp add convohub --scope user{env_flag} -- {line}",
        "hermes": f"hermes mcp add convohub --command {_quote(exe)}{hermes_env}{hermes_args}",
        "opencode": json.dumps(opencode, ensure_ascii=False, indent=2),
        "cline": json.dumps(cline, ensure_ascii=False, indent=2),
        "extension_dir": str(config.EXTENSION_DIR),
        "extension_dir_exists": config.EXTENSION_DIR.is_dir(),
        "data_dir": str(config.DATA_DIR),
        "installed": config.FROZEN,
    }


class OpenFolderIn(BaseModel):
    which: str = Field(pattern="^(extension|data)$")


@router.post("/open-folder")
def open_folder(body: OpenFolderIn):
    """Opens the extension or data folder in Windows Explorer (local only; other sites can't call this)."""
    path = config.EXTENSION_DIR if body.which == "extension" else config.DATA_DIR
    if not path.is_dir():
        raise HTTPException(404, f"این پوشه پیدا نشد: {path}")
    if sys.platform != "win32":
        raise HTTPException(400, "فقط روی ویندوز.")
    os.startfile(path)  # noqa: S606 (fixed, known folder)
    return {"ok": True}
