"""Multi-model mode (SPEC §5.3): one question to several models in parallel, optional orchestrator synthesis."""

import asyncio
from collections.abc import AsyncIterator

from . import openrouter, prompting

MAX_MODELS = 4


async def run(models: list[str], orchestrator: str | None, messages: list[dict], state: dict) -> AsyncIterator[dict]:
    """Yields UI events tagged with a slot (0..n-1 for the panel, "s" for the synthesis).

    state["answers"] collects {slot, model, text, usage, error} for saving, in slot order.
    """
    answers = state.setdefault("answers", [])
    yield {"type": "panel_start", "models": models, "orchestrator": orchestrator}

    queue: asyncio.Queue = asyncio.Queue()
    results = [{"slot": i, "model": m, "text": "", "usage": {}, "error": None} for i, m in enumerate(models)]

    async def one(i: int, model: str):
        try:
            async for ev in openrouter.stream_chat(model, list(messages)):
                if ev["type"] == "delta":
                    results[i]["text"] += ev["text"]
                    await queue.put({"type": "delta", "slot": i, "text": ev["text"]})
                elif ev["type"] == "usage":
                    results[i]["usage"] = ev
        except openrouter.OpenRouterError as exc:
            results[i]["error"] = str(exc)
        except Exception as exc:  # one broken model must not stop the others
            results[i]["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            await queue.put({"type": "slot_done", "slot": i, "usage": results[i]["usage"],
                             "error": results[i]["error"]})

    tasks = [asyncio.create_task(one(i, m)) for i, m in enumerate(models)]
    try:
        remaining = len(tasks)
        while remaining:
            ev = await queue.get()
            if ev["type"] == "slot_done":
                remaining -= 1
            yield ev
    finally:
        for t in tasks:
            t.cancel()  # the user pressed stop: don't keep paying for answers nobody reads
        answers.extend(results)

    good = [(r["model"], r["text"]) for r in results if r["text"].strip()]
    if not orchestrator or not good:
        return
    synth = {"slot": "s", "model": orchestrator, "text": "", "usage": {}, "error": None, "synthesis": True}
    answers.append(synth)
    yield {"type": "synth_start", "model": orchestrator}
    try:
        async for ev in openrouter.stream_chat(orchestrator, prompting.synthesis_messages(messages, good)):
            if ev["type"] == "delta":
                synth["text"] += ev["text"]
                yield {"type": "delta", "slot": "s", "text": ev["text"]}
            elif ev["type"] == "usage":
                synth["usage"] = ev
    except openrouter.OpenRouterError as exc:
        synth["error"] = str(exc)
    yield {"type": "slot_done", "slot": "s", "usage": synth["usage"], "error": synth["error"]}
