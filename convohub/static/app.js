"use strict";

// ---------- helpers ----------

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...children) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined) e.append(c);
  return e;
};

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers = { "Content-Type": "application/json" };
    delete init.json;
  }
  const res = await fetch("/api" + path, init);
  if (!res.ok) {
    let msg = t("common.error_status", { status: res.status });
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// Numbers in the interface language's digits (the name is historical: it formats for I18N.locale).
const fa = (n) => Number(n || 0).toLocaleString(I18N.locale);
// Counted phrases: English needs singular and plural, so such texts have "key.one" and "key.other"
// (in Persian both are the same). {n} is the formatted number.
const tn = (key, n, vars = {}) => t(`${key}.${Number(n) === 1 ? "one" : "other"}`, { n: fa(n), ...vars });
const SOURCE_NAMES = { gemini: "Gemini", claude: "Claude", grok: "Grok", chatgpt: "ChatGPT", native: t("source.native"), other: t("source.other") };
const METHOD_NAMES = { paste: "paste", link: t("method.link"), file: t("method.file"), extension: t("method.extension"), native: "" };
// Line icons from the sprite at the top of index.html (they take the text colour).
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ic");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}
const badge = (source) => el("span", { class: `badge ${source}` }, SOURCE_NAMES[source] || source);

function fmtDate(s) {
  if (!s) return "";
  const d = new Date(s.replace(" ", "T") + "Z");
  return d.toLocaleString(I18N.locale, { dateStyle: "medium", timeStyle: "short" });
}

function fmtCost(usd) {
  if (usd === null || usd === undefined) return "";
  if (usd === 0) return t("cost.free");
  if (usd < 0.001) return "$" + usd.toFixed(5);
  return "$" + usd.toFixed(usd < 0.1 ? 4 : 3);
}

const store = {
  get(k, d = null) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

// Minimal, safe markdown: escape first, then add a few formats.
function renderMarkdown(src) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const blocks = src.split(/```/);
  let html = "";
  blocks.forEach((block, i) => {
    if (i % 2 === 1) {
      const code = block.replace(/^[\w+-]*\n/, "");
      html += `<pre><code>${esc(code)}</code></pre>`;
      return;
    }
    const lines = esc(block).split("\n");
    let list = null;
    let para = [];
    const flushPara = () => { if (para.length) { html += `<p>${para.join("<br>")}</p>`; para = []; } };
    const flushList = () => { if (list) { html += `</${list}>`; list = null; } };
    for (const raw of lines) {
      const line = inline(raw);
      let m;
      if ((m = raw.match(/^(#{1,4})\s+(.*)$/))) {
        flushPara(); flushList();
        html += `<h${m[1].length + 1}>${inline(m[2])}</h${m[1].length + 1}>`;
      } else if ((m = raw.match(/^\s*[-*•]\s+(.*)$/))) {
        flushPara();
        if (list !== "ul") { flushList(); html += "<ul>"; list = "ul"; }
        html += `<li>${inline(m[1])}</li>`;
      } else if ((m = raw.match(/^\s*[\d\u06F0-\u06F9]+[.)]\s+(.*)$/))) { // also Persian digits
        flushPara();
        if (list !== "ol") { flushList(); html += "<ol>"; list = "ol"; }
        html += `<li>${inline(m[1])}</li>`;
      } else if (/^\s*([-*_])\1{2,}\s*$/.test(raw)) {
        flushPara(); flushList();
        html += "<hr>";
      } else if ((m = raw.match(/^\s*&gt;\s?(.*)$/))) { // lines are already escaped
        flushPara(); flushList();
        html += `<blockquote>${inline(m[1])}</blockquote>`;
      } else if (!raw.trim()) {
        flushPara(); flushList();
      } else {
        flushList();
        para.push(line);
      }
    }
    flushPara(); flushList();
  });
  return html;

  function inline(s) {
    return s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
  }
}

// ---------- in-page dialogs ----------
// Native alert/confirm/prompt can be silently blocked (e.g. in an embedded browser), which made delete and
// rename do nothing. These draw the dialog inside the page instead.

function uiDialog({ message, input = null, ok = t("common.ok"), cancel = t("common.cancel"), danger = false }) {
  const dlg = $("#ui-dialog");
  const field = $("#ui-input");
  const okBtn = $("#ui-ok");
  const cancelBtn = $("#ui-cancel");
  $("#ui-message").textContent = message;
  field.hidden = input === null;
  field.value = input ?? "";
  okBtn.textContent = ok;
  okBtn.classList.toggle("danger-fill", danger);
  cancelBtn.hidden = cancel === null;
  cancelBtn.textContent = cancel || "";
  return new Promise((resolve) => {
    const done = (value) => {
      dlg.removeEventListener("close", onClose);
      cancelBtn.onclick = null;
      resolve(value);
    };
    const onClose = () => done(dlg.returnValue === "ok" ? (input === null ? true : field.value) : (input === null ? false : null));
    dlg.addEventListener("close", onClose);
    cancelBtn.onclick = () => { dlg.returnValue = "cancel"; dlg.close(); };
    dlg.returnValue = "";
    dlg.showModal();
    (input === null ? okBtn : field).focus();
    if (input !== null) field.select();
  });
}
const notify = (message) => uiDialog({ message, cancel: null });
const askConfirm = (message, ok = t("common.ok"), danger = false) => uiDialog({ message, ok, danger });
const askText = (message, value = "") => uiDialog({ message, input: value });

// ---------- state ----------

const state = {
  conversations: [],
  models: [],
  current: null, // {type: 'conv'|'chat', id}
  streaming: null, // AbortController
  memory: { enabled: true, items: [] },
};

// ---------- sidebar ----------

async function refreshList() {
  const q = $("#search").value.trim();
  const items = await api("/conversations" + (q ? "?q=" + encodeURIComponent(q) : ""));
  if (!q) state.conversations = items;
  renderList(items, !!q);
}

function renderList(items, isSearch) {
  const lists = $("#lists");
  lists.innerHTML = "";
  const chats = items.filter((c) => c.source === "native");
  const convs = items.filter((c) => c.source !== "native");
  const item = (c) => {
    const del = el("button", {
      class: "item-del", type: "button", title: t("common.delete"),
      onclick: (e) => { e.stopPropagation(); deleteConv(c).catch(showFatal); },
    }, icon("trash"));
    const li = el("li", { onclick: () => (c.source === "native" ? openChat(c.id) : openConversation(c.id)) },
      el("span", { class: "item-title", title: c.title, dir: "auto" }, c.title),
      el("span", { class: "item-meta" },
        c.source !== "native" ? badge(c.source) : null,
        c.source !== "native" ? (c.chars < 1000 ? t("list.chars", { n: fa(c.chars) }) : t("list.chars_k", { n: fa(Math.round(c.chars / 1000)) })) : fmtDate(c.updated_at)),
      c.snippet ? el("span", { class: "snippet" }, c.snippet) : null,
      del);
    if (state.current && state.current.id === c.id) li.classList.add("active");
    return li;
  };
  const section = (title, arr, empty) => {
    lists.append(el("h3", {}, title));
    lists.append(arr.length ? el("ul", {}, arr.map(item)) : empty);
  };
  if (isSearch && !items.length) {
    lists.append(el("div", { class: "side-empty" }, t("list.no_results")));
    return;
  }
  section(t("list.my_chats"), chats, el("div", { class: "side-empty" },
    t("list.chats_empty"),
    el("div", {}, el("button", { onclick: () => newChat().catch(showFatal) }, t("side.new_chat")))));
  section(t("list.library"), convs, el("div", { class: "side-empty" },
    t("list.library_empty"),
    el("div", {}, el("button", { onclick: () => $("#btn-import").click() }, t("side.import")))));
}

// What the main area shows when nothing is open: the next steps, depending on what exists already.
function showWelcome() {
  const hasLibrary = state.conversations.some((c) => c.source !== "native");
  const hasChat = state.conversations.some((c) => c.source === "native");
  const hasKey = state.keySet;
  const step = (n, title, text, done) => el("li", {},
    el("span", { class: "n" }, done ? "✓" : fa(n)), el("div", {}, el("b", {}, title), el("span", {}, text)));
  $("#view").replaceChildren(el("div", { class: "scroll" }, el("div", { class: "welcome" },
    el("h2", {}, t("welcome.hello")),
    el("p", {}, t("welcome.lead")),
    el("ol", { class: "steps" },
      step(1, t("welcome.step1_title"), t("welcome.step1_text"), hasKey),
      step(2, t("welcome.step2_title"), t("welcome.step2_text"), hasLibrary),
      step(3, t("welcome.step3_title"), t("welcome.step3_text"), hasChat),
      step(4, t("welcome.step4_title"), t("welcome.step4_text"), false)),
    el("div", { class: "cta" },
      hasKey ? null : el("button", { class: "primary", onclick: openKeyDialog }, t("welcome.enter_key")),
      el("button", { class: hasKey && !hasLibrary ? "primary" : "", onclick: () => $("#btn-import").click() }, t("side.import")),
      el("button", { class: hasKey && hasLibrary ? "primary" : "", onclick: () => newChat().catch(showFatal) }, t("side.new_chat")),
      el("button", { onclick: openConnect }, t("welcome.connect"))))));
}

let searchTimer;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => refreshList().catch(showFatal), 250);
});

function showFatal(err) {
  console.error(err);
  notify(err.message || String(err));
}

// ---------- conversation view ----------

async function openConversation(id) {
  closeNav();
  stopStreaming();
  state.current = { type: "conv", id };
  refreshList().catch(() => {});
  const conv = await api(`/conversations/${id}`);
  const view = $("#view");
  view.innerHTML = "";

  const title = el("h1", { title: t("common.click_to_rename"), onclick: () => renameConv(conv) }, conv.title);
  const actions = el("div", { class: "actions" },
    el("button", { class: "primary", onclick: () => newChat([{ id: conv.id, use_summary: false }]) }, t("conv.chat_with")),
    el("button", { onclick: () => renameConv(conv) }, t("common.rename")),
    conv.import_method === "link" ? el("button", { onclick: (e) => refreshLink(conv, e.target) }, t("conv.reread")) : null,
    el("button", { onclick: (e) => summarize(conv, e.target) }, conv.summary ? t("conv.resummarize") : t("conv.summarize")),
    el("button", { onclick: (e) => extractMemory(conv, e.currentTarget), title: t("conv.memory_title") },
      icon("memory"), t("conv.memory_btn")),
    el("button", { class: "danger", onclick: () => deleteConv(conv) }, t("common.delete")));

  const meta = el("div", { class: "meta" },
    badge(conv.source),
    t("conv.meta_import", { method: METHOD_NAMES[conv.import_method] || conv.import_method, date: fmtDate(conv.created_at) }),
    conv.updated_at !== conv.created_at ? t("conv.meta_updated", { date: fmtDate(conv.updated_at) }) : "",
    t("conv.meta_size", { chars: fa(conv.raw_text.length), tokens: fa(conv.tokens) }),
    conv.source_url ? el("div", { dir: "ltr" }, el("a", { href: conv.source_url, target: "_blank", rel: "noreferrer" }, conv.source_url)) : null);

  const body = el("div", { class: "scroll" }, meta);
  if (conv.import_method === "link") {
    body.append(el("div", { class: "notice" },
      t("conv.link_notice")));
  }
  if (conv.import_method === "extension") {
    body.append(el("div", { class: "meta" }, t("conv.ext_note")));
  }
  if (conv.summary) {
    const det = el("details", { class: "summary" },
      el("summary", {}, t("conv.summary_head", { tokens: fa(conv.summary_tokens), model: conv.summary_model })),
      el("div", { class: "msg" }));
    det.lastChild.innerHTML = renderMarkdown(conv.summary);
    body.append(det);
  }
  body.append(el("div", { class: "transcript" }, conv.raw_text));

  view.append(el("div", { class: "view-header" }, title, actions), body);
}

async function renameConv(conv) {
  const txt = await askText(t("conv.rename_prompt"), conv.title);
  if (!txt || !txt.trim() || txt === conv.title) return;
  await api(`/conversations/${conv.id}`, { method: "PATCH", json: { title: txt.trim() } });
  conv.source === "native" ? openChat(conv.id) : openConversation(conv.id);
}

async function deleteConv(conv) {
  const question = conv.source === "native" ? "conv.delete_chat_confirm" : "conv.delete_conv_confirm";
  if (!(await askConfirm(t(question, { title: conv.title }), t("common.delete_ok"), true))) return;
  await api(`/conversations/${conv.id}`, { method: "DELETE" });
  if (state.current && state.current.id === conv.id) {
    stopStreaming();
    state.current = null;
    showWelcome();
  }
  refreshList();
}

async function refreshLink(conv, btn) {
  btn.disabled = true;
  btn.replaceChildren(el("span", { class: "spinner" }), " " + t("conv.reading"));
  try {
    await api(`/conversations/${conv.id}/refresh`, { method: "POST" });
    openConversation(conv.id);
  } catch (err) {
    notify(err.message);
    btn.disabled = false;
    btn.textContent = t("conv.reread");
  }
}

async function summarize(conv, btn) {
  const model = store.get("model");
  if (!model) { notify(t("conv.need_model_summary")); return; }
  if (!(await askConfirm(t("conv.summary_confirm", { model, tokens: fa(conv.tokens) }), t("conv.summary_ok")))) return;
  btn.disabled = true;
  btn.replaceChildren(el("span", { class: "spinner" }), " " + t("conv.summarizing"));
  try {
    await api(`/conversations/${conv.id}/summarize`, { method: "POST", json: { model } });
    openConversation(conv.id);
  } catch (err) {
    notify(err.message);
    btn.disabled = false;
    btn.textContent = t("conv.summarize");
  }
}

// ---------- chat view ----------

async function newChat(context = []) {
  const { id } = await api("/chats", { method: "POST", json: { model: store.get("model"), context } });
  await refreshList();
  openChat(id);
}

async function loadModels() {
  if (state.models.length) return state.models;
  try {
    state.models = await api("/models");
    const dl = $("#models-dl");
    dl.innerHTML = "";
    for (const m of state.models) {
      const price = m.prompt_price !== null ? ` · $${(m.prompt_price * 1e6).toFixed(2)}/M` : "";
      dl.append(el("option", { value: m.id }, `${m.name}${price} · ${Math.round(m.context_length / 1000)}K`));
    }
  } catch (err) {
    console.warn("models:", err.message);
  }
  return state.models;
}

async function openChat(id) {
  closeNav();
  stopStreaming();
  state.current = { type: "chat", id };
  refreshList().catch(() => {});
  const [data] = await Promise.all([api(`/chats/${id}`), loadModels(), refreshMemory()]);
  const { chat, messages, context } = data;
  const view = $("#view");
  view.innerHTML = "";

  const modelInput = el("input", {
    type: "text", list: "models-dl", placeholder: t("chat.model_placeholder"),
    value: store.get("model") || chat.model || "", spellcheck: "false",
  });
  modelInput.addEventListener("change", () => {
    const v = modelInput.value.trim();
    if (v) store.set("model", v);
    updateEstimate();
  });

  const titleEl = el("h1", { title: t("common.click_to_rename"), onclick: () => renameConv(chat) }, chat.title);

  // Agent mode is remembered per chat in this browser.
  const agentKey = `agent:${id}`;
  // A chat that was never toggled starts in the mode you used last.
  const agentToggle = el("input", {
    type: "checkbox", id: `agent-${id}`, checked: (store.get(agentKey) ?? store.get("agent:last")) === "1",
  });
  const agentWarn = el("span", { class: "agent-warn" });
  const refreshAgentWarn = async () => {
    agentWarn.textContent = "";
    if (!agentToggle.checked) return;
    try {
      const s = await api("/agent/settings");
      const m = state.models.find((x) => x.id === modelInput.value.trim());
      if (!s.allowed_folders.length) agentWarn.textContent = t("chat.warn_no_folders");
      else if (m && !m.tools) agentWarn.textContent = t("chat.warn_no_tools");
    } catch {}
  };
  agentToggle.addEventListener("change", () => {
    store.set(agentKey, agentToggle.checked ? "1" : "0");
    store.set("agent:last", agentToggle.checked ? "1" : "0");
    header.classList.toggle("agent-on", agentToggle.checked);
    refreshAgentWarn();
  });
  modelInput.addEventListener("change", refreshAgentWarn);
  state.refreshAgentWarn = refreshAgentWarn; // only the open chat listens (see the listener below)

  // Memory on/off per chat (remembered in this browser); a chat never toggled follows the global setting.
  const memKey = `memory:${id}`;
  const memoryToggle = el("input", {
    type: "checkbox", id: `mem-${id}`, checked: (store.get(memKey) ?? (state.memory.enabled ? "1" : "0")) === "1",
  });
  memoryToggle.addEventListener("change", () => {
    store.set(memKey, memoryToggle.checked ? "1" : "0");
    updateEstimate();
  });

  const header = el("div", { class: "view-header" },
    titleEl,
    el("div", { class: "model-picker" }, modelInput),
    el("label", { class: "agent-toggle", for: `agent-${id}`, title: t("chat.agent_title") },
      agentToggle, t("chat.agent_mode")),
    el("label", { class: "memory-toggle", for: `mem-${id}`, title: t("chat.memory_title") },
      memoryToggle, t("chat.memory")),
    agentWarn,
    el("div", { class: "actions" },
      el("button", { onclick: () => openHandoff(id, () => modelInput.value.trim()), title: t("chat.handoff_title") }, icon("share"), t("chat.handoff")),
      el("button", { onclick: () => showAgentLog(id) }, t("chat.agent_log")),
      el("button", { class: "danger", onclick: () => deleteConv(chat) }, t("common.delete"))));
  header.classList.toggle("agent-on", agentToggle.checked);
  refreshAgentWarn();

  const contextBar = el("div", { class: "context-bar" });
  const renderContext = (items) => {
    contextBar.innerHTML = "";
    contextBar.append(el("span", {}, t("chat.refs")));
    if (!items.length) contextBar.append(el("span", { class: "hint" }, t("chat.refs_none")));
    for (const it of items) {
      const sel = el("select", { title: t("chat.ref_mode_title") },
        el("option", { value: "0" }, t("chat.ref_full")),
        el("option", { value: "1", disabled: !it.has_summary }, it.has_summary ? t("chat.ref_summary") : t("chat.ref_summary_none")));
      sel.value = it.use_summary ? "1" : "0";
      sel.addEventListener("change", () => {
        it.use_summary = sel.value === "1";
        saveContext(items);
      });
      contextBar.append(el("span", { class: "chip" }, badge(it.source), it.title, sel,
        el("button", { class: "link", title: t("common.remove"), onclick: () => saveContext(items.filter((x) => x !== it)) }, "×")));
    }
    contextBar.append(el("button", { onclick: () => pickContext(items) }, t("chat.pick_refs")));
  };
  const saveContext = async (items) => {
    const res = await api(`/chats/${id}/context`, {
      method: "PUT", json: { items: items.map((x) => ({ id: x.id, use_summary: !!x.use_summary })) },
    });
    currentContext = res.context;
    renderContext(currentContext);
    updateEstimate();
  };
  let currentContext = context;
  renderContext(currentContext);

  const pickContext = (items) => {
    const dlg = $("#context-dialog");
    const list = $("#context-options");
    const chosen = new Map(items.map((x) => [x.id, x]));
    const renderOptions = () => {
      const f = $("#context-filter").value.trim().toLowerCase();
      list.innerHTML = "";
      for (const c of state.conversations) {
        if (c.id === id) continue;
        if (f && !c.title.toLowerCase().includes(f)) continue;
        const cb = el("input", { type: "checkbox", id: `ctx-${c.id}`, checked: chosen.has(c.id) });
        cb.addEventListener("change", () => {
          cb.checked ? chosen.set(c.id, { id: c.id, use_summary: false }) : chosen.delete(c.id);
        });
        list.append(el("li", {}, cb, el("label", { for: `ctx-${c.id}` }, badge(c.source), c.title)));
      }
      if (!list.children.length) list.append(el("li", { class: "hint" }, t("chat.pick_empty")));
    };
    $("#context-filter").value = "";
    $("#context-filter").oninput = renderOptions;
    renderOptions();
    $("#context-save").onclick = () => { dlg.close(); saveContext([...chosen.values()]); };
    $("#context-cancel").onclick = () => dlg.close();
    dlg.showModal();
  };

  const list = el("div", { class: "messages" });
  const scroller = el("div", { class: "scroll" }, list);
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].kind === "panel" || messages[i].kind === "synthesis") {
      const group = [];
      while (i < messages.length && (messages[i].kind === "panel" || messages[i].kind === "synthesis")) group.push(messages[i++]);
      i--;
      list.append(panelView(group.filter((m) => m.kind === "panel").map((m) => m.model),
        group.find((m) => m.kind === "synthesis")?.model, group).node);
    } else {
      list.append(messageEl(messages[i]));
    }
  }
  if (!messages.length) {
    list.append(el("div", { class: "chat-empty empty" },
      el("h3", {}, t("chat.empty_title")),
      el("div", {}, t("chat.empty_text")),
      el("div", { class: "tips" },
        el("div", { class: "tip" }, t("chat.tip1")),
        el("div", { class: "tip" }, t("chat.tip2")),
        el("div", { class: "tip" }, t("chat.tip3")))));
  }

  const input = el("textarea", { rows: 3, placeholder: t("chat.input_placeholder") });
  const sendBtn = el("button", { class: "primary" }, t("chat.send"));
  const estimateLine = el("div", { class: "estimate" });

  let estTimer;
  let estSeq = 0;
  const updateEstimate = () => {
    clearTimeout(estTimer);
    estTimer = setTimeout(async () => {
      const seq = ++estSeq;
      try {
        const est = await api(`/chats/${id}/estimate`, {
          method: "POST",
          json: { draft: input.value, model: modelInput.value.trim() || null, models: panelCfg.extra, memory: memoryToggle.checked },
        });
        if (seq !== estSeq) return; // a newer estimate is on its way
        const parts = [t("est.input", { tokens: fa(est.total_tokens) })];
        if (est.system_tokens > 500) parts.push(t("est.breakdown", { refs: fa(est.system_tokens - (est.memory_tokens || 0)), history: fa(est.history_tokens) }));
        if (est.memory_notes) parts.push(tn("est.memory", est.memory_notes, { tokens: fa(est.memory_tokens) }));
        if (est.models_count) parts.push(t("est.models", { n: fa(est.models_count) }));
        if (est.input_cost !== undefined) parts.push(t("est.cost", { cost: fmtCost(est.input_cost) }) + (panelCfg.orchestrator && est.models_count ? t("est.plus_synth") : ""));
        if (est.model && est.model.context_length) parts.push(t("est.limit", { k: fa(Math.round(est.model.context_length / 1000)) }));
        if (modelInput.value.trim() && !est.model && state.models.length) parts.push(t("est.not_listed"));
        if (est.over_context) parts.push(t("est.over"));
        estimateLine.textContent = parts.join(" · ");
        estimateLine.classList.toggle("warn", !!est.over_context);
      } catch (err) {
        estimateLine.textContent = "";
      }
    }, 300);
  };
  input.addEventListener("input", updateEstimate);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
  });
  sendBtn.addEventListener("click", () => (state.streaming ? stopStreaming() : send()));

  async function send() {
    const content = input.value.trim();
    const model = modelInput.value.trim();
    if (!content) return;
    if (!model) { notify(t("chat.need_model")); modelInput.focus(); return; }
    store.set("model", model);
    if (panelCfg.extra.length) return sendPanel(content, model);
    const placeholder = list.querySelector(".empty");
    if (placeholder) placeholder.remove();

    list.append(messageEl({ role: "user", content }));
    const spinner = el("span", { class: "spinner" });
    const reply = el("div", { class: "msg assistant" }, spinner);
    list.append(reply);
    scroller.scrollTop = scroller.scrollHeight;
    input.value = "";

    const agentMode = agentToggle.checked;
    const ctrl = new AbortController();
    state.streaming = ctrl;
    sendBtn.textContent = t("chat.stop");
    let usage = null;
    let error = null;

    // The reply is a sequence of text segments and tool cards, in the order they happen.
    let segText = "";
    let segEl = null;
    const cards = {};
    const groups = [];
    const offered = new Set();
    let curGroup = null; // consecutive tool steps are folded into one compact line
    const flushText = () => { if (segEl) segEl.innerHTML = renderMarkdown(segText); };
    const endText = () => { flushText(); segEl = null; segText = ""; };
    const addBlock = (node) => { spinner.remove(); reply.append(node); };
    const scrollIfNear = () => {
      if (scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 200) scroller.scrollTop = scroller.scrollHeight;
    };
    const handle = (ev) => {
      if (ev.type === "delta") {
        if (!segEl) { segEl = el("div", { class: "seg-text" }); addBlock(segEl); curGroup = null; }
        segText += ev.text;
      } else if (ev.type === "tool_call") {
        endText();
        if (!curGroup) { curGroup = toolGroup(); groups.push(curGroup); addBlock(curGroup.node); }
        cards[ev.id] = curGroup.addStep({ name: ev.name, args: ev.args, status: ev.needs_approval ? "waiting" : "running" });
      } else if (ev.type === "approval_request") {
        cards[ev.id]?.askApproval(ev);
        scroller.scrollTop = scroller.scrollHeight;
      } else if (ev.type === "tool_result") {
        cards[ev.id]?.setResult(ev);
        if (ev.grant_folder && !offered.has(ev.grant_folder)) {
          offered.add(ev.grant_folder);
          addBlock(grantBar(ev.grant_folder));
          curGroup = null;
        }
      } else if (ev.type === "memory_suggestion") {
        endText();
        curGroup = null;
        if (!state.memory.items.some((n) => n.id === ev.id)) state.memory.items.unshift({ id: ev.id, text: ev.text, status: "suggested" });
        updateMemoryBadge();
        addBlock(memoryCard(ev));
      } else if (ev.type === "notice") {
        endText();
        curGroup = null;
        addBlock(el("div", { class: "notice" }, ev.message));
      } else if (ev.type === "error") error = ev.message;
      else if (ev.type === "done") usage = ev.usage;
    };

    try {
      const res = await fetch(`/api/chats/${id}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, model, agent: agentMode, memory: memoryToggle.checked }), signal: ctrl.signal,
      });
      if (!res.ok) {
        let msg = t("common.error_status", { status: res.status });
        try { msg = (await res.json()).detail || msg; } catch {}
        throw new Error(msg);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let lastRender = 0;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 2);
          if (!line.startsWith("data:")) continue;  // ": ping" keep-alives while waiting for approval
          handle(JSON.parse(line.slice(5)));
        }
        const now = performance.now();
        if (now - lastRender > 60) {
          flushText();
          lastRender = now;
          scrollIfNear();
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") error = err.message;
    } finally {
      state.streaming = null;
      sendBtn.textContent = t("chat.send");
    }
    flushText();
    spinner.remove();
    for (const c of Object.values(cards)) c.finish();
    for (const g of groups) g.refresh();
    if (error) {
      reply.classList.add("error");
      reply.append(el("div", {}, "⚠ " + error));
    }
    if (usage && (usage.prompt_tokens || usage.cost !== undefined)) {
      reply.append(usageEl({ model, ...usage }));
    }
    scroller.scrollTop = scroller.scrollHeight;
    refreshList().catch(() => {});
    updateEstimate();
    api(`/chats/${id}`).then((d) => { titleEl.textContent = d.chat.title; chat.title = d.chat.title; }).catch(() => {});
  }

  const composer = el("div", { class: "composer" },
    el("div", { class: "composer-inner" },
      el("div", { class: "composer-row" }, input, sendBtn), estimateLine));

  // ---------- multi-model (panel) ----------
  const panelKey = `panel:${id}`;
  const panelCfg = (() => {
    try { return { extra: [], orchestrator: "", ...JSON.parse(store.get(panelKey) || "{}") }; } catch { return { extra: [], orchestrator: "" }; }
  })();
  const panelBar = el("div", { class: "panel-bar" });
  const savePanel = () => {
    panelCfg.extra = panelCfg.extra.map((x) => x.trim()).filter((x, i, a) => x && a.indexOf(x) === i);
    store.set(panelKey, JSON.stringify(panelCfg));
    renderPanelBar();
    updateEstimate();
  };
  const modelField = (value, onChange, placeholder = t("panel.model")) => {
    const f = el("input", { type: "text", list: "models-dl", value, placeholder, spellcheck: "false", class: "model-field" });
    f.addEventListener("change", () => onChange(f.value.trim()));
    return f;
  };
  function renderPanelBar() {
    const on = panelCfg.extra.length > 0;
    panelBar.innerHTML = "";
    panelBar.classList.toggle("on", on);
    agentToggle.disabled = on;
    agentToggle.parentElement.title = on ? t("panel.no_tools")
      : agentToggle.parentElement.dataset.title || agentToggle.parentElement.title;
    if (on) {
      panelBar.append(el("span", { class: "hint" }, t("panel.other_models")));
      panelCfg.extra.forEach((m, i) => {
        panelBar.append(el("span", { class: "chip" },
          modelField(m, (v) => { panelCfg.extra[i] = v; savePanel(); }),
          el("button", { class: "link", title: t("common.remove"), onclick: () => { panelCfg.extra.splice(i, 1); savePanel(); } }, "×")));
      });
    }
    if (panelCfg.extra.length < 3) {
      panelBar.append(el("button", { onclick: () => {
        panelCfg.extra.push(""); renderPanelBar();
        panelBar.querySelectorAll(".model-field")[panelCfg.extra.length - 1]?.focus();
      } }, on ? t("panel.add") : t("panel.add_first")));
    }
    if (on) {
      panelBar.append(el("span", { class: "hint sep" }, t("panel.synth_with")),
        modelField(panelCfg.orchestrator, (v) => { panelCfg.orchestrator = v; savePanel(); }, t("panel.no_synth")));
    }
  }
  agentToggle.parentElement.dataset.title = agentToggle.parentElement.title;
  renderPanelBar();

  async function sendPanel(content, model) {
    const models = [model, ...panelCfg.extra.filter((m) => m !== model)];
    const placeholder = list.querySelector(".empty");
    if (placeholder) placeholder.remove();
    list.append(messageEl({ role: "user", content }));
    const pv = panelView(models, panelCfg.orchestrator || null);
    list.append(pv.node);
    scroller.scrollTop = scroller.scrollHeight;
    input.value = "";

    const ctrl = new AbortController();
    state.streaming = ctrl;
    sendBtn.textContent = t("chat.stop");
    let lastRender = 0;
    try {
      await readSSE(`/api/chats/${id}/messages`,
        { content, model, models: panelCfg.extra, orchestrator: panelCfg.orchestrator || null, memory: memoryToggle.checked },
        ctrl.signal, (ev) => {
          pv.handle(ev);
          const now = performance.now();
          if (now - lastRender > 80) { pv.flush(); lastRender = now; }
        });
    } catch (err) {
      if (err.name !== "AbortError") pv.fail(err.message);
    } finally {
      state.streaming = null;
      sendBtn.textContent = t("chat.send");
    }
    pv.flush();
    pv.finish();
    refreshList().catch(() => {});
    updateEstimate();
    api(`/chats/${id}`).then((d) => { titleEl.textContent = d.chat.title; chat.title = d.chat.title; }).catch(() => {});
  }

  view.append(header, contextBar, panelBar, scroller, composer);
  scroller.scrollTop = scroller.scrollHeight;
  updateEstimate();
  (modelInput.value ? input : modelInput).focus();
}

