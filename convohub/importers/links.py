"""Import from public share links using a headless browser.

Uses the Chrome or Edge already installed on Windows (no separate browser download).
The browser starts with an empty profile: no cookies, no login (CLAUDE.md hard constraint #1).
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


# host regex, path regex, source
_PATTERNS = [
    (r"gemini\.google\.com", r"^/share/[\w-]+", "gemini"),
    (r"g\.co", r"^/gemini/share/[\w-]+", "gemini"),
    (r"share\.gemini\.google", r"^/[\w-]+", "gemini"),  # newer short share links
    (r"(www\.)?grok\.com", r"^/share/[\w-]+", "grok"),
    (r"(www\.)?claude\.ai", r"^/share/[\w-]+", "claude"),
    (r"(www\.)?chatgpt\.com", r"^/share/[\w-]+", "chatgpt"),
    (r"chat\.openai\.com", r"^/share/[\w-]+", "chatgpt"),
]

NAV_TIMEOUT_MS = 30_000
CONTENT_WAIT_MS = 25_000


class LinkImportError(Exception):
    pass


@dataclass
class LinkResult:
    source: str
    url: str
    title: str
    raw_text: str
    messages: list[dict] = field(default_factory=list)


def match_link(url: str) -> str | None:
    """Return the source name if this is a supported share link, else None."""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return None
    if p.scheme not in ("http", "https"):
        return None
    for host, path, source in _PATTERNS:
        if re.fullmatch(host, p.hostname or "") and re.match(path, p.path):
            return source
    return None


# Runs in the page. Tries known per-site selectors for user/assistant turns; falls back to page text.
_EXTRACT_JS = r"""
() => {
  // Hide citation chips and screen-reader labels ("You said") so innerText skips them.
  const style = document.createElement('style');
  style.textContent = 'source-footnote, sources-carousel-inline, source-inline-chip, .cdk-visually-hidden,'
    + ' .screen-reader-user-query-label,'
    // ChatGPT: source chips and copy buttons are <button>s; "Worked for 9s" is the reasoning summary
    + ' [data-conversation-transcript] button, [data-markdown-text-style] button, [data-chatgpt-copy-reference],'
    + ' [data-message-content-controls], [data-cot],'
    + ' [data-assistant-reasoning-summary] { display: none !important; }';
  document.head.appendChild(style);

  // Gemini collapses long user messages; its .query-text-line paragraphs still hold the full text.
  const textOf = (e) => {
    const lines = e.querySelectorAll('.query-text-line');
    if (lines.length) return Array.from(lines).map(l => l.textContent.trim()).join('\n');
    return e.innerText || '';
  };
  const heading = document.querySelector('share-viewer h1, .share-title-section h1');
  const title = heading ? heading.innerText : document.title;

  const rules = [
    // ChatGPT, Nov 2026: share pages use <li data-message-role> + [data-assistant-markdown-root];
    // the logged-in app uses [data-markdown-text-style="assistant-message"]. User bubbles are the same.
    { user: '[data-user-message-bubble], [data-message-role="user"]',
      assistant: '[data-markdown-text-style="assistant-message"], [data-assistant-markdown-root], [data-message-role="assistant"]' },
    // ChatGPT (older layout)
    { user: '[data-message-author-role="user"]', assistant: '[data-message-author-role="assistant"]' },
    // Gemini (share pages use response-container, the app uses model-response)
    { user: 'user-query', assistant: 'message-content' },
    // Claude
    { user: '[data-testid="user-message"]', assistant: '.font-claude-response, .font-claude-message' },
    // Grok (user bubbles are right-aligned with items-end, replies left with items-start)
    { user: '[class*="items-end"] .message-bubble', assistant: '[class*="items-start"] .message-bubble' },
  ];
  const innermost = (els) => els.filter(e => !els.some(o => o !== e && e.contains(o)));
  for (const r of rules) {
    const u = innermost(Array.from(document.querySelectorAll(r.user)));
    const a = innermost(Array.from(document.querySelectorAll(r.assistant)));
    if (!u.length || !a.length) continue;
    const all = u.map(e => ['user', e]).concat(a.map(e => ['assistant', e]));
    all.sort((x, y) => (x[1].compareDocumentPosition(y[1]) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
    const messages = [];
    for (const [role, e] of all) {
      const content = textOf(e).trim();
      if (!content) continue;
      const prev = messages[messages.length - 1];
      if (prev && prev.role === role) prev.content += '\n\n' + content;  // one turn split in parts
      else messages.push({ role, content });
    }
    if (messages.length) return { title, messages, text: null };
  }
  const body = document.body ? document.body.innerText : '';
  return { title, messages: [], text: body };
}
"""

_WAIT_SELECTOR = (
    '[data-message-role], [data-message-author-role], user-query, model-response, message-content, '
    '[data-testid="user-message"], .font-claude-response, .message-bubble'
)

_BOT_WALL = re.compile(r"cloudflare|ray id|just a moment|verify you are human|تایید امنیتی|چند لحظه صبر", re.I)


def fetch_link(url: str) -> LinkResult:
    """Blocking. Call from a worker thread."""
    source = match_link(url)
    if not source:
        raise LinkImportError(
            "این لینک رو نمی‌شناسم. لینک share از Gemini، Grok، Claude یا ChatGPT بده "
            "(مثلاً https://gemini.google.com/share/...)."
        )
    try:
        from playwright.sync_api import Error as PWError
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise LinkImportError("Playwright نصب نیست. یه بار `uv sync` رو اجرا کن.") from exc

    with sync_playwright() as pw:
        browser = _launch(pw, PWError)
        try:
            page = browser.new_page(locale="fa-IR")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            except PWTimeout as exc:
                raise LinkImportError(
                    "صفحه توی ۳۰ ثانیه باز نشد. شاید این سایت بدون VPN باز نمیشه؛ VPN رو چک کن و دوباره امتحان کن."
                ) from exc
            except PWError as exc:
                raise LinkImportError(
                    "نتونستم صفحه رو باز کنم (شبکه یا آدرس). شاید این سایت بدون VPN باز نمیشه."
                ) from exc

            try:
                page.wait_for_selector(_WAIT_SELECTOR, timeout=CONTENT_WAIT_MS, state="attached")
                page.wait_for_load_state("networkidle", timeout=CONTENT_WAIT_MS)
            except PWTimeout:
                pass  # take whatever has rendered

            final_host = urlparse(page.url).hostname or ""
            if "accounts.google.com" in final_host or "/login" in page.url or "/auth" in page.url:
                raise LinkImportError("این لینک لاگین می‌خواد؛ احتمالاً خصوصیه یا پاک شده. لینک share عمومی بده.")

            data = page.evaluate(_EXTRACT_JS)
        finally:
            browser.close()

    messages = data.get("messages") or []
    if not messages:
        # We only accept pages where we found real user/assistant turns. Otherwise we'd save
        # a landing page, a "not found" page or a bot check as if it were the conversation.
        page_text = (data.get("title") or "") + "\n" + (data.get("text") or "")
        if _BOT_WALL.search(page_text):
            raise LinkImportError(
                "این سایت جلوی مرورگر خودکار رو گرفت (بررسی ضدربات). فعلاً متن مکالمه رو کپی و paste کن."
            )
        raise LinkImportError(
            "توی این صفحه مکالمه‌ای پیدا نشد. یا لینک پاک شده/خصوصیه، یا ظاهر سایت عوض شده. "
            "فعلاً متن مکالمه رو کپی و paste کن."
        )

    from ..library import render_messages
    return LinkResult(source=source, url=url.strip(), title=_clean_title(data.get("title") or ""),
                      raw_text=render_messages(messages), messages=messages)


def _launch(pw, PWError):
    """The system's own Chrome or Edge (the installed app ships no browser of its own)."""
    from .. import config
    last = None
    channels = ("chrome", "msedge") if config.FROZEN else ("chrome", "msedge", None)
    for channel in channels:
        try:
            kwargs = {"headless": True}
            if channel:
                kwargs["channel"] = channel
            return pw.chromium.launch(**kwargs)
        except PWError as exc:
            last = exc
    raise LinkImportError(
        "برای ایمپورت از لینک، Chrome یا Microsoft Edge باید روی این سیستم نصب باشه و هیچ‌کدوم پیدا نشد. "
        "یکی‌شون رو نصب کن (Edge معمولاً همراه ویندوزه)، یا متن مکالمه رو کپی و paste کن."
    ) from last


def _clean_title(title: str) -> str:
    title = re.sub(r"\s*[-|‎]\s*(Gemini|ChatGPT|Claude|Grok)\s*$", "", title.strip(), flags=re.I)
    if title.lower() in ("gemini", "chatgpt", "claude", "grok", "google gemini", ""):
        return ""
    return title
