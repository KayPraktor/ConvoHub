// Reads the conversation that is on screen, from the page DOM only.
// Kept free of extension APIs so it can also be tested by injecting it into a page.
(() => {
  const SITES = {
    "gemini.google.com": {
      source: "gemini",
      user: "user-query",
      assistant: "model-response message-content, response-container message-content",
      composer: 'rich-textarea .ql-editor[contenteditable="true"], rich-textarea [contenteditable="true"]',
      title: () => {
        const sel = document.querySelector(
          "conversations-list .conversation.selected .conversation-title, [data-test-id='conversation-title'], share-viewer h1");
        return sel ? sel.innerText : "";
      },
    },
    "chatgpt.com": {
      source: "chatgpt",
      // Three layouts seen in Nov 2026 (innermost match wins, so a bubble inside a turn is used):
      // - logged-in app: [data-user-message-bubble] / [data-markdown-text-style="assistant-message"]
      // - share pages:   <li data-message-role> with [data-user-message-bubble] / [data-assistant-markdown-root]
      // - older app:     [data-message-author-role]
      user: '[data-user-message-bubble], [data-message-role="user"], [data-message-author-role="user"]',
      assistant: '[data-markdown-text-style="assistant-message"], [data-assistant-markdown-root], ' +
        '[data-message-role="assistant"], [data-message-author-role="assistant"]',
      composer: '#prompt-textarea[contenteditable="true"], div.ProseMirror[contenteditable="true"], textarea#prompt-textarea, textarea[id*="composer"]',
      title: () => document.title.replace(/\s*[-|]\s*ChatGPT\s*$/i, ""),
    },
    "claude.ai": {
      source: "claude",
      user: '[data-testid="user-message"]',
      assistant: ".font-claude-response, .font-claude-message",
      composer: 'div.ProseMirror[contenteditable="true"], [data-testid="chat-input"] [contenteditable="true"]',
      title: () => document.title.replace(/\s*[-|]\s*Claude\s*$/i, ""),
    },
    "grok.com": {
      source: "grok",
      user: '[class*="items-end"] .message-bubble',
      assistant: '[class*="items-start"] .message-bubble',
      composer: 'form textarea, div.ProseMirror[contenteditable="true"], form [contenteditable="true"]',
      title: () => document.title.replace(/\s*[-|]\s*Grok\s*$/i, ""),
    },
  };
  const GENERIC_TITLES = /^(gemini|google gemini|chatgpt|claude|grok|new chat|چت جدید)$/i;

  // Citation chips and screen-reader labels ("You said") would otherwise end up in the text.
  const JUNK_CSS = "source-footnote, sources-carousel-inline, source-inline-chip, .cdk-visually-hidden, " +
    ".screen-reader-user-query-label, .sr-only, " +
    // ChatGPT: source chips / copy buttons are <button>s; "Worked for 9s" is the reasoning summary
    "[data-conversation-transcript] button, [data-markdown-text-style] button, [data-chatgpt-copy-reference], " +
    "[data-message-content-controls], [data-cot], " +
    "[data-assistant-reasoning-summary] { display: none !important; }";

  function site() {
    return SITES[location.hostname.replace(/^www\./, "")] || null;
  }

  function innermost(els) {
    return els.filter((e) => !els.some((o) => o !== e && e.contains(o)));
  }

  function textOf(e) {
    const lines = e.querySelectorAll(".query-text-line"); // Gemini collapses long user messages
    if (lines.length) return Array.from(lines).map((l) => l.textContent.trim()).join("\n");
    return e.innerText || "";
  }

  // querySelectorAll that also looks inside (open) shadow roots: some chat apps render messages
  // inside web components, where a plain document.querySelectorAll can't see them.
  function deepAll(selector, root = document) {
    const out = Array.from(root.querySelectorAll(selector));
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) out.push(...deepAll(selector, el.shadowRoot));
    }
    return out;
  }

  function nodes(s) {
    const u = innermost(deepAll(s.user));
    const a = innermost(deepAll(s.assistant));
    const all = u.map((e) => ["user", e]).concat(a.map((e) => ["assistant", e]));
    all.sort((x, y) => (x[1].compareDocumentPosition(y[1]) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
    return all;
  }

  function extract() {
    const s = site();
    if (!s) return null;
    // The style is added and removed in the same task, so the page never repaints with it.
    const style = document.createElement("style");
    style.textContent = JUNK_CSS;
    document.head.appendChild(style);
    let messages;
    try {
      messages = [];
      for (const [role, e] of nodes(s)) {
        const content = textOf(e).trim();
        if (!content) continue;
        const prev = messages[messages.length - 1];
        if (prev && prev.role === role) prev.content += "\n\n" + content; // one turn split in parts
        else messages.push({ role, content });
      }
    } finally {
      style.remove();
    }
    let title = (s.title() || "").trim();
    if (GENERIC_TITLES.test(title)) title = "";
    return { source: s.source, url: location.href, title, messages };
  }

  function countTurns() {
    const s = site();
    return s ? nodes(s).length : 0;
  }

  function scrollParent(el) {
    for (let p = el && el.parentElement; p; p = p.parentElement) {
      const oy = getComputedStyle(p).overflowY;
      if ((oy === "auto" || oy === "scroll") && p.scrollHeight > p.clientHeight + 10) return p;
    }
    return document.scrollingElement;
  }

  // Long chats only keep the latest turns in the page; older ones load when you scroll up.
  async function loadFullHistory(onProgress) {
    const s = site();
    if (!s) return;
    const first = nodes(s)[0];
    if (!first) return;
    const box = scrollParent(first[1]);
    const bottom = box.scrollTop;
    let last = -1;
    let stable = 0;
    for (let i = 0; i < 60 && stable < 3; i++) {
      box.scrollTop = 0;
      await new Promise((r) => setTimeout(r, 700));
      const n = countTurns();
      stable = n === last ? stable + 1 : 0;
      last = n;
      if (onProgress) onProgress(n);
    }
    box.scrollTop = box.scrollHeight || bottom;
  }

  // When no messages are found: a summary of the page STRUCTURE only (tag/attribute names, counts and
  // short role-like attribute values), never message text, so the selectors can be fixed.
  function diagnose() {
    const s = site();
    const tags = {}, attrs = {}, values = {};
    let shadows = 0;
    const bump = (o, k) => { o[k] = (o[k] || 0) + 1; };
    const visit = (root) => {
      for (const e of root.querySelectorAll("*")) {
        const tag = e.tagName.toLowerCase();
        if (tag.includes("-") || ["article", "section", "li", "ol", "ul", "main", "iframe"].includes(tag)) bump(tags, tag);
        for (const a of e.attributes) {
          if (!a.name.startsWith("data-") && a.name !== "role") continue;
          bump(attrs, a.name);
          if (/role|author|message|turn|testid|speaker|sender/.test(a.name) && a.value.length <= 40) {
            bump(values, `${a.name}=${a.value.replace(/[0-9a-f]{8,}|\d+/gi, "#")}`);
          }
        }
        if (e.shadowRoot) { shadows++; visit(e.shadowRoot); }
      }
    };
    visit(document);
    const top = (o, n) => Object.fromEntries(Object.entries(o).sort((x, y) => y[1] - x[1]).slice(0, n));
    return {
      host: location.hostname,
      path: location.pathname.replace(/[0-9a-f-]{8,}/gi, "<id>"),
      iframes: Array.from(document.querySelectorAll("iframe")).map((f) => {
        try { return new URL(f.src, location.href).host; } catch { return "?"; }
      }),
      shadowRoots: shadows,
      bodyTextLength: document.body ? document.body.innerText.length : 0,
      matches: s ? { user: deepAll(s.user).length, assistant: deepAll(s.assistant).length } : null,
      tags: top(tags, 40),
      attributes: top(attrs, 100),
      roleLikeValues: top(values, 100),
    };
  }

  // ---------- handoff: put a text from ConvoHub into the message box (the user presses Send) ----------

  // Editors keep hidden helper boxes next to the real one (Gemini's Quill has a 0-width ".ql-clipboard"),
  // so "visible" means a real size on screen, and the biggest match wins.
  const visible = (e) => {
    if (!e || !e.isConnected || e.closest(".ql-clipboard")) return false;
    const r = e.getBoundingClientRect();
    return r.width > 40 && r.height > 10;
  };

  function composer() {
    const s = site();
    const pick = (sel) => {
      const found = Array.from(document.querySelectorAll(sel)).filter(visible);
      const area = (e) => { const r = e.getBoundingClientRect(); return r.width * r.height; };
      return found.sort((a, b) => area(b) - area(a))[0] || null;
    };
    return (s && s.composer && pick(s.composer)) || pick('textarea, [contenteditable="true"]');
  }

  const boxText = (box) => (box.tagName === "TEXTAREA" ? box.value : box.innerText) || "";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Returns {ok, via}. ok is false if no message box was found or the text didn't show up in it.
  async function insertIntoComposer(text) {
    const box = composer();
    if (!box) return { ok: false, reason: "no-box" };
    box.focus();
    const probe = text.trim().slice(0, 30);
    const landed = () => boxText(box).includes(probe);
    if (box.tagName === "TEXTAREA") {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
      setter.call(box, (box.value.trim() ? box.value + "\n\n" : "") + text);
      box.dispatchEvent(new Event("input", { bubbles: true }));
      return { ok: landed(), via: "value" };
    }
    // Caret at the end, then let the site's own editor take it as a paste (long texts may become an
    // attachment, as with a real paste). If the site ignores the paste, type it in.
    const range = document.createRange();
    range.selectNodeContents(box);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    const before = boxText(box).length;
    let handled = false;
    try {
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      handled = !box.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    } catch {}
    if (handled) {
      await sleep(400);
      // Became an attachment (the box barely changed but something was added) or landed as text: done.
      if (landed() || boxText(box).length !== before) return { ok: true, via: "paste" };
    }
    box.focus();
    document.execCommand("insertText", false, text);
    await sleep(150);
    return { ok: landed(), via: "insertText" };
  }

  window.convohubExtract = { site, extract, countTurns, loadFullHistory, diagnose, composer, insertIntoComposer };
})();