function usageEl(m) {
  const bits = [m.model];
  if (m.prompt_tokens) bits.push(`in ${m.prompt_tokens.toLocaleString()}`);
  if (m.cached_tokens) bits.push(`cached ${m.cached_tokens.toLocaleString()}`);
  if (m.completion_tokens) bits.push(`out ${m.completion_tokens.toLocaleString()}`);
  if (m.cost !== null && m.cost !== undefined) bits.push(fmtCost(m.cost));
  return el("div", { class: "msg-meta" }, bits.join(" · "));
}

// The server appends one of these to a saved reply that was cut off (messages.py "api.answer_cut", in
// Persian as older chats have it, or in English).
const INCOMPLETE_MARKS = ["[\u062C\u0648\u0627\u0628 \u0646\u0627\u0642\u0635 \u0645\u0627\u0646\u062F]", "[Answer incomplete]"];

function messageEl(m) {
  if (m.role === "user") return el("div", { class: "msg user", dir: "auto" }, m.content);
  const div = el("div", { class: "msg assistant" });
  if (m.tool_trace && m.tool_trace.length) {
    let group = null;
    for (const seg of m.tool_trace) {
      if (seg.type === "text") {
        group = null;
        const segEl = el("div", { class: "seg-text" });
        segEl.innerHTML = renderMarkdown(seg.text);
        div.append(segEl);
      } else if (seg.type === "memory") {
        group = null;
        div.append(memoryCard({ id: seg.memory_id, text: seg.text }));
      } else {
        if (!group) { group = toolGroup(); div.append(group.node); }
        const step = group.addStep({ name: seg.name, args: seg.args, status: seg.status });
        step.setResult({ status: seg.status, approval: seg.approval, preview: seg.preview });
      }
    }
    if (m.content && INCOMPLETE_MARKS.some((s) => m.content.endsWith(s))) div.append(el("div", { class: "notice" }, t("chat.incomplete")));
  } else {
    div.innerHTML = renderMarkdown(m.content);
  }
  if (m.model) div.append(usageEl(m));
  return div;
}

