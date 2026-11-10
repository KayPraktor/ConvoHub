"""OpenRouter client: model list and streaming chat completions."""

import json
import time
from collections.abc import AsyncIterator

import httpx

from . import config

BASE_URL = "https://openrouter.ai/api/v1"
_HEADERS = {"X-Title": "ConvoHub"}
_TIMEOUT = httpx.Timeout(connect=15.0, read=180.0, write=60.0, pool=15.0)

_models_cache: tuple[float, list[dict]] | None = None
_MODELS_TTL = 3600


class OpenRouterError(Exception):
    """An error with a message that can be shown to the user (in Persian)."""


def _auth_headers() -> dict:
    key = config.openrouter_key()
    if not key:
        raise OpenRouterError("کلید OpenRouter توی فایل .env نیست. کلید رو بذار و برنامه رو دوباره اجرا کن.")
    return {**_HEADERS, "Authorization": f"Bearer {key}"}


def _network_error(exc: Exception) -> OpenRouterError:
    return OpenRouterError(
        "به OpenRouter وصل نشدم. اینترنت یا VPN رو چک کن و دوباره امتحان کن. "
        f"({type(exc).__name__})"
    )


_STATUS_MESSAGES = {
    400: "درخواست رو قبول نکرد",
    401: "کلید OpenRouter معتبر نیست",
    402: "اعتبار حساب OpenRouter تموم شده",
    403: "این درخواست اجازه نداره (شاید فیلتر محتوای مدل)",
    404: "این مدل پیدا نشد",
    408: "مدل دیر جواب داد",
    413: "متن برای این مدل زیادی بلنده",
    429: "تعداد درخواست‌ها زیاد شده؛ کمی صبر کن",
    502: "سرویس‌دهنده‌ی مدل در دسترس نیست",
    503: "هیچ سرویس‌دهنده‌ای برای این مدل در دسترس نیست",
}


def _status_error(status: int, body: str) -> OpenRouterError:
    detail = ""
    try:
        detail = json.loads(body).get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        pass
    base = _STATUS_MESSAGES.get(status, f"خطای OpenRouter (کد {status})")
    return OpenRouterError(f"{base}. {detail}".strip())


async def list_models(force: bool = False) -> list[dict]:
    """Models from OpenRouter, trimmed to what the UI needs. Cached for an hour."""
    global _models_cache
    if not force and _models_cache and time.time() - _models_cache[0] < _MODELS_TTL:
        return _models_cache[1]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            res = await client.get(f"{BASE_URL}/models", headers=_HEADERS)
    except httpx.HTTPError as exc:
        raise _network_error(exc) from exc
    if res.status_code != 200:
        raise _status_error(res.status_code, res.text)

    models = []
    for m in res.json().get("data", []):
        if m["id"].endswith(":batch"):
            continue  # batch-only variants can't stream interactive chat
        pricing = m.get("pricing") or {}
        modality = (m.get("architecture") or {}).get("output_modalities") or ["text"]
        if "text" not in modality:
            continue
        models.append({
            "id": m["id"],
            "name": m.get("name") or m["id"],
            "context_length": m.get("context_length") or 0,
            "prompt_price": _price(pricing.get("prompt")),          # USD per token
            "completion_price": _price(pricing.get("completion")),  # USD per token
            "cache_read_price": _price(pricing.get("input_cache_read")),
            "tools": "tools" in (m.get("supported_parameters") or []),  # can be used in agent mode
        })
    models.sort(key=lambda m: m["name"].lower())
    _models_cache = (time.time(), models)
    return models


def _price(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def stream_chat(model: str, messages: list[dict], max_tokens: int | None = None,
                      tools: list[dict] | None = None) -> AsyncIterator[dict]:
    """Yield {'type': 'delta', 'text'} events, then one {'type': 'usage', ...} event.

    With tools: also one {'type': 'tool_calls', 'calls': [...], 'reasoning_details': [...]} event at the end
    when the model asked for tools. reasoning_details must be sent back with the assistant message
    (Gemini needs its "thought signatures" to continue after a tool call).

    Raises OpenRouterError for problems that should be shown to the user.
    """
    payload = {"model": model, "messages": messages, "stream": True, "usage": {"include": True}}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = tools
    headers = _auth_headers()
    calls: dict[int, dict] = {}
    reasoning_details: list = []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload, headers=headers) as res:
                if res.status_code != 200:
                    body = (await res.aread()).decode("utf-8", "replace")
                    raise _status_error(res.status_code, body)
                async for line in res.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # blank lines and ": OPENROUTER PROCESSING" keep-alives
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if "error" in chunk:
                        err = chunk["error"]
                        raise OpenRouterError(f"مدل وسط جواب خطا داد: {err.get('message', err)}")
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        text = delta.get("content")
                        if text:
                            yield {"type": "delta", "text": text}
                        for tc in delta.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", len(calls)), {"id": "", "name": "", "arguments": ""})
                            slot["id"] = tc.get("id") or slot["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
                        if delta.get("reasoning_details"):
                            reasoning_details.extend(delta["reasoning_details"])
                    if chunk.get("usage"):
                        u = chunk["usage"]
                        yield {
                            "type": "usage",
                            "prompt_tokens": u.get("prompt_tokens"),
                            "completion_tokens": u.get("completion_tokens"),
                            "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                            "cost": u.get("cost"),
                        }
    except httpx.HTTPError as exc:
        raise _network_error(exc) from exc
    if calls:
        ordered = [calls[i] for i in sorted(calls)]
        for n, c in enumerate(ordered):
            c["id"] = c["id"] or f"call_{n}"
        yield {"type": "tool_calls", "calls": ordered, "reasoning_details": reasoning_details}


async def complete(model: str, messages: list[dict], max_tokens: int | None = None) -> tuple[str, dict]:
    """Non-interactive call built on the stream (so long calls don't hit a single read timeout)."""
    parts, usage = [], {}
    async for ev in stream_chat(model, messages, max_tokens=max_tokens):
        if ev["type"] == "delta":
            parts.append(ev["text"])
        elif ev["type"] == "usage":
            usage = ev
    return "".join(parts), usage


async def check_key(key: str) -> tuple[bool | None, str]:
    """Ask OpenRouter whether a key works. (True, ""), (False, reason) or (None, reason) if we couldn't tell."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            res = await client.get(f"{BASE_URL}/key", headers={**_HEADERS, "Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        return None, f"به OpenRouter وصل نشدم ({type(exc).__name__})؛ کلید ذخیره شد ولی بررسی نشد."
    if res.status_code == 200:
        return True, ""
    if res.status_code in (401, 403):
        return False, "OpenRouter این کلید رو قبول نکرد. دوباره از سایت OpenRouter کپی‌اش کن."
    return None, f"OpenRouter جواب غیرمنتظره داد (کد {res.status_code})؛ کلید ذخیره شد ولی بررسی نشد."
