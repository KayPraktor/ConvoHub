"use strict";

// Interface language (fa / en). Loaded before app.js.
//
// - The language is known synchronously when this file runs (cached in localStorage, else the browser
//   language), so app.js may call t() anywhere, even at the top level. Changing the language reloads the page.
// - I18N.init() asks the server for the saved choice. A new install has none: we keep the browser's guess and
//   save it. If the server's choice differs from the cached one (another browser changed it), we reload once.
// - Dictionaries register themselves with I18N.add({ fa: {...}, en: {...} }) (static/locales/*.js).
// - Static HTML uses data-i18n="key" (text), data-i18n-title, data-i18n-placeholder, data-i18n-aria-label,
//   and data-i18n-html (only for dictionary entries that contain markup; never for user data).
// - Platform: texts about Windows-only things (the Recycle Bin, drive letters...) can have a macOS variant
//   "<key>.mac"; t() picks it on a Mac. The browser runs on the same computer as the server, so the browser's
//   guess is used until I18N.init() reads the server's answer (/api/health "platform").

const I18N = (() => {
  const LANGS = ["fa", "en"];
  const dicts = { fa: {}, en: {} };
  const guess = () => ((navigator.language || "").toLowerCase().startsWith("fa") ? "fa" : "en");
  let cached = null;
  try { cached = localStorage.getItem("lang"); } catch {}
  let lang = LANGS.includes(cached) ? cached : guess();
  let platform = /Mac/i.test(navigator.userAgentData?.platform || navigator.platform || navigator.userAgent || "")
    ? "darwin" : /Win/i.test(navigator.platform || navigator.userAgent || "") ? "win32" : "linux";

  const setDocLang = (l) => {
    document.documentElement.lang = l;
    document.documentElement.dir = l === "fa" ? "rtl" : "ltr";
  };
  setDocLang(lang);

  function add(d) {
    for (const l of Object.keys(d)) Object.assign((dicts[l] ||= {}), d[l]);
  }

  function t(key, vars) {
    const mac = platform === "darwin" ? `${key}.mac` : null;
    let s = (mac && (dicts[lang][mac] ?? dicts.en[mac])) ?? dicts[lang][key] ?? dicts.en[key] ?? dicts.fa[key];
    if (s === undefined) {
      console.warn("i18n: missing key", key);
      return key;
    }
    if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
    return s;
  }

  function apply(root = document) {
    for (const e of root.querySelectorAll("[data-i18n]")) e.textContent = t(e.dataset.i18n);
    for (const e of root.querySelectorAll("[data-i18n-html]")) e.innerHTML = t(e.dataset.i18nHtml);
    for (const e of root.querySelectorAll("[data-i18n-title]")) e.title = t(e.dataset.i18nTitle);
    for (const e of root.querySelectorAll("[data-i18n-placeholder]")) e.placeholder = t(e.dataset.i18nPlaceholder);
    for (const e of root.querySelectorAll("[data-i18n-aria-label]")) e.setAttribute("aria-label", t(e.dataset.i18nAriaLabel));
  }

  const remember = (l) => { try { localStorage.setItem("lang", l); } catch {} };

  async function init() {
    let saved = null;
    const health = fetch("/api/health").then((r) => r.json()).catch(() => null);
    try {
      saved = (await (await fetch("/api/settings/lang")).json()).lang;
    } catch {}
    const h = await health;
    if (h && ["win32", "darwin", "linux"].includes(h.platform)) platform = h.platform;
    if (!saved) {
      saved = lang; // new install: keep the guess and save it
      try {
        await fetch("/api/settings/lang", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: saved }) });
      } catch {}
    }
    remember(saved);
    if (saved !== lang) {
      location.reload(); // texts already built in the other language
      return new Promise(() => {}); // never continue on this page
    }
    apply();
  }

  async function switchTo(l) {
    if (!LANGS.includes(l) || l === lang) return;
    const res = await fetch("/api/settings/lang", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: l }) });
    if (!res.ok) throw new Error(`${res.status}`);
    remember(l);
    location.reload();
  }

  return {
    LANGS, add, t, apply, init, switchTo,
    get lang() { return lang; },
    get platform() { return platform; }, // "win32" | "darwin" | "linux"
    get dir() { return lang === "fa" ? "rtl" : "ltr"; },
    get locale() { return lang === "fa" ? "fa-IR" : "en-US"; },
  };
})();

const t = I18N.t;