// ---------- streaming helper ----------

async function readSSE(url, body, signal, onEvent) {
  const res = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal,
  });
  if (!res.ok) {
    let msg = t("common.error_status", { status: res.status });
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5)));
    }
  }
}

// ---------- multi-model answers side by side ----------

function usageText(u) {
  if (!u) return "";
  const bits = [];
  if (u.prompt_tokens) bits.push(`in ${u.prompt_tokens.toLocaleString()}`);
  if (u.completion_tokens) bits.push(`out ${u.completion_tokens.toLocaleString()}`);
  if (u.cost !== null && u.cost !== undefined) bits.push(fmtCost(u.cost));
  return bits.join(" · ");
}

// models: the panel; orchestrator: synthesis model or null; stored: saved messages to show instead of streaming.
function panelView(models, orchestrator, stored = null) {
  const makeBox = (cls, head) => {
    const body = el("div", { class: "panel-body" }, stored ? null : el("span", { class: "spinner" }));
    const meta = el("div", { class: "msg-meta" });
    const node = el("div", { class: cls }, head, body, meta);
    return { node, body, meta, text: "", dirty: false, done: false };
  };
  const cols = models.map((m) => ({ model: m, ...makeBox("panel-col", el("div", { class: "panel-head", dir: "ltr" }, m)) }));
  const grid = el("div", { class: "panel-grid" }, cols.map((c) => c.node));
  grid.style.setProperty("--cols", String(Math.min(models.length, 3)));
  const node = el("div", { class: "panel" }, grid);
  let synth = null;
  const makeSynth = (model) => {
    synth = makeBox("panel-synth", el("div", { class: "panel-head" }, t("panel.synth_head"), el("span", { dir: "ltr" }, model)));
    node.append(synth.node);
  };
  const slot = (s) => (s === "s" ? synth : cols[s]);

  if (stored) {
    for (const m of stored) {
      let box;
      if (m.kind === "synthesis") { makeSynth(m.model); box = synth; }
      else box = cols.find((c) => c.model === m.model && !c.text);
      if (!box) continue;
      box.text = m.content;
      box.body.innerHTML = renderMarkdown(m.content);
      box.meta.textContent = usageText(m);
    }
    for (const c of cols) if (!c.text) c.body.append(el("span", { class: "hint" }, t("panel.not_saved")));
  }

  return {
    node,
    handle(ev) {
      if (ev.type === "synth_start") makeSynth(ev.model);
      else if (ev.type === "delta") {
        const b = slot(ev.slot);
        if (b) { b.text += ev.text; b.dirty = true; }
      } else if (ev.type === "slot_done") {
        const b = slot(ev.slot);
        if (!b) return;
        b.done = true;
        b.dirty = true;
        b.meta.textContent = usageText(ev.usage);
        if (ev.error) b.meta.append(el("div", { class: "error" }, "⚠ " + ev.error));
      } else if (ev.type === "done" && ev.usage && ev.usage.cost) {
        node.append(el("div", { class: "msg-meta" }, t("panel.total", { usage: usageText(ev.usage) })));
      }
    },
    flush() {
      for (const b of [...cols, synth].filter(Boolean)) {
        if (!b.dirty) continue;
        b.body.innerHTML = b.text ? renderMarkdown(b.text) : (b.done ? "" : '<span class="spinner"></span>');
        b.dirty = false;
      }
    },
    finish() {
      for (const b of [...cols, synth].filter(Boolean)) {
        if (!b.text) b.body.replaceChildren(el("span", { class: "hint" }, t("panel.no_answer")));
      }
    },
    fail(msg) { node.append(el("div", { class: "error" }, "⚠ " + msg)); },
  };
}

