// Talks to the local ConvoHub server. Content scripts can't call 127.0.0.1 themselves (the page's CORS rules
// apply to them), so they ask this service worker. Nothing here reads cookies or calls the AI sites' servers.
importScripts("i18n.js");
const I = self.convohubI18n;
const t = I.t;

const DEFAULTS = { server: "http://127.0.0.1:28765", autoSync: true };

// ConvoHub's default port moved from 8765 (Windows sometimes reserves it) to 28765.
const OLD_DEFAULT = /^http:\/\/(127\.0\.0\.1|localhost):8765\/?$/;

async function settings() {
  const s = { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
  if (OLD_DEFAULT.test(s.server)) {
    s.server = DEFAULTS.server;
    await chrome.storage.sync.set({ server: s.server });
  }
  return s;
}

async function call(path, init = {}) {
  const { server } = await settings();
  let res;
  try {
    res = await fetch(server.replace(/\/+$/, "") + path, {
      ...init,
      headers: { "X-ConvoHub-Client": "extension", "Content-Type": "application/json", ...(init.headers || {}) },
    });
  } catch (e) {
    return { ok: false, offline: true, error: t("offline") };
  }
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok) {
    return { ok: false, unpaired: !!(data && data.unpaired), error: (data && data.detail) || t("httpError", { status: String(res.status) }) };
  }
  return { ok: true, data };
}

// ---------- interface language: follows the ConvoHub app ----------
// /api/health says which language the app uses. It's cached for a minute; when ConvoHub is off, the last
// language the app reported is used, and if it was never reached, the browser's language.
const LANG_TTL_MS = 60 * 1000;
let langCheckedAt = 0;
let langPending = null;

function applyLang(l) {
  I.setLang(l);
  try { chrome.action.setTitle({ title: t("actionTitle") }); } catch {}
}

function noteHealth(res) {
  const l = res && res.ok && res.data && I.norm(res.data.lang);
  if (!l) return false;
  langCheckedAt = Date.now();
  applyLang(l);
  chrome.storage.local.set({ appLang: l });
  return true;
}

async function getLang(force = false) {
  if (!force && Date.now() - langCheckedAt < LANG_TTL_MS) return I.lang;
  if (!langPending) {
    langPending = (async () => {
      if (!noteHealth(await call("/api/health"))) {
        langCheckedAt = Date.now(); // don't ask again on every message while ConvoHub is off
        const { appLang } = await chrome.storage.local.get("appLang");
        applyLang(I.norm(appLang) || I.browserLang());
      }
      return I.lang;
    })().finally(() => { langPending = null; });
  }
  return langPending;
}

// A different server address may mean a different app (and language): check again on the next message.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "sync" && changes.server) langCheckedAt = 0;
});

async function handle(msg) {
  if (msg.type === "settings") return { ok: true, data: await settings() };
  if (msg.type === "lang") return { ok: true, data: { lang: await getLang(!!msg.force) } };
  if (msg.type === "health") {
    const res = await call("/api/health");
    noteHealth(res);
    return res;
  }
  if (msg.type === "status") {
    await getLang(); // each status check also refreshes the language when the cache is old
    return call("/api/extension/status?url=" + encodeURIComponent(msg.url));
  }
  if (msg.type === "sync") return call("/api/extension/sync", { method: "POST", body: JSON.stringify(msg.payload) });
  if (msg.type === "handoff-peek") return call("/api/extension/handoff/peek", { method: "POST" });
  if (msg.type === "handoff-take") return call("/api/extension/handoff/take", { method: "POST" });
  if (msg.type === "diagnose") return call("/api/extension/diagnose", { method: "POST", body: JSON.stringify(msg.payload) });
  return { ok: false, error: "unknown message" };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    const res = await handle(msg);
    // Every answer says which language to show, so open pages switch when the app's language changes.
    sendResponse({ ...res, lang: await getLang() });
  })();
  return true; // async response
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
getLang();
