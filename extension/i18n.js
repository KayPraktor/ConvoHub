// Texts of the extension in Persian (fa) and English (en), and a small t(key, vars) helper.
// The language follows the ConvoHub app (background.js asks /api/health), not the browser's language;
// the browser's language is only the fallback when ConvoHub has never been reached.
// Loaded by the content scripts (after extract.js), by options.html and by the service worker (importScripts).
(function (g) {
  const STRINGS = {
    fa: {
      // background.js
      offline: "ConvoHub روشن نیست (start.bat رو اجرا کن).",
      httpError: "خطا {status}",
      actionTitle: "ConvoHub — تنظیمات",
      // content.js: the "send" button
      reloaded: "افزونه دوباره بارگذاری شده؛ صفحه رو refresh کن.",
      noResponse: "افزونه جواب نداد",
      send: "بفرست به ConvoHub",
      offlineShort: "ConvoHub روشن نیست",
      unpaired: "توی ConvoHub «قبول» رو بزن",
      synced: "همگام با ConvoHub ({n} پیام)",
      syncedTitle: "پیام‌های جدید خودکار اضافه میشن. برای فرستادن کامل دوباره کلیک کن.",
      loadingAll: "در حال بارگذاری کل مکالمه…",
      loadingN: "در حال بارگذاری… ({n} پیام)",
      noMessages: "پیامی پیدا نشد",
      diagSaved: "یه گزارش از ساختار صفحه (بدون متن پیام‌ها) توی ConvoHub ذخیره شد: data/extension-diagnose.json",
      diagRetry: "اگه صفحه هنوز کامل باز نشده، چند ثانیه بعد دوباره امتحان کن.",
      error: "خطا",
      created: "ذخیره شد ({n} پیام)",
      appended: "{n} پیام جدید اضافه شد",
      replaced: "دوباره ذخیره شد ({n} پیام)",
      unaligned: "با نسخه‌ی قبلی جور نشد؛ برای فرستادن کامل کلیک کن",
      // content.js: the handoff button (a text ConvoHub prepared for this chat)
      hoPending: "گذاشتن متن ConvoHub توی جعبه‌ی پیام («{title}»)",
      hoPendingTitle: "متن رو توی جعبه‌ی پیام همین چت می‌ذاره. بعدش خودت نگاهش کن و Send رو بزن.",
      hoNothing: "متنی منتظر نیست",
      hoPlaced: "متن گذاشته شد؛ یه نگاه بنداز و Send رو بزن",
      hoCopied: "نتونستم متن رو توی جعبه‌ی پیام بذارم؛ کپی شد، روی جعبه کلیک کن و Ctrl+V بزن",
      hoRetry: "نتونستم متن رو توی جعبه‌ی پیام بذارم؛ روی جعبه‌ی پیام کلیک کن و دوباره این دکمه رو بزن",
      // options page
      optServer: "آدرس ConvoHub",
      optAuto: "پیام‌های جدید مکالمه‌هایی که قبلاً فرستادم خودکار اضافه بشن",
      optHint: "روی صفحه‌ی چت (Gemini، ChatGPT، Claude، Grok) دکمه‌ی «بفرست به ConvoHub» پایین سمت راست میاد. " +
        "افزونه فقط متن صفحه‌ای که باز کردی رو می‌خونه؛ نه کوکی، نه رمز، نه چیز دیگه.",
      optSave: "ذخیره",
      optTest: "تست اتصال",
      optBadServer: "آدرس باید روی همین کامپیوتر باشه، مثل http://127.0.0.1:28765",
      optSaved: "ذخیره شد.",
      optNoConnect: "وصل نشد",
      optConnected: "وصله ✓ (نسخه‌ی {version})",
      optUnpaired: "سرور روشنه ولی این افزونه هنوز تأیید نشده. توی صفحه‌ی ConvoHub «قبول» رو بزن " +
        "(یا این ID رو توی تنظیمات بذار): {id}",
    },
    en: {
      offline: "ConvoHub isn't running (run start.bat).",
      httpError: "Error {status}",
      actionTitle: "ConvoHub — Settings",
      reloaded: "The extension was reloaded; refresh this page.",
      noResponse: "The extension didn't respond",
      send: "Send to ConvoHub",
      offlineShort: "ConvoHub isn't running",
      unpaired: "Click “Accept” in ConvoHub",
      synced: "In sync with ConvoHub ({n} messages)",
      synced_one: "In sync with ConvoHub ({n} message)",
      syncedTitle: "New messages are added automatically. Click to send the whole chat again.",
      loadingAll: "Loading the whole conversation…",
      loadingN: "Loading… ({n} messages)",
      loadingN_one: "Loading… ({n} message)",
      noMessages: "No messages found",
      diagSaved: "A report of the page structure (without the message text) was saved in ConvoHub: data/extension-diagnose.json",
      diagRetry: "If the page hasn't finished loading, try again in a few seconds.",
      error: "Error",
      created: "Saved ({n} messages)",
      created_one: "Saved ({n} message)",
      appended: "{n} new messages added",
      appended_one: "{n} new message added",
      replaced: "Saved again ({n} messages)",
      replaced_one: "Saved again ({n} message)",
      unaligned: "Doesn't match the saved copy; click to send the whole chat",
      hoPending: "Put the ConvoHub text in the message box (“{title}”)",
      hoPendingTitle: "Puts the text in this chat's message box. Then look it over and press Send yourself.",
      hoNothing: "No text is waiting",
      hoPlaced: "Text placed; look it over and press Send",
      hoCopied: "Couldn't put the text in the message box; it was copied, so click the box and press Ctrl+V",
      hoRetry: "Couldn't put the text in the message box; click the message box and press this button again",
      optServer: "ConvoHub address",
      optAuto: "Automatically add new messages to chats I've already sent",
      optHint: "On a chat page (Gemini, ChatGPT, Claude, Grok) a “Send to ConvoHub” button appears at the bottom right. " +
        "The extension only reads the text of the page you have open: no cookies, no passwords, nothing else.",
      optSave: "Save",
      optTest: "Test connection",
      optBadServer: "The address must be on this computer, like http://127.0.0.1:28765",
      optSaved: "Saved.",
      optNoConnect: "Couldn't connect",
      optConnected: "Connected ✓ (version {version})",
      optUnpaired: "The server is on, but this extension isn't approved yet. Click “Accept” on the ConvoHub page " +
        "(or put this ID in its settings): {id}",
    },
  };

  const norm = (l) => (l === "fa" || l === "en" ? l : null);
  const browserLang = () => {
    try { return String(navigator.language || "").toLowerCase().startsWith("fa") ? "fa" : "en"; } catch { return "en"; }
  };
  let lang = browserLang();

  const num = (n) => Number(n).toLocaleString(lang === "fa" ? "fa-IR" : "en-US");

  // t("synced", { n: 3 }): numbers are formatted for the language; "key_one" is used for n === 1 when it exists.
  function t(key, vars) {
    const table = STRINGS[lang] || STRINGS.en;
    let s = (vars && vars.n === 1 && table[key + "_one"]) || table[key] || STRINGS.en[key] || key;
    if (vars) {
      s = s.replace(/\{(\w+)\}/g, (m, name) => {
        if (!(name in vars)) return m;
        const v = vars[name];
        return typeof v === "number" ? num(v) : String(v);
      });
    }
    return s;
  }

  g.convohubI18n = {
    STRINGS,
    t,
    num,
    norm,
    browserLang,
    get lang() { return lang; },
    dir: () => (lang === "fa" ? "rtl" : "ltr"),
    // Returns true when the language actually changed.
    setLang(l) {
      const n = norm(l);
      if (!n || n === lang) return false;
      lang = n;
      return true;
    },
  };
})(typeof self !== "undefined" ? self : window);