// ---------- agent: tool cards, approvals, log, settings ----------

const AGENT_TOOLS = ["list_allowed_folders", "list_directory", "read_file", "find_files", "write_file", "edit_file",
  "run_command", "delete_path", "read_skill"];
const keyed = (names, prefix) => Object.fromEntries(names.map((k) => [k, t(prefix + k)]));
const TOOL_LABELS = keyed(AGENT_TOOLS, "tool.");
const STATUS_LABELS = keyed(["running", "waiting", "ok", "error", "denied", "blocked", "stopped"], "status.");

function argSummary(name, args = {}) {
  if (args.command) return args.command;
  if (args.path) return args.path + (args.pattern ? `  (${args.pattern}${args.contains ? ` ∋ "${args.contains}"` : ""})` : "");
  if (args.name) return args.name;
  const s = JSON.stringify(args);
  return s === "{}" ? "" : s.slice(0, 160);
}

function diffEl(diff) {
  const pre = el("pre", { class: "diff" });
  const lines = (diff || t("diff.no_change")).split("\n");
  for (const line of lines) {
    const cls = line.startsWith("+") && !line.startsWith("+++") ? "add"
      : line.startsWith("-") && !line.startsWith("---") ? "del" : line.startsWith("@@") ? "hunk" : "";
    pre.append(el("span", { class: cls }, line || " "));
  }
  // The whole diff is always there (scroll inside the box); this only makes the box taller.
  const added = lines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
  const removed = lines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length;
  const toggle = el("button", { class: "link", type: "button" }, t("diff.bigger"));
  toggle.onclick = () => {
    const tall = pre.classList.toggle("tall");
    toggle.textContent = tall ? t("diff.smaller") : t("diff.bigger");
  };
  return el("div", { class: "diff-wrap" },
    el("div", { class: "diff-meta" }, t("diff.lines", { added: fa(added), removed: fa(removed) }), lines.length > 15 ? toggle : null),
    pre);
}

// Short verbs for one-line steps, and phrases for the folded group summary.
const STEP_VERBS = keyed(AGENT_TOOLS, "verb.");
const GROUP_PHRASES = {
  list_allowed_folders: () => t("group.list_allowed_folders"),
  ...Object.fromEntries(AGENT_TOOLS.filter((k) => k !== "list_allowed_folders").map((k) => [k, (n) => tn(`group.${k}`, n)])),
};
const PROBLEM_LABELS = keyed(["denied", "blocked", "error", "stopped"], "problem.");

function shortPath(p) {
  const parts = String(p).split(/[\\/]+/).filter(Boolean);
  return parts.length > 3 ? "…/" + parts.slice(-2).join("/") : String(p);
}

function stepArgs(name, args = {}) {
  if (args.command) return args.command;
  if (args.path) return shortPath(args.path) + (args.contains ? `  ∋ "${args.contains}"` : args.pattern && args.pattern !== "*" ? `  ${args.pattern}` : "");
  if (args.name) return args.name;
  const s = JSON.stringify(args);
  return s === "{}" ? "" : s.slice(0, 120);
}

