const DEFAULTS = { server: "http://127.0.0.1:28765", autoSync: true };
const $ = (id) => document.getElementById(id);
const say = (t) => { $("msg").textContent = t; };

chrome.storage.sync.get(DEFAULTS, (s) => {
  $("server").value = s.server;
  $("auto").checked = s.autoSync;
});

$("save").addEventListener("click", () => {
  const server = $("server").value.trim() || DEFAULTS.server;
  if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/?$/.test(server)) {
    say("آدرس باید روی همین کامپیوتر باشه، مثل http://127.0.0.1:28765");
    return;
  }
  chrome.storage.sync.set({ server, autoSync: $("auto").checked }, () => say("ذخیره شد."));
});

$("test").addEventListener("click", () => {
  say("…");
  chrome.runtime.sendMessage({ type: "health" }, (res) => {
    if (!res || !res.ok) return say((res && res.error) || "وصل نشد");
    // Also asks the pairing-protected endpoint, so an unpaired extension shows up in ConvoHub to accept.
    chrome.runtime.sendMessage({ type: "status", url: "https://chatgpt.com/" }, (st) => {
      if (st && st.ok) return say(`وصله ✓ (نسخه‌ی ${res.data.version})`);
      say(`سرور روشنه ولی این افزونه هنوز تأیید نشده. توی صفحه‌ی ConvoHub «قبول» رو بزن ` +
          `(یا این ID رو توی تنظیمات بذار): ${chrome.runtime.id}`);
    });
  });
});
