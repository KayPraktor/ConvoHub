// Talks to the local ConvoHub server. Content scripts can't call 127.0.0.1 themselves (the page's CORS rules
// apply to them), so they ask this service worker. Nothing here reads cookies or calls the AI sites' servers.

const DEFAULTS = { server: "http://127.0.0.1:8765", autoSync: true };

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
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
    return { ok: false, offline: true, error: "ConvoHub روشن نیست (start.bat رو اجرا کن)." };
  }
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok) {
    return { ok: false, unpaired: !!(data && data.unpaired), error: (data && data.detail) || `خطا ${res.status}` };
  }
  return { ok: true, data };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    if (msg.type === "settings") return sendResponse({ ok: true, data: await settings() });
    if (msg.type === "health") return sendResponse(await call("/api/health"));
    if (msg.type === "status") {
      return sendResponse(await call("/api/extension/status?url=" + encodeURIComponent(msg.url)));
    }
    if (msg.type === "sync") {
      return sendResponse(await call("/api/extension/sync", { method: "POST", body: JSON.stringify(msg.payload) }));
    }
    if (msg.type === "diagnose") {
      return sendResponse(await call("/api/extension/diagnose", { method: "POST", body: JSON.stringify(msg.payload) }));
    }
    sendResponse({ ok: false, error: "unknown message" });
  })();
  return true; // async response
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