// A folded block of consecutive tool steps: one clickable summary line, like Claude Code.
function toolGroup() {
  const steps = [];
  // Points toward the line's end ("›" is mirrored to "‹" in right-to-left text); turns down when open (app.css).
  const chevron = el("span", { class: "chev" }, "›");
  const summary = el("span", { class: "group-summary" });
  const state = el("span", { class: "group-state" });
  const list = el("div", { class: "group-steps" });
  const node = el("div", { class: "tool-group" },
    el("button", { class: "group-head", type: "button", onclick: () => node.classList.toggle("open") },
      summary, state, chevron),
    list);

  const refresh = () => {
    const counts = {}, order = [];
    let problems = 0, running = false, waiting = false;
    for (const s of steps) {
      const key = s.name.startsWith("mcp__") ? "mcp" : s.name;
      if (!(key in counts)) { counts[key] = 0; order.push(key); }
      counts[key]++;
      if (PROBLEM_LABELS[s.status]) problems++;
      if (s.status === "running") running = true;
      if (s.status === "waiting") waiting = true;
    }
    summary.textContent = order.map((k) =>
      k === "mcp" ? tn("group.mcp", counts[k]) : (GROUP_PHRASES[k] || ((n) => `${k} ×${fa(n)}`))(counts[k])).join(t("common.list_sep"));
    state.innerHTML = "";
    if (waiting) state.append(el("span", { class: "pill waiting" }, t("status.waiting")));
    else if (running) state.append(el("span", { class: "spinner" }));
    if (problems) state.append(el("span", { class: "pill problem" }, tn("group.problems", problems)));
  };

  return {
    node,
    refresh,
    addStep({ name, args, status }) {
      const step = toolStep({ name, args, status, onChange: () => { refresh(); }, onNeedsAttention: () => node.classList.add("open") });
      steps.push(step.info);
      list.append(step.node);
      refresh();
      return step;
    },
  };
}

function toolStep({ name, args, status, onChange, onNeedsAttention }) {
  const info = { name, status };
  const verb = STEP_VERBS[name] || (name.startsWith("mcp__") ? "MCP · " + name.slice(5).split("__").pop() : name);
  const dot = el("span", { class: `dot ${status}` });
  const flag = el("span", { class: "step-flag" });
  const body = el("div", { class: "step-body" });
  const node = el("div", { class: "tool-step" },
    el("button", { class: "step-head", type: "button", title: (args && (args.path || args.command)) || "",
      onclick: () => node.classList.toggle("open") },
      dot,
      el("span", { class: "step-verb" }, verb),
      el("span", { class: "step-args", dir: "ltr" }, stepArgs(name, args)),
      flag),
    body);
  let current = status;
  const setStatus = (s) => {
    current = info.status = s;
    dot.className = `dot ${s}`;
    flag.textContent = PROBLEM_LABELS[s] || (s === "waiting" ? t("step.waiting") : "");
    flag.className = `step-flag ${s}`;
    onChange();
  };
  return {
    node,
    info,
    askApproval(ev) {
      setStatus("waiting");
      node.classList.add("open");
      onNeedsAttention();
      const p = ev.preview || {};
      const box = el("div", { class: "approval" });
      if (p.kind === "write" || p.kind === "edit") {
        box.append(el("div", {}, p.exists ? t("approve.edit_existing") : t("approve.create")),
          el("div", { class: "path", dir: "ltr" }, p.path), diffEl(p.diff));
      } else if (p.kind === "command") {
        box.append(
          el("div", { class: "danger-text" }, t("approve.command_warn")),
          el("pre", { dir: "ltr" }, p.command),
          el("div", { class: "path", dir: "ltr" }, t("approve.cwd", { cwd: p.cwd })));
      } else if (p.kind === "delete") {
        const isFolder = p.target === "folder";
        box.append(el("div", { class: "danger-text" },
          isFolder ? t("approve.delete_folder") : t("approve.delete_file")),
          el("div", { class: "path", dir: "ltr" }, p.path),
          isFolder ? el("div", {}, tn("approve.folder_files", p.files)) : null);
      } else if (p.kind === "mcp") {
        box.append(el("div", {}, t("approve.mcp", { tool: p.tool, server: p.server })),
          el("pre", { dir: "ltr" }, JSON.stringify(p.args, null, 2)));
      }
      const yes = el("button", { class: "primary" }, t("approve.yes"));
      const no = el("button", {}, t("approve.no"));
      // MCP tools: "always allow" this one tool (saved in settings, can be taken back there).
      const always = p.kind === "mcp"
        ? el("button", { title: t("approve.always_title", { key: p.key }) }, t("approve.always"))
        : null;
      const buttons = [yes, always, no].filter(Boolean);
      const answer = async (approved, alwaysAllow = false) => {
        buttons.forEach((b) => (b.disabled = true));
        try {
          await api(`/agent/approvals/${ev.approval_id}`, { method: "POST", json: { approved, always: alwaysAllow } });
          setStatus(approved ? "running" : "denied");
          box.classList.add("answered");
          box.querySelector(".approval-actions").replaceWith(el("div", { class: "hint" },
            alwaysAllow ? t("approve.done_always", { key: p.key }) : approved ? t("approve.done_yes") : t("approve.done_no")));
        } catch (err) {
          notify(err.message);
          buttons.forEach((b) => (b.disabled = false));
        }
      };
      yes.onclick = () => answer(true);
      no.onclick = () => answer(false);
      if (always) always.onclick = () => answer(true, true);
      box.append(el("div", { class: "approval-actions" }, ...buttons));
      body.append(box);
    },
    setResult(ev) {
      setStatus(ev.status);
      if (ev.preview) body.append(el("pre", { class: "step-result", dir: "auto" }, ev.preview));
      if (ev.status !== "waiting") node.classList.remove("open"); // fold back once answered
    },
    finish() {
      if (current === "running" || current === "waiting") setStatus("stopped");
      body.querySelectorAll(".approval button").forEach((b) => (b.disabled = true));
    },
  };
}

// Shown when the agent tried a folder that isn't allowed: one click adds it to the settings.
// Only the user can press this; the model can never widen its own access.
function grantBar(folder) {
  const btn = el("button", { class: "primary" }, t("grant.btn"));
  const bar = el("div", { class: "grant-bar" },
    el("span", {}, t("grant.text")),
    el("code", { dir: "ltr" }, folder),
    btn);
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      const s = await api("/agent/settings");
      await api("/agent/settings", { method: "PUT", json: { allowed_folders: [...s.allowed_folders, folder] } });
      bar.replaceChildren(el("span", {}, t("grant.added")), el("code", { dir: "ltr" }, folder),
        el("span", { class: "hint" }, t("grant.continue")));
      window.dispatchEvent(new Event("agent-settings-changed"));
    } catch (err) {
      notify(err.message);
      btn.disabled = false;
    }
  };
  return bar;
}

async function showAgentLog(chatId) {
  const dlg = $("#log-dialog");
  const box = $("#log-entries");
  box.innerHTML = '<span class="spinner"></span>';
  dlg.showModal();
  try {
    const rows = await api(`/chats/${chatId}/agent-log`);
    box.innerHTML = "";
    if (!rows.length) { box.append(el("div", { class: "hint" }, t("log.empty"))); return; }
    for (const r of rows) {
      box.append(el("details", { class: "log-row" },
        el("summary", {},
          el("span", { class: "log-time" }, fmtDate(r.created_at)),
          el("span", { class: "tool-name" }, TOOL_LABELS[r.tool] || r.tool),
          el("span", { class: "tool-args", dir: "ltr" }, argSummary(r.tool, r.args)),
          el("span", { class: `tool-status ${r.status}` }, STATUS_LABELS[r.status] || r.status),
          r.approval !== "auto" ? el("span", { class: "hint" }, r.approval === "approved" ? t("log.approved") : t("log.denied")) : null),
        el("pre", { dir: "auto" }, JSON.stringify(r.args, null, 2) + "\n\n" + (r.result || ""))));
    }
  } catch (err) {
    box.textContent = err.message;
  }
}
$("#log-close").addEventListener("click", () => $("#log-dialog").close());

async function openAgentSettings() {
  const dlg = $("#settings-dialog");
  $("#settings-error").hidden = true;
  try {
    const s = await api("/agent/settings");
    $("#set-folders").value = s.allowed_folders.join("\n");
    $("#set-skills").value = s.skill_folders.join("\n");
    $("#set-mcp").value = Object.keys(s.mcp_servers).length
      ? JSON.stringify({ mcpServers: s.mcp_servers }, null, 2) : "";
    renderSkills(s.skills);
    renderAlways(s.mcp_always_allow || []);
    $("#set-ext-id").value = (await api("/settings/extension")).paired || "";
  } catch (err) {
    notify(err.message);
    return;
  }
  dlg.showModal();
}

function renderAlways(keys) {
  const ul = $("#set-always");
  ul.innerHTML = "";
  if (!keys.length) ul.append(el("li", { class: "hint" }, t("settings.always_none")));
  for (const k of keys) {
    ul.append(el("li", {}, el("span", { dir: "ltr" }, k), " ",
      el("button", { class: "link", title: t("settings.revoke"), onclick: async () => {
        const s = await api("/agent/settings", { method: "PUT", json: { mcp_always_allow: keys.filter((x) => x !== k) } });
        renderAlways(s.mcp_always_allow);
      } }, "×")));
  }
}

$("#set-ext-save").addEventListener("click", async () => {
  try {
    const s = await api("/settings/extension", { method: "PUT", json: { id: $("#set-ext-id").value.trim() || null } });
    $("#set-ext-id").value = s.paired || "";
    checkExtensionPending();
    notify(s.paired ? t("settings.ext_saved") : t("settings.ext_removed"));
  } catch (err) {
    notify(err.message);
  }
});

// An extension that isn't paired yet tried to connect: offer a one-click "accept".
async function checkExtensionPending() {
  const bar = $("#ext-pending");
  let st;
  try { st = await api("/settings/extension"); } catch { return; }
  bar.hidden = !st.pending;
  if (!st.pending) return;
  bar.replaceChildren(
    el("div", {}, t("ext.pending_title")),
    el("code", { dir: "ltr" }, st.pending),
    el("div", { class: "hint" }, t("ext.pending_hint")),
    el("div", { class: "row" },
      el("button", { class: "primary", onclick: async () => {
        await api("/settings/extension", { method: "PUT", json: { id: st.pending } });
        bar.hidden = true;
        notify(t("ext.accepted"));
      } }, t("ext.accept")),
      el("button", { onclick: () => { bar.hidden = true; } }, t("ext.decline"))));
}
setInterval(checkExtensionPending, 10000);

function renderSkills(skills) {
  const ul = $("#set-skill-list");
  ul.innerHTML = "";
  if (!skills.length) ul.append(el("li", { class: "hint" }, t("settings.no_skills")));
  for (const s of skills) ul.append(el("li", {}, el("strong", { dir: "ltr" }, s.name), " — ", s.description));
}

