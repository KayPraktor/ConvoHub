const DEFAULTS = { server: "http://127.0.0.1:28765", autoSync: true };
const I = window.convohubI18n;
const t = I.t;
const $ = (id) => document.getElementById(id);
const say = (text) => { $("msg").textContent = text; };

// Puts the texts in the current language and sets the page direction (rtl for Persian).
function render() {
  document.documentElement.lang = I.lang;
  document.documentElement.dir = I.dir();
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
}

// Every answer from background.js carries the ConvoHub app's language.
const ask = (msg) => new Promise((resolve) => {
  chrome.runtime.sendMessage(msg, (res) => {
    if (res && res.lang && I.setLang(res.lang)) render();
    resolve(res);
  });
});

render();
ask({ type: "lang" });

chrome.storage.sync.get(DEFAULTS, (s) => {
  $("server").value = s.server;
  $("auto").checked = s.autoSync;
});

$("save").addEventListener("click", () => {
  const server = $("server").value.trim() || DEFAULTS.server;
  if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/?$/.test(server)) {
    say(t("optBadServer"));
    return;
  }
  chrome.storage.sync.set({ server, autoSync: $("auto").checked }, async () => {
    say(t("optSaved"));
    await ask({ type: "lang", force: true }); // a different address may be an app with another language
    say(t("optSaved"));
  });
});

$("test").addEventListener("click", async () => {
  say("…");
  const res = await ask({ type: "health" });
  if (!res || !res.ok) return say((res && res.error) || t("optNoConnect"));
  // Also asks the pairing-protected endpoint, so an unpaired extension shows up in ConvoHub to accept.
  const st = await ask({ type: "status", url: "https://chatgpt.com/" });
  if (st && st.ok) return say(t("optConnected", { version: res.data.version }));
  say(t("optUnpaired", { id: chrome.runtime.id }));
});
