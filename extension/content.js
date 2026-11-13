// The "send to ConvoHub" button on chat pages, and automatic updates for chats that were sent before.
(() => {
  const X = window.convohubExtract;
  if (!X || !X.site()) return;

  const QUIET_MS = 4000; // wait until the page stops changing (the answer has finished streaming)
  const ask = (msg) => new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(msg, (res) => resolve(res || { ok: false, error: "no response" }));
    } catch (e) {
      resolve({ ok: false, error: "افزونه دوباره بارگذاری شده؛ صفحه رو refresh کن." });
    }
  });
  const fa = (n) => Number(n).toLocaleString("fa-IR");

  // ---------- the button (in a shadow root so the site's CSS can't touch it) ----------
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;right:18px;bottom:84px;z-index:2147483646;";
  const root = host.attachShadow({ mode: "open" });
  // Built with DOM calls, not innerHTML: Gemini's page enforces Trusted Types, which rejects innerHTML.
  const style = document.createElement("style");
  style.textContent = `
    button { font: 13px Vazirmatn, Tahoma, sans-serif; direction: rtl; border: 1px solid #c7cdd8;
      border-radius: 999px; padding: 6px 12px; background: #fff; color: #1f2328; cursor: pointer;
      box-shadow: 0 2px 8px rgb(0 0 0 / .15); opacity: .85; display: flex; gap: 6px; align-items: center; }
    button:hover { opacity: 1; }
    button.synced { border-color: #16a34a; }
    button.error { border-color: #dc2626; color: #b91c1c; }
    button:disabled { cursor: progress; }
    @media (prefers-color-scheme: dark) { button { background: #1f2125; color: #e6e6e6; border-color: #3a3f47; } }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #9ca3af; }
    .synced .dot { background: #16a34a; }
    .error .dot { background: #dc2626; }`;
  const btn = document.createElement("button");
  btn.type = "button";
  const dot = document.createElement("span");
  dot.className = "dot";
  const label = document.createElement("span");
  label.className = "label";
  label.textContent = "بفرست به ConvoHub";
  btn.append(dot, label);
  root.append(style, btn);
  host.style.display = "none"; // shown once we know this page is a conversation (or the server is off)
  document.documentElement.appendChild(host);

  const show = (text, cls = "", title = "") => {
    label.textContent = text;
    btn.className = cls;
    btn.title = title || "ConvoHub";
  };

  // ---------- state per conversation page ----------
  let url = location.href;
  let known = false;       // this chat is already in the library: keep it updated
  let lastSent = "";       // fingerprint of what we last sent, to avoid repeats
  let timer = null;
  let busy = false;

  const fingerprint = (data) => {
    const last = data.messages[data.messages.length - 1];
    return `${data.messages.length}|${last ? last.content.length + last.content.slice(-80) : ""}`;
  };

  async function refreshStatus() {
    const st = await ask({ type: "status", url: location.href });
    if (!st.ok) {
      known = false;
      host.style.display = "";
      const label = st.offline ? "ConvoHub روشن نیست" : st.unpaired ? "توی ConvoHub «قبول» رو بزن" : "بفرست به ConvoHub";
      show(label, st.offline || st.unpaired ? "error" : "", st.error || "");
      return;
    }
    if (!st.data.supported) { host.style.display = "none"; return; }
    host.style.display = "";
    known = st.data.known;
    if (known) show(`همگام با ConvoHub (${fa(st.data.messages)} پیام)`, "synced", "پیام‌های جدید خودکار اضافه میشن. برای فرستادن کامل دوباره کلیک کن.");
    else show("بفرست به ConvoHub");
  }

  async function send(full) {
    if (busy) return;
    busy = true;
    btn.disabled = true;
    try {
      if (full) {
        show("در حال بارگذاری کل مکالمه…");
        await X.loadFullHistory((n) => show(`در حال بارگذاری… (${fa(n)} پیام)`));
      }
      const data = X.extract();
      if (!data || !data.messages.length) {
        // Send ConvoHub a structure-only report of this page (no message text) so the selectors can be fixed.
        const report = { ...X.diagnose(), extensionVersion: chrome.runtime.getManifest().version };
        const sent = await ask({ type: "diagnose", payload: report });
        show("پیامی پیدا نشد", "error", sent.ok
          ? "یه گزارش از ساختار صفحه (بدون متن پیام‌ها) توی ConvoHub ذخیره شد: data/extension-diagnose.json"
          : "اگه صفحه هنوز کامل باز نشده، چند ثانیه بعد دوباره امتحان کن.");
        return;
      }
      const res = await ask({ type: "sync", payload: { ...data, full } });
      if (!res.ok) {
        show(res.offline ? "ConvoHub روشن نیست" : res.unpaired ? "توی ConvoHub «قبول» رو بزن" : "خطا", "error", res.error);
        return;
      }
      lastSent = fingerprint(data);
      known = true;
      const r = res.data;
      const msg = {
        created: `ذخیره شد (${fa(r.total)} پیام)`,
        appended: `${fa(r.added)} پیام جدید اضافه شد`,
        replaced: `دوباره ذخیره شد (${fa(r.total)} پیام)`,
        unchanged: `همگام با ConvoHub (${fa(r.total)} پیام)`,
        unaligned: "با نسخه‌ی قبلی جور نشد؛ برای فرستادن کامل کلیک کن",
      }[r.mode];
      show(msg, r.mode === "unaligned" ? "error" : "synced");
    } finally {
      busy = false;
      btn.disabled = false;
    }
  }

  btn.addEventListener("click", () => send(true));

  // ---------- automatic updates for chats that are already in the library ----------
  const observer = new MutationObserver(() => {
    if (!known) return;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const { data: cfg } = await ask({ type: "settings" });
      if (!cfg || !cfg.autoSync || busy) return;
      const data = X.extract();
      if (!data || !data.messages.length || fingerprint(data) === lastSent) return;
      send(false);
    }, QUIET_MS);
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });

  // Chat sites change the URL without reloading when you open another chat.
  setInterval(() => {
    if (location.href !== url) {
      url = location.href;
      known = false;
      lastSent = "";
      refreshStatus();
    }
  }, 1000);

  // ---------- handoff: a text ConvoHub prepared for this chat ----------
  // ConvoHub keeps it waiting; this button puts it into the message box. The user reads it and presses Send.
  const hoHost = document.createElement("div");
  hoHost.style.cssText = "position:fixed;right:18px;bottom:128px;z-index:2147483646;display:none;";
  const hoRoot = hoHost.attachShadow({ mode: "open" });
  const hoStyle = document.createElement("style");
  hoStyle.textContent = style.textContent + " button { border-color: #0f766e; } button.done { border-color: #16a34a; }";
  const hoBtn = document.createElement("button");
  hoBtn.type = "button";
  hoRoot.append(hoStyle, hoBtn);
  document.documentElement.appendChild(hoHost);
  let hoText = null;      // taken from ConvoHub but not placed yet (e.g. no message box found)
  let hoShownUntil = 0;   // keep the result message on screen for a moment

  const hoShow = (text, cls = "", title = "") => {
    hoBtn.textContent = text;
    hoBtn.className = cls;
    hoBtn.title = title;
    hoHost.style.display = "";
  };

  async function hoCheck() {
    if (document.visibilityState !== "visible" || Date.now() < hoShownUntil || hoText) return;
    const res = await ask({ type: "handoff-peek" });
    if (res.ok && res.data.pending) {
      hoShow(`گذاشتن متن ConvoHub توی جعبه‌ی پیام («${res.data.title}»)`, "", "متن رو توی جعبه‌ی پیام همین چت می‌ذاره. بعدش خودت نگاهش کن و Send رو بزن.");
    } else {
      hoHost.style.display = "none";
    }
  }

  async function hoPlace() {
    if (!hoText) {
      const res = await ask({ type: "handoff-take" });
      if (!res.ok) { hoShow(res.error || "متنی منتظر نیست", "error"); hoShownUntil = Date.now() + 6000; return; }
      hoText = res.data.text;
    }
    const r = await X.insertIntoComposer(hoText);
    if (r.ok) {
      hoText = null;
      hoShow("متن گذاشته شد؛ یه نگاه بنداز و Send رو بزن", "done");
    } else {
      // No message box found, or the text didn't show up in it: put it on the clipboard so it's not lost.
      try {
        await navigator.clipboard.writeText(hoText);
        hoText = null;
        hoShow("نتونستم متن رو توی جعبه‌ی پیام بذارم؛ کپی شد، روی جعبه کلیک کن و Ctrl+V بزن", "error");
      } catch {
        hoShow("نتونستم متن رو توی جعبه‌ی پیام بذارم؛ روی جعبه‌ی پیام کلیک کن و دوباره این دکمه رو بزن", "error");
        return;
      }
    }
    hoShownUntil = Date.now() + 8000;
  }

  hoBtn.addEventListener("click", hoPlace);
  setInterval(hoCheck, 3000);
  document.addEventListener("visibilitychange", hoCheck);
  hoCheck();

  refreshStatus();
})();