$("#btn-settings").addEventListener("click", openAgentSettings);

// ---------- backups ----------

function fmtSize(n) {
  return n < 1024 * 1024 ? `${fa(Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function renderBackups(info) {
  $("#backup-folder").value = info.default ? "" : info.folder;
  $("#backup-folder").placeholder = info.default ? info.folder
    : I18N.platform === "darwin" ? "/Users/me/Backups/ConvoHub" : "D:\\Backups\\ConvoHub";
  const ul = $("#backup-list");
  ul.innerHTML = "";
  if (!info.items.length) ul.append(el("li", { class: "hint" }, t("backup.none")));
  for (const b of info.items) {
    ul.append(el("li", {},
      // backup names use local time (unlike the database's UTC timestamps)
      el("span", {}, new Date(b.created.replace(" ", "T")).toLocaleString(I18N.locale, { dateStyle: "medium", timeStyle: "short" })),
      el("span", { class: "hint" }, b.auto ? t("backup.auto") : t("backup.manual")),
      el("span", { class: "hint" }, fmtSize(b.size)),
      el("a", { href: `/api/backups/${encodeURIComponent(b.name)}`, download: b.name }, t("backup.download"))));
  }
}

async function openBackups() {
  $("#backup-msg").textContent = "";
  try {
    renderBackups(await api("/backups"));
  } catch (err) {
    notify(err.message);
    return;
  }
  $("#backup-dialog").showModal();
}

$("#btn-backup").addEventListener("click", openBackups);

// ---------- shutting down ----------
$("#btn-quit").addEventListener("click", async () => {
  if (!(await askConfirm(t("quit.confirm"), t("quit.ok"), true))) return;
  stopStreaming();
  try {
    await api("/shutdown", { method: "POST" });
  } catch (err) {
    notify(err.message);
    return;
  }
  $("#app").replaceChildren(el("div", { class: "welcome" },
    el("h2", {}, t("quit.title")),
    el("p", {}, t("quit.text"))));
});
$("#backup-close").addEventListener("click", () => $("#backup-dialog").close());
$("#backup-now").addEventListener("click", async () => {
  const btn = $("#backup-now");
  btn.disabled = true;
  $("#backup-msg").textContent = t("backup.running");
  try {
    const res = await api("/backups", { method: "POST" });
    renderBackups(res);
    $("#backup-msg").textContent = tn("backup.saved", res.created.conversations, { path: res.created.path });
  } catch (err) {
    $("#backup-msg").textContent = "⚠ " + err.message;
  } finally {
    btn.disabled = false;
  }
});
$("#backup-folder-save").addEventListener("click", async () => {
  try {
    renderBackups(await api("/backups/folder", { method: "PUT", json: { folder: $("#backup-folder").value.trim() } }));
    $("#backup-msg").textContent = t("backup.folder_saved");
  } catch (err) {
    $("#backup-msg").textContent = "⚠ " + err.message;
  }
});
window.addEventListener("agent-settings-changed", () => state.refreshAgentWarn?.());
$("#settings-cancel").addEventListener("click", () => $("#settings-dialog").close());
$("#settings-save").addEventListener("click", async () => {
  const errBox = $("#settings-error");
  errBox.hidden = true;
  const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
  let mcp = {};
  const raw = $("#set-mcp").value.trim();
  if (raw) {
    try { mcp = JSON.parse(raw); } catch (e) {
      errBox.textContent = t("settings.bad_mcp_json", { error: e.message });
      errBox.hidden = false;
      return;
    }
  }
  try {
    const s = await api("/agent/settings", {
      method: "PUT",
      json: { allowed_folders: lines($("#set-folders").value), skill_folders: lines($("#set-skills").value), mcp_servers: mcp },
    });
    renderSkills(s.skills);
    $("#settings-dialog").close();
    window.dispatchEvent(new Event("agent-settings-changed"));
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
  }
});

function stopStreaming() {
  if (state.streaming) state.streaming.abort();
}

// ---------- import dialog ----------

const importDlg = $("#import-dialog");
let importTab = "paste";

function setImportTab(tab) {
  importTab = tab;
  for (const b of importDlg.querySelectorAll(".tab")) b.classList.toggle("active", b.dataset.tab === tab);
  for (const s of importDlg.querySelectorAll("[data-pane]")) s.hidden = s.dataset.pane !== tab;
  $("#meta-row").hidden = tab === "link";
  $("#import-error").hidden = true;
}

for (const b of importDlg.querySelectorAll(".tab")) b.addEventListener("click", () => setImportTab(b.dataset.tab));

$("#btn-import").addEventListener("click", () => {
  $("#paste-text").value = "";
  $("#paste-info").textContent = "";
  $("#file-input").value = "";
  $("#link-url").value = "";
  $("#import-title").value = "";
  $("#import-source").value = "";
  setImportTab("paste");
  importDlg.showModal();
});
$("#import-cancel").addEventListener("click", () => importDlg.close());

let previewTimer;
$("#paste-text").addEventListener("input", () => {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const text = $("#paste-text").value;
    if (!text.trim()) { $("#paste-info").textContent = ""; return; }
    try {
      const p = await api("/import/preview", { method: "POST", json: { text } });
      $("#paste-info").textContent =
        t("import.preview", { chars: fa(p.chars), tokens: fa(p.tokens), source: SOURCE_NAMES[p.source] || p.source });
      $("#import-title").placeholder = p.title;
    } catch {}
  }, 300);
});

$("#import-submit").addEventListener("click", async () => {
  const btn = $("#import-submit");
  const errBox = $("#import-error");
  errBox.hidden = true;
  btn.disabled = true;
  const label = btn.textContent;
  btn.replaceChildren(el("span", { class: "spinner" }), " " + (importTab === "link" ? t("import.reading_page") : t("import.importing")));
  try {
    let res;
    const title = $("#import-title").value.trim() || null;
    const source = $("#import-source").value || null;
    if (importTab === "paste") {
      const text = $("#paste-text").value;
      if (!text.trim()) throw new Error(t("import.no_text"));
      res = await api("/import/paste", { method: "POST", json: { text, title, source } });
    } else if (importTab === "file") {
      const f = $("#file-input").files[0];
      if (!f) throw new Error(t("import.no_file"));
      const fd = new FormData();
      fd.append("file", f);
      if (source) fd.append("source", source);
      res = await api("/import/file", { method: "POST", body: fd });
      if (title && res.ids.length === 1) {
        await api(`/conversations/${res.ids[0]}`, { method: "PATCH", json: { title } });
      }
    } else {
      const url = $("#link-url").value.trim();
      if (!url) throw new Error(t("import.no_link"));
      res = await api("/import/link", { method: "POST", json: { url } });
    }
    importDlg.close();
    await refreshList();
    if (res.ids.length === 1) openConversation(res.ids[0]);
    else notify(tn("import.done_many", res.ids.length));
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
});

// ---------- startup ----------

$("#btn-new-chat").addEventListener("click", () => newChat().catch(showFatal));

// ---------- theme and narrow-window menu ----------

const THEMES = { auto: ["auto", t("theme.auto")], light: ["sun", t("theme.light")], dark: ["moon", t("theme.dark")] };
function applyTheme(name) {
  if (name === "light" || name === "dark") document.documentElement.dataset.theme = name;
  else delete document.documentElement.dataset.theme;
  const [ic, label] = THEMES[name] || THEMES.auto;
  $("#btn-theme").replaceChildren(icon(ic), label);
}
$("#btn-theme").addEventListener("click", () => {
  const order = ["auto", "light", "dark"];
  const next = order[(order.indexOf(store.get("theme", "auto")) + 1) % order.length];
  store.set("theme", next);
  applyTheme(next);
});
applyTheme(store.get("theme", "auto"));

function closeNav() { $("#app").classList.remove("nav-open"); }
$("#btn-menu").addEventListener("click", () => $("#app").classList.add("nav-open"));
$("#scrim").addEventListener("click", closeNav);

// ---------- OpenRouter key (asked in the UI on first run) ----------

async function refreshKeyState() {
  const st = await api("/settings/key");
  state.keySet = st.set;
  $("#key-warning").hidden = st.set;
  return st;
}

async function openKeyDialog() {
  closeNav();
  const st = await refreshKeyState().catch(() => ({ set: false }));
  $("#key-input").value = "";
  $("#key-error").hidden = true;
  $("#key-state").textContent = !st.set ? t("key.none")
    : st.source === "env" ? t("key.from_env", { hint: st.hint })
    : t("key.saved_hint", { hint: st.hint });
  $("#key-remove").hidden = st.source !== "saved";
  $("#key-dialog").showModal();
  $("#key-input").focus();
}

$("#key-save").addEventListener("click", async () => {
  const btn = $("#key-save");
  const key = $("#key-input").value.trim();
  if (!key) { $("#key-input").focus(); return; }
  btn.disabled = true;
  btn.replaceChildren(el("span", { class: "spinner" }), " " + t("key.checking"));
  try {
    const res = await api("/settings/key", { method: "PUT", json: { key } });
    $("#key-input").value = "";
    $("#key-dialog").close();
    await refreshKeyState();
    state.models = [];
    loadModels();
    notify(res.warning ? t("key.saved_warning", { warning: res.warning }) : t("key.saved_ok", { hint: res.hint }));
    if (!state.current) showWelcome();
  } catch (err) {
    $("#key-error").textContent = err.message;
    $("#key-error").hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = t("key.save");
  }
});
$("#key-remove").addEventListener("click", async () => {
  if (!(await askConfirm(t("key.remove_confirm"), t("common.delete_ok"), true))) return;
  await api("/settings/key", { method: "DELETE" });
  $("#key-dialog").close();
  await refreshKeyState();
  if (!state.current) showWelcome();
});
$("#key-close").addEventListener("click", () => $("#key-dialog").close());
$("#btn-key").addEventListener("click", openKeyDialog);
$("#key-warning").addEventListener("click", openKeyDialog);

// ---------- connect: extension guide + MCP commands with this machine's paths ----------

async function openConnect(tab = "ext") {
  closeNav();
  let info, pairing;
  try {
    [info, pairing] = await Promise.all([api("/integrations"), api("/settings/extension")]);
  } catch (err) {
    notify(err.message);
    return;
  }
  $("#ext-dir").textContent = info.extension_dir;
  $("#ext-open").disabled = !info.extension_dir_exists;
  $("#ext-state").textContent = pairing.paired
    ? t("connect.ext_paired", { id: pairing.paired })
    : t("connect.ext_none");
  $("#mcp-claude").textContent = info.claude_code;
  $("#mcp-hermes").textContent = info.hermes;
  $("#mcp-opencode").textContent = info.opencode;
  $("#mcp-cline").textContent = info.cline;
  setConnectTab(typeof tab === "string" ? tab : "ext");
  $("#connect-dialog").showModal();
}

function setConnectTab(tab) {
  for (const b of document.querySelectorAll("[data-ctab]")) b.classList.toggle("active", b.dataset.ctab === tab);
  for (const s of document.querySelectorAll("[data-cpane]")) s.hidden = s.dataset.cpane !== tab;
  clearInterval(state.remoteTimer);
  if (tab === "remote") refreshRemote();
}

// ---------- remote connector: a temporary public address for Gemini and other cloud MCP clients ----------

function renderRemote(s) {
  const on = s.running;
  const inst = s.install || { state: "idle" };
  const installing = inst.state === "downloading";

  // step 1: the tunnel tool
  $("#rstep-1-state").textContent = s.cloudflared ? t("remote.ready") : "";
  $("#rstep-1").classList.toggle("done", s.cloudflared);
  $("#rstep-1-body").hidden = s.cloudflared;
  const manual = s.can_install === false; // not Windows: the user installs cloudflared (macOS: Homebrew)
  $("#remote-manual").hidden = !manual;
  $("#remote-install-hint").textContent = manual ? s.install_hint || "" : "";
  $("#remote-brew-box").hidden = !(manual && I18N.platform === "darwin");
  $("#remote-install").hidden = installing || manual;
  $("#remote-progress").hidden = !installing;
  if (installing) {
    const pct = inst.total ? Math.round((100 * inst.done) / inst.total) : 0;
    $("#remote-progress-bar").style.width = `${pct}%`;
    $("#remote-install-state").textContent = inst.total
      ? t("remote.downloading", { done: fa((inst.done / 1e6).toFixed(0)), total: fa((inst.total / 1e6).toFixed(0)) })
      : t("remote.download_starting");
  } else {
    $("#remote-install-state").textContent = inst.state === "error" ? inst.error : "";
  }
  $("#remote-install-state").classList.toggle("error", inst.state === "error");

  // step 2: on / off
  $("#rstep-2").classList.toggle("disabled", !s.cloudflared);
  $("#rstep-2").classList.toggle("done", on && s.reachable === true);
  $("#remote-toggle").disabled = !s.cloudflared && !on;
  $("#remote-toggle").textContent = on ? t("remote.turn_off") : t("connect.remote.turn_on");
  $("#remote-toggle").classList.toggle("primary", !on);
  $("#remote-toggle").classList.toggle("danger", on);
  $("#rstep-2-state").textContent = on ? (s.reachable === true ? t("remote.reachable") : s.reachable === false ? t("remote.unreachable") : t("remote.preparing")) : "";
  $("#remote-state").textContent = !on ? (s.cloudflared ? t("remote.off") : t("remote.do_step1"))
    : s.reachable === true ? t("remote.on_since", { time: s.started_at })
    : s.reachable === false ? s.reach_detail
    : t("remote.checking", { detail: s.reach_detail || "" });

  // step 3: connect Gemini
  $("#rstep-3").classList.toggle("disabled", !on);
  $("#remote-on").hidden = !on;
  $("#remote-off-hint").hidden = on;
  if (on) $("#remote-url").textContent = s.url;
  $("#remote-calls").replaceChildren(...(s.calls.length
    ? s.calls.map((c) => el("li", {}, el("span", { class: "hint" }, c.at), " ", c.tool, " ",
        el("code", { dir: "ltr" }, Object.keys(c.args).length ? JSON.stringify(c.args) : "")))
    : [el("li", { class: "hint" }, t("remote.no_calls"))]));
  $("#remote-error").hidden = !s.error;
  $("#remote-error").textContent = s.error || "";

  // poll faster while something is in progress
  const busy = installing || (on && s.reachable == null);
  clearInterval(state.remoteTimer);
  if ($("#connect-dialog").open) state.remoteTimer = setInterval(refreshRemote, busy ? 1500 : 4000);
}

async function refreshRemote() {
  try { renderRemote(await api("/remote")); } catch {}
}

$("#remote-install").addEventListener("click", async () => {
  try { renderRemote(await api("/remote/install", { method: "POST" })); } catch (err) { notify(err.message); }
});
$("#remote-recheck").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  try { renderRemote(await api("/remote")); } catch (err) { notify(err.message); } finally { btn.disabled = false; }
});

$("#remote-toggle").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const s = await api("/remote").catch(() => ({ running: false }));
  if (!s.running && !(await askConfirm(t("remote.confirm"), t("remote.confirm_ok")))) return;
  btn.disabled = true;
  btn.textContent = s.running ? t("remote.stopping") : t("remote.starting");
  try {
    renderRemote(await api(s.running ? "/remote/stop" : "/remote/start", { method: "POST" }));
  } catch (err) {
    notify(err.message);
    refreshRemote();
  }
});

document.querySelectorAll("[data-ctab]").forEach((b) => b.addEventListener("click", () => setConnectTab(b.dataset.ctab)));
document.querySelectorAll("button.copy").forEach((b) => b.addEventListener("click", async () => {
  const text = document.getElementById(b.dataset.copyFrom).textContent;
  try {
    await navigator.clipboard.writeText(text);
    const old = b.textContent;
    b.textContent = t("common.copied");
    setTimeout(() => (b.textContent = old), 1500);
  } catch {
    notify(t("common.copy_failed"));
  }
}));
$("#ext-open").addEventListener("click", () => api("/open-folder", { method: "POST", json: { which: "extension" } }).catch((e) => notify(e.message)));
$("#connect-close").addEventListener("click", () => { clearInterval(state.remoteTimer); $("#connect-dialog").close(); });
$("#btn-connect").addEventListener("click", () => openConnect("ext"));

// ---------- memory: notes about the user that every model sees (the user approves each one) ----------

async function refreshMemory() {
  try {
    state.memory = await api("/memory");
    updateMemoryBadge();
  } catch {}
  return state.memory;
}

function updateMemoryBadge() {
  const n = state.memory.items.filter((x) => x.status === "suggested").length;
  const b = $("#memory-badge");
  b.hidden = !n;
  b.textContent = fa(n);
  b.title = tn("memory.badge_title", n);
}

// Runs a memory API call, keeps state.memory in sync and redraws the open memory dialog.
async function memoryAct(call) {
  try {
    state.memory = await call();
    updateMemoryBadge();
    if ($("#memory-dialog").open) renderMemory();
    return true;
  } catch (err) {
    notify(err.message);
    return false;
  }
}

const memApprove = (id, text) =>
  memoryAct(() => api(`/memory/${id}`, { method: "PATCH", json: { status: "active", ...(text ? { text } : {}) } }));
const memDelete = (id) => memoryAct(() => api(`/memory/${id}`, { method: "DELETE" }));

// The card a model's suggestion shows in the chat: save, edit then save, or drop.
function memoryCard({ id, text }) {
  const node = el("div", { class: "memory-card" });
  const render = () => {
    const note = state.memory.items.find((n) => n.id === id);
    const status = !note ? "dropped" : note.status;
    node.classList.toggle("done", status !== "suggested");
    const label = t(`memory.card.${status}`);
    node.replaceChildren(el("span", { class: "mc-label" }, icon("memory"), label),
      el("span", { class: "mc-text" }, note ? note.text : text));
    if (status === "suggested") {
      node.append(
        el("button", { class: "primary", type: "button", onclick: async () => { if (await memApprove(id)) render(); } }, t("memory.save")),
        el("button", { type: "button", onclick: async () => {
          const txt = await askText(t("memory.edit_prompt"), note.text);
          if (txt && txt.trim() && (await memApprove(id, txt.trim()))) render();
        } }, t("memory.edit")),
        el("button", { type: "button", onclick: async () => { if (await memDelete(id)) render(); } }, t("memory.no")));
    }
  };
  render();
  return node;
}

async function openMemory() {
  closeNav();
  await refreshMemory();
  renderMemory();
  $("#memory-dialog").showModal();
  $("#memory-input").focus();
}

function memoryRow(n) {
  const src = n.source_title ? el("span", { class: "mem-src" }, t("memory.from", { title: n.source_title })) : null;
  const actions = n.status === "suggested"
    ? [el("button", { class: "primary", type: "button", onclick: () => memApprove(n.id) }, t("memory.save")),
       el("button", { type: "button", onclick: () => memDelete(n.id) }, t("memory.no"))]
    : [el("button", { type: "button", onclick: async () => {
          const txt = await askText(t("memory.edit_prompt"), n.text);
          if (txt && txt.trim() && txt.trim() !== n.text) memoryAct(() => api(`/memory/${n.id}`, { method: "PATCH", json: { text: txt.trim() } }));
        } }, t("memory.edit")),
       el("button", { type: "button", title: t("memory.delete"), "aria-label": t("memory.delete"), onclick: () => memDelete(n.id) }, icon("trash"))];
  return el("li", { class: n.status === "suggested" ? "pending" : "" },
    el("span", { class: "mem-text" }, n.text, src), el("span", { class: "mem-actions" }, ...actions));
}

function renderMemory() {
  const s = state.memory;
  $("#memory-enabled").checked = s.enabled;
  const pending = s.items.filter((n) => n.status === "suggested");
  const active = s.items.filter((n) => n.status === "active");
  $("#memory-suggested").hidden = !pending.length;
  $("#memory-suggested-list").replaceChildren(...pending.map(memoryRow));
  $("#memory-list").replaceChildren(...(active.length ? active.map(memoryRow)
    : [el("li", { class: "empty-row" }, t("memory.empty"))]));
  $("#memory-meta").textContent = active.length
    ? tn("memory.meta", active.length, { tokens: fa(s.tokens) }) +
      (s.all_fit ? "" : t("memory.meta_over", { cap: fa(s.token_cap) }))
    : "";
}

$("#btn-memory").addEventListener("click", openMemory);
$("#memory-close").addEventListener("click", () => $("#memory-dialog").close());
$("#memory-enabled").addEventListener("change", (e) =>
  memoryAct(() => api("/memory/settings", { method: "PUT", json: { enabled: e.target.checked } })));
$("#memory-add").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#memory-input");
  const text = input.value.trim();
  if (!text) return;
  if (await memoryAct(() => api("/memory", { method: "POST", json: { texts: [text] } }))) input.value = "";
});

// "Notes for memory" on an imported conversation: a model lists candidate notes, the user picks.
async function extractMemory(conv, btn) {
  const model = store.get("model");
  if (!model) { notify(t("memory.need_model")); return; }
  const tokens = conv.tokens > 120000 && conv.summary ? conv.summary_tokens : conv.tokens;
  if (!(await askConfirm(t("memory.extract_confirm", { model, tokens: fa(tokens) }), t("memory.extract_ok")))) return;
  const old = [...btn.childNodes];
  btn.disabled = true;
  btn.replaceChildren(el("span", { class: "spinner" }), " " + t("conv.reading"));
  let res;
  try {
    res = await api(`/conversations/${conv.id}/memory/extract`, { method: "POST", json: { model } });
  } catch (err) {
    notify(err.message);
    return;
  } finally {
    btn.disabled = false;
    btn.replaceChildren(...old);
  }
  const list = $("#extract-list");
  $("#extract-intro").textContent =
    t("memory.extract_intro", { title: conv.title });
  list.replaceChildren(...(res.suggestions.length ? res.suggestions.map((s, i) => {
    const cb = el("input", { type: "checkbox", id: `ex-${i}`, checked: !s.known, disabled: s.known });
    const text = el("input", { type: "text", value: s.text, maxlength: 500, disabled: s.known });
    return el("li", { class: s.known ? "known" : "" }, cb, el("span", { class: "mem-text" }, text,
      s.known ? el("span", { class: "mem-src" }, t("memory.known")) : null));
  }) : [el("li", { class: "empty-row" }, t("memory.none_found"))]));
  $("#extract-meta").textContent = "";
  $("#extract-save").disabled = !res.suggestions.some((s) => !s.known);
  $("#extract-save").onclick = async () => {
    const texts = [...list.querySelectorAll("li")]
      .filter((li) => li.querySelector("input[type=checkbox]")?.checked)
      .map((li) => li.querySelector("input[type=text]").value.trim()).filter(Boolean);
    if (!texts.length) { $("#extract-meta").textContent = t("memory.none_selected"); return; }
    if (await memoryAct(() => api("/memory", { method: "POST", json: { texts, source_conversation_id: conv.id } }))) {
      $("#extract-dialog").close();
      notify(tn("memory.added", texts.length));
    }
  };
  $("#extract-dialog").showModal();
}
$("#extract-close").addEventListener("click", () => $("#extract-dialog").close());

// ---------- handoff: continue this chat in the original AI chat, or in another chatbot ----------
// ConvoHub never writes into those sites itself: it prepares the text, and the user pastes it (or the
// extension puts it into the message box) and presses Send.

const ho = { chatId: null, getModel: null, info: null, upto: 0, format: "full", target: "new", req: 0 };
const hoTarget = () => document.querySelector('input[name="ho-target"]:checked')?.value || "new";
const hoFormat = () => document.querySelector('input[name="ho-format"]:checked')?.value || "full";

async function openHandoff(chatId, getModel) {
  ho.chatId = chatId;
  ho.getModel = getModel;
  try {
    ho.info = await api(`/chats/${chatId}/handoff`);
  } catch (err) {
    notify(err.message);
    return;
  }
  if (!ho.info.turns) {
    notify(t("handoff.no_messages"));
    return;
  }
  const hasRefs = ho.info.references.length > 0;
  const orig = document.querySelector('input[name="ho-target"][value="original"]');
  orig.disabled = !hasRefs;
  orig.closest(".ho-card").title = hasRefs ? "" : t("handoff.no_refs");
  document.querySelector(`input[name="ho-target"][value="${hasRefs ? "original" : "new"}"]`).checked = true;
  document.querySelector('input[name="ho-format"][value="full"]').checked = true;
  $("#ho-since").checked = true;
  $("#handoff-dialog").showModal();
  hoRefresh();
}

function hoRender() {
  const target = hoTarget();
  const last = ho.info.last;
  $("#ho-since-wrap").hidden = !(target === "original" && last);
  if (last) {
    $("#ho-since-label").textContent =
      t("handoff.since", { date: fmtDate(last.created_at), n: fa(ho.info.new_since_last) });
  }
  const origin = $("#ho-origin");
  origin.innerHTML = "";
  if (target === "original") {
    origin.append(t("handoff.origin"));
    ho.info.references.forEach((r, i) => {
      if (i) origin.append(t("common.list_sep"));
      origin.append(badge(r.source), t("handoff.ref_title", { title: r.title }));
      if (r.source_url) origin.append(el("a", { href: r.source_url, target: "_blank", rel: "noreferrer" }, t("handoff.open")));
    });
    if (ho.info.references.length > 1) origin.append(el("br"), t("handoff.many_refs"));
  } else {
    origin.textContent = t("handoff.new_note");
  }
}

async function hoRefresh() {
  hoRender();
  const target = hoTarget();
  const format = hoFormat();
  const text = $("#ho-text");
  const meta = $("#ho-meta");
  $("#ho-error").hidden = true;
  meta.innerHTML = "";
  ho.target = target;
  ho.format = format;
  const req = ++ho.req;
  const body = { target, since_last: $("#ho-since").checked, format };
  if (format === "brief") {
    const model = ho.getModel() || store.get("model") || "";
    text.value = "";
    text.placeholder = t("handoff.brief_none");
    if (!model) {
      meta.textContent = t("handoff.brief_need_model");
      return;
    }
    const btn = el("button", { type: "button" }, t("handoff.brief_build", { model }));
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = t("handoff.brief_writing");
      try {
        const res = await api(`/chats/${ho.chatId}/handoff/build`, { method: "POST", json: { ...body, model } });
        if (req !== ho.req) return;
        hoShow(res);
      } catch (err) {
        $("#ho-error").textContent = err.message;
        $("#ho-error").hidden = false;
        btn.disabled = false;
        btn.textContent = t("handoff.brief_build", { model });
      }
    };
    meta.append(btn, " ", el("span", {}, t("handoff.brief_note")));
    return;
  }
  text.placeholder = "…";
  try {
    const res = await api(`/chats/${ho.chatId}/handoff/build`, { method: "POST", json: body });
    if (req === ho.req) hoShow(res);
  } catch (err) {
    $("#ho-error").textContent = err.message;
    $("#ho-error").hidden = false;
  }
}

function hoShow(res) {
  ho.upto = res.upto;
  $("#ho-text").value = res.text;
  const meta = $("#ho-meta");
  meta.innerHTML = "";
  if (!res.text) {
    meta.textContent = t("handoff.nothing_new");
    return;
  }
  const what = ho.target === "original" ? tn("handoff.count", res.count) : t("handoff.refs_and_chat");
  meta.textContent = t("handoff.meta", { what, tokens: fa(res.tokens), chars: fa(res.text.length) }) +
    (res.text.length > 30000 ? t("handoff.long") : "") +
    t("handoff.editable");
}

async function hoDone(via) {
  const text = $("#ho-text").value;
  if (!text.trim()) {
    notify(t("handoff.nothing_to_send"));
    return false;
  }
  try {
    ho.info = { ...ho.info, ...(await api(`/chats/${ho.chatId}/handoff/done`, {
      method: "POST", json: { target: ho.target, format: ho.format, upto: ho.upto, via, text: via === "extension" ? text : null },
    })) };
    return true;
  } catch (err) {
    notify(err.message);
    return false;
  }
}

function hoFlash(btn, label) {
  const old = [...btn.childNodes];
  btn.textContent = label;
  setTimeout(() => btn.replaceChildren(...old), 1800);
}

document.querySelectorAll('input[name="ho-target"], input[name="ho-format"]').forEach((r) => r.addEventListener("change", hoRefresh));
$("#ho-since").addEventListener("change", hoRefresh);
$("#ho-copy").addEventListener("click", async (e) => {
  const text = $("#ho-text").value;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    $("#ho-text").select();
    if (!document.execCommand("copy")) { notify(t("common.copy_failed")); return; }
  }
  if (await hoDone("copy")) hoFlash(e.currentTarget || $("#ho-copy"), t("handoff.copied"));
});
$("#ho-file").addEventListener("click", async () => {
  const text = $("#ho-text").value;
  if (!text.trim() || !(await hoDone("file"))) return;
  const title = (ho.info.references[0]?.title || "convohub").replace(/[\\/:*?"<>|]+/g, " ").trim().slice(0, 60);
  const a = el("a", { href: URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" })),
    download: `ConvoHub handoff - ${title}.md` });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
});
$("#ho-ext").addEventListener("click", async () => {
  if (!(await hoDone("extension"))) return;
  const ref = ho.target === "original" && ho.info.references.length === 1 ? ho.info.references[0] : null;
  const meta = $("#ho-meta");
  meta.innerHTML = "";
  meta.append(t("handoff.ext_waiting"));
  if (ref?.source_url) meta.append(" ", el("a", { href: ref.source_url, target: "_blank", rel: "noreferrer" }, t("handoff.open_original")));
});
$("#ho-close").addEventListener("click", () => $("#handoff-dialog").close());

$("#btn-lang").addEventListener("click", () =>
  I18N.switchTo(I18N.lang === "fa" ? "en" : "fa").catch((e) => notify(e.message)));

(async () => {
  await I18N.init(); // the saved language (a new install saves the browser's); fills data-i18n texts
  if (I18N.platform === "darwin") { // path examples in this system's style (index.html has the Windows ones)
    $("#set-folders").placeholder = "/Users/me/Projects/MyApp";
    $("#set-skills").placeholder = "~/.claude/skills";
    $("#backup-folder").placeholder = "/Users/me/Backups/ConvoHub";
  }
  try {
    await refreshKeyState();
  } catch {}
  await refreshList().catch(showFatal);
  if (!state.current) showWelcome();
  if (!state.keySet) openKeyDialog();  // first run: ask for the key right away
  loadModels();
  refreshMemory();
  checkExtensionPending();
})();
