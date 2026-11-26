"""Texts the server shows to the user, in Persian and English (see i18n.py).

Keys are grouped by area: "api.", "launcher.", "import.", "link.", "remote.", ...
Keep the Persian casual (like the rest of the app) and the English plain and short.
Placeholders are str.format names ({path}, {n}...); both languages of a key must use the same ones
(tests/test_i18n.py checks this).
A key ending in "_mac" is the macOS variant of the key without it (texts about Windows-only things such as
drive letters); i18n.tp() picks it on a Mac. It must use the same placeholders as its base key.
"""

MESSAGES: dict[str, dict[str, str]] = {
    # ---------- web API ----------
    "api.not_found": {"fa": "پیدا نشد.", "en": "Not found."},
    "api.bad_lang": {"fa": "زبان پشتیبانی نمیشه.", "en": "Unsupported language."},
    "api.new_chat_title": {"fa": "گفتگوی جدید", "en": "New chat"},
    "api.no_summary": {"fa": "مدل خلاصه‌ای برنگردوند.", "en": "The model returned no summary."},
    "api.link_timeout": {
        "fa": "خوندن لینک بیشتر از ۹۰ ثانیه طول کشید. شبکه یا VPN رو چک کن.",
        "en": "Reading the link took more than 90 seconds. Check your network or VPN.",
    },
    "api.not_from_link": {"fa": "این مکالمه از لینک نیومده.", "en": "This conversation wasn't imported from a link."},
    "api.too_many_models": {"fa": "حداکثر {n} مدل با هم.", "en": "At most {n} models at once."},
    "api.answer_cut": {"fa": "[جواب ناقص ماند]", "en": "[Answer incomplete]"},
    "api.approval_gone": {
        "fa": "این درخواست دیگه منتظر جواب نیست.",
        "en": "This request is no longer waiting for an answer.",
    },
    "api.pick_summary_model": {"fa": "برای خلاصه یه مدل انتخاب کن.", "en": "Pick a model for the summary."},
    "api.nothing_to_send": {"fa": "متنی برای فرستادن نیست.", "en": "There's no text to send."},
    "api.bad_model_reply": {
        "fa": "جواب مدل قابل خوندن نبود. یه مدل دیگه امتحان کن.",
        "en": "Couldn't read the model's reply. Try another model.",
    },
    "api.no_pending_handoff": {
        "fa": "متنی منتظر نیست. توی ConvoHub دوباره «بفرست به افزونه» رو بزن.",
        "en": "No text is waiting. In ConvoHub, click “Send to extension” again.",
    },
    "api.backup_failed": {"fa": "بکاپ گرفته نشد: {error}", "en": "Backup failed: {error}"},
    "api.external_server": {
        "fa": "این نسخه از بیرون اجرا شده (مثلاً با uvicorn مستقیم)؛ از همونجا ببندش.",
        "en": "This copy was started from outside (for example, directly with uvicorn); stop it from there.",
    },
    "api.bad_key": {
        "fa": "این شبیه کلید OpenRouter نیست (باید با sk-or- شروع بشه).",
        "en": "This doesn't look like an OpenRouter key (it should start with sk-or-).",
    },
    "api.folder_missing": {"fa": "این پوشه پیدا نشد: {path}", "en": "Folder not found: {path}"},
    "api.open_folder_failed": {"fa": "نتونستم پوشه رو باز کنم: {path}", "en": "Couldn't open the folder: {path}"},
    "api.extension_unpaired": {
        "fa": "این افزونه هنوز توی ConvoHub تأیید نشده. صفحه‌ی ConvoHub رو باز کن و «قبول» رو بزن.",
        "en": "This extension isn't approved in ConvoHub yet. Open the ConvoHub page and click “Accept”.",
    },

    # ---------- importing: pasted text, files, the browser extension ----------
    "import.empty_text": {"fa": "متن خالیه.", "en": "The text is empty."},
    "import.untitled": {"fa": "مکالمه‌ی بدون عنوان", "en": "Untitled conversation"},
    "import.ext_unsupported_page": {
        "fa": "این صفحه یه مکالمه‌ی پشتیبانی‌شده نیست.",
        "en": "This page isn't a supported conversation.",
    },
    "import.ext_no_messages": {"fa": "پیامی توی صفحه پیدا نشد.", "en": "No messages found on the page."},

    "file.too_big": {"fa": "فایل خیلی بزرگه (بیشتر از ۲۰۰ مگابایت).", "en": "The file is too big (over 200 MB)."},
    "file.bad_json": {"fa": "فایل JSON خرابه یا کامل نیست.", "en": "The JSON file is broken or incomplete."},
    "file.unknown_json": {
        "fa": "این فرمت JSON رو نمی‌شناسم. فعلاً خروجی ChatGPT و Claude پشتیبانی میشه.",
        "en": "Unknown JSON format. For now, ChatGPT and Claude exports are supported.",
    },
    "file.no_conversations": {"fa": "توی فایل مکالمه‌ای پیدا نشد.", "en": "No conversations found in the file."},
    "file.empty": {"fa": "فایل خالیه.", "en": "The file is empty."},
    "file.unsupported": {
        "fa": "فرمت فایل پشتیبانی نمیشه. فایل .txt، .md یا .json بده.",
        "en": "Unsupported file type. Use a .txt, .md or .json file.",
    },

    # ---------- importing from a share link ----------
    "link.unknown": {
        "fa": "این لینک رو نمی‌شناسم. لینک share از Gemini، Grok، Claude یا ChatGPT بده "
              "(مثلاً https://gemini.google.com/share/...).",
        "en": "Unknown link. Use a share link from Gemini, Grok, Claude or ChatGPT "
              "(for example https://gemini.google.com/share/...).",
    },
    "link.no_playwright": {
        "fa": "Playwright نصب نیست. یه بار `uv sync` رو اجرا کن.",
        "en": "Playwright isn't installed. Run `uv sync` once.",
    },
    "link.timeout": {
        "fa": "صفحه توی ۳۰ ثانیه باز نشد. شاید این سایت بدون VPN باز نمیشه؛ VPN رو چک کن و دوباره امتحان کن.",
        "en": "The page didn't open within 30 seconds. This site may need a VPN; check it and try again.",
    },
    "link.open_failed": {
        "fa": "نتونستم صفحه رو باز کنم (شبکه یا آدرس). شاید این سایت بدون VPN باز نمیشه.",
        "en": "Couldn't open the page (network or address). This site may need a VPN.",
    },
    "link.login": {
        "fa": "این لینک لاگین می‌خواد؛ احتمالاً خصوصیه یا پاک شده. لینک share عمومی بده.",
        "en": "This link asks for a login; it's probably private or deleted. Use a public share link.",
    },
    "link.bot_wall": {
        "fa": "این سایت جلوی مرورگر خودکار رو گرفت (بررسی ضدربات). فعلاً متن مکالمه رو کپی و paste کن.",
        "en": "The site blocked the automated browser (bot check). For now, copy and paste the conversation text.",
    },
    "link.no_conversation": {
        "fa": "توی این صفحه مکالمه‌ای پیدا نشد. یا لینک پاک شده/خصوصیه، یا ظاهر سایت عوض شده. "
              "فعلاً متن مکالمه رو کپی و paste کن.",
        "en": "No conversation found on this page. The link may be deleted or private, or the site's layout "
              "changed. For now, copy and paste the conversation text.",
    },
    "link.no_browser": {
        "fa": "برای ایمپورت از لینک، Chrome یا Microsoft Edge باید روی این سیستم نصب باشه و هیچ‌کدوم پیدا نشد. "
              "یکی‌شون رو نصب کن (Edge معمولاً همراه ویندوزه)، یا متن مکالمه رو کپی و paste کن.",
        "en": "Importing from a link needs Chrome or Microsoft Edge on this computer, and neither was found. "
              "Install one of them (Edge usually comes with Windows), or copy and paste the conversation text.",
    },
    "link.no_browser_mac": {
        "fa": "برای ایمپورت از لینک، Google Chrome یا Microsoft Edge باید توی پوشه‌ی Applications مک نصب باشه "
              "و هیچ‌کدوم پیدا نشد. یکی‌شون رو نصب کن، یا متن مکالمه رو کپی و paste کن.",
        "en": "Importing from a link needs Google Chrome or Microsoft Edge in your Mac's Applications folder, and "
              "neither was found. Install one of them, or copy and paste the conversation text.",
    },

    # ---------- agent mode ----------
    "agent.mcp_failed": {"fa": "سرور MCP «{server}» وصل نشد: {error}", "en": "MCP server “{server}” didn't connect: {error}"},
    "agent.max_steps": {"fa": "ایجنت بعد از {n} مرحله متوقف شد.", "en": "The agent stopped after {n} steps."},
    # UI labels quoted in the prompts, so the model names the button the user actually sees.
    "agent.ui_agent_mode": {"fa": "«حالت ایجنت»", "en": "“Agent mode”"},
    "agent.ui_continue": {"fa": "«ادامه بده»", "en": "“continue”"},

    "settings.label_allowed": {"fa": "پوشه‌های مجاز", "en": "Allowed folders"},
    "settings.label_skills": {"fa": "پوشه‌های skill", "en": "Skill folders"},
    "settings.not_list": {"fa": "{label} باید لیست باشه.", "en": "{label} must be a list."},
    "settings.path_not_absolute": {
        "fa": "مسیر باید کامل باشه (مثل D:\\Projects\\MyApp): {path}",
        "en": "The path must be a full path (like D:\\Projects\\MyApp): {path}",
    },
    "settings.path_not_absolute_mac": {
        "fa": "مسیر باید کامل باشه (مثل /Users/me/Projects/MyApp): {path}",
        "en": "The path must be a full path (like /Users/me/Projects/MyApp): {path}",
    },
    "settings.folder_missing": {"fa": "این پوشه وجود نداره: {path}", "en": "This folder doesn't exist: {path}"},
    "settings.whole_drive": {
        "fa": "کل یه درایو رو نمیشه داد؛ یه پوشه‌ی مشخص بده: {path}",
        "en": "You can't allow a whole drive; choose a specific folder: {path}",
    },
    "settings.whole_drive_mac": {
        "fa": "کل دیسک (/) رو نمیشه داد؛ یه پوشه‌ی مشخص بده: {path}",
        "en": "You can't allow the whole disk (/); choose a specific folder: {path}",
    },
    "settings.mcp_not_object": {"fa": "تنظیمات MCP باید یه آبجکت JSON باشه.", "en": "MCP settings must be a JSON object."},
    "settings.mcp_no_command": {
        "fa": "سرور MCP «{name}» باید command یا url داشته باشه.",
        "en": "MCP server “{name}” needs a command or a url.",
    },
    "settings.mcp_bad_args": {"fa": "args سرور «{name}» باید لیست باشه.", "en": "The args of server “{name}” must be a list."},
    "settings.always_allow_broken": {"fa": "لیست «همیشه اجازه بده» خرابه.", "en": "The “always allow” list is broken."},

    # ---------- backups ----------
    "backup.path_not_absolute": {
        "fa": "مسیر باید کامل باشه، مثل D:\\Backups\\ConvoHub",
        "en": "The path must be a full path, like D:\\Backups\\ConvoHub",
    },
    "backup.path_not_absolute_mac": {
        "fa": "مسیر باید کامل باشه، مثل /Users/me/Backups/ConvoHub",
        "en": "The path must be a full path, like /Users/me/Backups/ConvoHub",
    },
    "backup.folder_missing": {"fa": "این پوشه وجود نداره: {path}", "en": "This folder doesn't exist: {path}"},
    "backup.bad_name": {"fa": "اسم فایل بکاپ معتبر نیست.", "en": "Invalid backup file name."},
    "backup.not_found": {"fa": "این بکاپ پیدا نشد.", "en": "Backup not found."},

    # ---------- browser extension pairing ----------
    "extension.bad_id": {
        "fa": "ID افزونه معتبر نیست (از صفحه‌ی chrome://extensions کپی کن).",
        "en": "Invalid extension ID (copy it from the chrome://extensions page).",
    },

    # ---------- OpenRouter ----------
    "openrouter.no_key": {
        "fa": "کلید OpenRouter توی فایل .env نیست. کلید رو بذار و برنامه رو دوباره اجرا کن.",
        "en": "There's no OpenRouter key in the .env file. Add the key and start the app again.",
    },
    "openrouter.network": {
        "fa": "به OpenRouter وصل نشدم. اینترنت یا VPN رو چک کن و دوباره امتحان کن. ({error})",
        "en": "Couldn't connect to OpenRouter. Check your internet or VPN and try again. ({error})",
    },
    "openrouter.status_400": {"fa": "درخواست رو قبول نکرد", "en": "The request was rejected"},
    "openrouter.status_401": {"fa": "کلید OpenRouter معتبر نیست", "en": "The OpenRouter key is invalid"},
    "openrouter.status_402": {"fa": "اعتبار حساب OpenRouter تموم شده", "en": "Your OpenRouter credit has run out"},
    "openrouter.status_403": {
        "fa": "این درخواست اجازه نداره (شاید فیلتر محتوای مدل)",
        "en": "This request isn't allowed (maybe the model's content filter)",
    },
    "openrouter.status_404": {"fa": "این مدل پیدا نشد", "en": "Model not found"},
    "openrouter.status_408": {"fa": "مدل دیر جواب داد", "en": "The model took too long to answer"},
    "openrouter.status_413": {"fa": "متن برای این مدل زیادی بلنده", "en": "The text is too long for this model"},
    "openrouter.status_429": {"fa": "تعداد درخواست‌ها زیاد شده؛ کمی صبر کن", "en": "Too many requests; wait a little"},
    "openrouter.status_502": {"fa": "سرویس‌دهنده‌ی مدل در دسترس نیست", "en": "The model's provider is unavailable"},
    "openrouter.status_503": {
        "fa": "هیچ سرویس‌دهنده‌ای برای این مدل در دسترس نیست",
        "en": "No provider is available for this model",
    },
    "openrouter.status_other": {"fa": "خطای OpenRouter (کد {status})", "en": "OpenRouter error (code {status})"},
    "openrouter.stream_error": {"fa": "مدل وسط جواب خطا داد: {error}", "en": "The model failed mid-answer: {error}"},

    # ---------- the OpenRouter key entered in the UI ----------
    "key.check_network": {
        "fa": "به OpenRouter وصل نشدم ({error})؛ کلید ذخیره شد ولی بررسی نشد.",
        "en": "Couldn't reach OpenRouter ({error}); the key was saved but not checked.",
    },
    "key.rejected": {
        "fa": "OpenRouter این کلید رو قبول نکرد. دوباره از سایت OpenRouter کپی‌اش کن.",
        "en": "OpenRouter didn't accept this key. Copy it again from the OpenRouter website.",
    },
    "key.check_unexpected": {
        "fa": "OpenRouter جواب غیرمنتظره داد (کد {status})؛ کلید ذخیره شد ولی بررسی نشد.",
        "en": "OpenRouter gave an unexpected answer (code {status}); the key was saved but not checked.",
    },

    # ---------- memory ----------
    "memory.empty": {"fa": "متن یادداشت خالیه.", "en": "The note is empty."},
    "memory.too_long": {"fa": "یادداشت حداکثر {n} حرف باشه.", "en": "A note can be at most {n} characters."},
    "memory.full": {
        "fa": "حافظه پره ({n} یادداشت). چندتا رو پاک کن.",
        "en": "Memory is full ({n} notes). Delete some.",
    },

    # ---------- remote connector (online address for Gemini and other cloud MCP clients) ----------
    "remote.download_failed": {"fa": "دانلود نشد (کد {status}).", "en": "Download failed (code {status})."},
    "remote.download_incomplete": {"fa": "فایل دانلودشده ناقصه.", "en": "The downloaded file is incomplete."},
    "remote.bad_signature": {
        "fa": "امضای فایل دانلودشده معتبر نیست، پس نصب نشد. ({detail})",
        "en": "The downloaded file's signature isn't valid, so it wasn't installed. ({detail})",
    },
    "remote.github_unreachable": {
        "fa": "به GitHub وصل نشد. اینترنت یا VPN رو چک کن و دوباره امتحان کن.",
        "en": "Couldn't connect to GitHub. Check your internet or VPN and try again.",
    },
    "remote.not_ready": {
        "fa": "هنوز آماده نیست (معمولاً کمتر از یه دقیقه طول می‌کشه).",
        "en": "Not ready yet (this usually takes less than a minute).",
    },
    "remote.connect_failed": {"fa": "وصل نشد ({error}).", "en": "Couldn't connect ({error})."},
    "remote.reachable": {"fa": "از اینترنت در دسترسه.", "en": "Reachable from the internet."},
    "remote.bad_status": {"fa": "جواب {status} اومد.", "en": "Got answer {status}."},
    "remote.unreachable": {
        "fa": "هنوز از اینترنت در دسترس نیست: {detail} شاید اینترنت یا VPN اجازه نمیده؛ خاموش و دوباره روشنش کن.",
        "en": "Not reachable from the internet yet: {detail} Your internet or VPN may be blocking it; "
              "turn it off and on again.",
    },
    "remote.no_cloudflared": {
        "fa": "ابزار تونل Cloudflare (cloudflared) هنوز نصب نیست. اول «نصب خودکار» رو بزن.",
        "en": "The Cloudflare tunnel tool (cloudflared) isn't installed yet. Click “Install automatically” first.",
    },
    "remote.no_cloudflared_mac": {
        "fa": "ابزار تونل Cloudflare (cloudflared) هنوز نصب نیست. با Homebrew نصبش کن: brew install cloudflared "
              "و بعد «دوباره بررسی کن» رو بزن.",
        "en": "The Cloudflare tunnel tool (cloudflared) isn't installed yet. Install it with Homebrew: "
              "brew install cloudflared, then press “Check again”.",
    },
    # Shown instead of the one-click install where ConvoHub can't install cloudflared itself (not Windows).
    "remote.install_unavailable": {
        "fa": "اینجا ConvoHub نمی‌تونه خودش نصبش کنه. cloudflared رو با package manager سیستمت نصب کن "
              "و بعد «دوباره بررسی کن» رو بزن.",
        "en": "ConvoHub can't install it by itself here. Install cloudflared with your system's package manager, "
              "then press “Check again”.",
    },
    "remote.install_unavailable_mac": {
        "fa": "با Homebrew نصبش کن: brew install cloudflared و بعد «دوباره بررسی کن» رو بزن.",
        "en": "Install it with Homebrew: brew install cloudflared, then press “Check again”.",
    },
    "remote.tunnel_failed": {
        "fa": "تونل Cloudflare بالا نیومد. شاید اینترنت یا VPN اجازه نمیده؛ یه بار دیگه امتحان کن.",
        "en": "The Cloudflare tunnel didn't start. Your internet or VPN may be blocking it; try again.",
    },

    # ---------- launcher (message boxes before the web page opens) ----------
    "launcher.port_how": {
        "fa": "یه عدد دیگه (مثلاً 38765) رو به‌عنوان CONVOHUB_PORT توی فایل .env بذار، "
              "و همون آدرس رو توی تنظیمات افزونه هم عوض کن.",
        "en": "set another number (for example 38765) as CONVOHUB_PORT in the .env file, "
              "and change the address in the extension's settings too.",
    },
    "launcher.port_reserved": {
        "fa": "ConvoHub نتونست روی پورت {port} بالا بیاد، چون ویندوز این پورت رو رزرو کرده "
              "(معمولاً Hyper-V، WSL یا Docker این کار رو می‌کنن).\n\n{how}",
        "en": "ConvoHub couldn't start on port {port} because Windows has reserved this port "
              "(Hyper-V, WSL or Docker usually do this).\n\nTo fix it, {how}",
    },
    "launcher.port_taken": {
        "fa": "پورت {port} دست یه برنامه‌ی دیگه‌ست. اون برنامه رو ببند، یا {how}",
        "en": "Port {port} is used by another program. Close that program, or {how}",
    },
    "launcher.port_other": {
        "fa": "پورت {port} دست یه برنامه‌ی دیگه‌ست. اون برنامه رو ببند یا CONVOHUB_PORT رو توی فایل .env عوض کن.",
        "en": "Port {port} is used by another program. Close that program or change CONVOHUB_PORT in the .env file.",
    },
    "launcher.not_running": {"fa": "ConvoHub روشن نیست.", "en": "ConvoHub isn't running."},
    "launcher.stopped": {"fa": "ConvoHub خاموش شد.", "en": "ConvoHub has stopped."},
    "launcher.stop_failed": {"fa": "نتونستم ConvoHub رو خاموش کنم.", "en": "Couldn't stop ConvoHub."},
    "launcher.start_failed": {
        "fa": "ConvoHub بالا نیومد. جزئیاتش توی این فایل هست:\n{log}",
        "en": "ConvoHub didn't start. The details are in this file:\n{log}",
    },

    # ---------- desktop shortcuts ----------
    "shortcut.stop_name": {"fa": "ConvoHub - خاموش", "en": "ConvoHub - Stop"},
    "shortcut.no_pythonw": {
        "fa": "pythonw.exe پیدا نشد کنار {exe}. اول `uv sync` رو اجرا کن.",
        "en": "pythonw.exe wasn't found next to {exe}. Run `uv sync` first.",
    },
    "shortcut.windows_only": {"fa": "این شورتکات فقط برای ویندوزه.", "en": "These shortcuts are for Windows only."},
    "shortcut.windows_only_mac": {
        "fa": "این شورتکات‌ها فقط برای ویندوزن. روی مک، ConvoHub رو با ‎./start.sh یا خود برنامه‌ی ConvoHub "
              "(توی Applications) باز کن.",
        "en": "These shortcuts are for Windows only. On a Mac, start ConvoHub with ./start.sh or the ConvoHub app "
              "(in Applications).",
    },
    "shortcut.failed": {"fa": "ساختن شورتکات نشد:\n{error}", "en": "Couldn't create the shortcuts:\n{error}"},
    "shortcut.failed_one": {"fa": "ساختن شورتکات «{name}» نشد.", "en": "Couldn't create the shortcut “{name}”."},
    "shortcut.created": {"fa": "ساخته شد: {path}", "en": "Created: {path}"},

    # ---------- handoff: text the user pastes into another chatbot ----------
    "handoff.compact_note": {"fa": "(متن کامل این بخش توی ConvoHub هست.)", "en": "(The full text of this part is in ConvoHub.)"},
    "handoff.intro_original": {
        "fa": "این ادامه‌ی همین گفتگوی ماست که توی یه ابزار دیگه (ConvoHub) با یه مدل دیگه ادامه پیدا کرد. "
              "بخونش و از این به بعد با در نظر گرفتنش ادامه بده. لازم نیست تکرارش کنی؛ کوتاه بگو چی دستت اومد، "
              "اگه با چیزی موافق نیستی بگو، و بعد منتظر پیام بعدی من باش.",
        "en": "This is the continuation of our conversation, carried on in another tool (ConvoHub) with another "
              "model. Read it and take it into account from now on. No need to repeat it; briefly say what you "
              "took from it, say if you disagree with anything, and then wait for my next message.",
    },
    "handoff.intro_new": {
        "fa": "سلام. این پیش‌زمینه‌ی یه کار در جریانه که قبلاً با چند دستیار هوش مصنوعی پیش بردم. "
              "بخونش تا در جریان باشی. لازم نیست تکرارش کنی؛ کوتاه بگو چی دستت اومد و بعد منتظر پیام بعدی من باش.",
        "en": "Hi. This is the background of ongoing work I've done with several AI assistants. Read it so you're "
              "up to speed. No need to repeat it; briefly say what you took from it and then wait for my next message.",
    },
    "handoff.me": {"fa": "**من:**", "en": "**Me:**"},
    "handoff.assistant": {"fa": "**دستیار:**", "en": "**Assistant:**"},
    "handoff.assistant_model": {"fa": "**دستیار ({model}):**", "en": "**Assistant ({model}):**"},
    "handoff.quoted": {"fa": "«{title}»", "en": "“{title}”"},
    "handoff.list_sep": {"fa": "، ", "en": ", "},
    "handoff.kind_summary": {"fa": "خلاصه", "en": "summary"},
    "handoff.kind_full": {"fa": "متن کامل", "en": "full text"},
    "handoff.background": {
        "fa": "## پیش‌زمینه: «{title}» ({source}، {kind})",
        "en": "## Background: “{title}” ({source}, {kind})",
    },
    "handoff.recent": {"fa": "## گفتگوی اخیر", "en": "## Recent conversation"},
    "handoff.references": {
        "fa": "(توی این بخش این مکالمه‌ها هم به‌عنوان مرجع جلوی مدل بود: {titles})",
        "en": "(In this part the model also had these conversations as reference: {titles})",
    },
    "handoff.kind_brief": {"fa": "خلاصه‌ی هندآف", "en": "handoff summary"},
    "handoff.kind_continuation": {"fa": "ادامه‌ی گفتگو", "en": "conversation continued"},
    "handoff.kind_text": {"fa": "متن", "en": "text"},
    "handoff.begin": {"fa": "--- شروع {kind} ---", "en": "--- Start: {kind} ---"},
    "handoff.end": {"fa": "--- پایان {kind} ---", "en": "--- End: {kind} ---"},
}
