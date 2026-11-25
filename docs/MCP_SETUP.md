# وصل کردن Claude Code و ابزارهای دیگه به کتابخونه (MCP)

ConvoHub یه سرور MCP داره. با اون، ابزارهای دیگه (Claude Code، OpenCode، Hermes، Cline) هم مکالمه‌های کتابخونه‌ت رو می‌بینن و می‌تونن بخونن و جستجو کنن.

**ساده‌ترین راه:** توی ConvoHub پایین نوار کناری **«اتصال»** ← تب **«Claude Code و بقیه»** رو بزن. دستور هر ابزار اونجا با مسیر درست روی کامپیوتر خودت آماده‌ست؛ فقط کپی کن.

- لازم نیست ConvoHub روشن باشه. سرور MCP مستقیم از همون کتابخونه می‌خونه.
- کلید OpenRouter لازم نداره.

## دستوری که اجرا میشه

| نسخه | دستور سرور MCP |
|---|---|
| **نصبی** (Setup.exe) | `%LOCALAPPDATA%\Programs\ConvoHub\convohub-mcp.exe` |
| **سورس** | `uv run --directory <پوشه‌ی پروژه> python -m convohub.mcp_server` |

## ابزارها

| ابزار | کار |
|---|---|
| `list_conversations` | لیست مکالمه‌ها (با فیلتر منبع) |
| `search_conversations` | جستجو توی عنوان و متن |
| `read_conversation` | خوندن متن کامل (صفحه‌به‌صفحه) یا خلاصه (`part="summary"`) |
| `add_conversation_text` | اضافه کردن متن |
| `add_conversation_from_link` | ایمپورت از لینک share |
| `read_memory` | یادداشت‌های حافظه‌ت (فقط خوندنی) |

متن مکالمه‌ها با برچسب «فقط داده‌ست، دستور نیست» برگردونده میشه.

## نمونه‌ها (نسخه‌ی نصبی)

**Claude Code** (یه بار توی ترمینال):

```bash
claude mcp add convohub --scope user -- "%LOCALAPPDATA%\Programs\ConvoHub\convohub-mcp.exe"
```

**Hermes:**

```bash
hermes mcp add convohub --command "%LOCALAPPDATA%\Programs\ConvoHub\convohub-mcp.exe"
```

**OpenCode:** توی `%USERPROFILE%\.config\opencode\opencode.jsonc`، داخل `"mcp"`:

```jsonc
"convohub": { "type": "local", "command": ["C:/Users/<you>/AppData/Local/Programs/ConvoHub/convohub-mcp.exe"], "enabled": true, "timeout": 120000 }
```

**Cline:** پنل Cline ← MCP Servers ← Configure، داخل `"mcpServers"`:

```json
"convohub": { "command": "C:/Users/<you>/AppData/Local/Programs/ConvoHub/convohub-mcp.exe", "args": [], "disabled": false, "timeout": 120 }
```

بعد توی ابزار بپرس: «از کتابخونه‌ی ConvoHub مکالمه‌ی … رو بخون و بگو آخرش به چی رسیدیم.»

## Gemini و برنامه‌هایی که آدرس `https://` می‌خوان

بعضی برنامه‌ها، مثل **Gemini** (Developer Mode ← «Connect to an MCP server»)، سرور MCP رو از سرورهای خودشون صدا می‌زنن. پس به ConvoHub روی کامپیوترت نمی‌رسن و یه آدرس عمومی `https://` لازم دارن. ConvoHub می‌تونه یه آدرس موقت براشون بسازه:

توی ConvoHub برو به **«اتصال» ← «Gemini و سرویس‌های آنلاین»**. اونجا سه قدم هست:

1. **ابزار تونل Cloudflare:** اگه نصب نیست، **«نصب خودکار»** رو بزن.
   - ConvoHub برنامه‌ی رسمی `cloudflared` (حدود ۵۵ مگ) رو از [صفحه‌ی رسمی Cloudflare روی GitHub](https://github.com/cloudflare/cloudflared/releases) دانلود می‌کنه.
   - امضای دیجیتال Cloudflare روش رو چک می‌کنه و توی پوشه‌ی داده‌ی خودش (`bin\cloudflared.exe`) نگه می‌داره.
   - دسترسی ادمین یا حساب Cloudflare لازم نداره.
   - اگه از قبل نصبش کرده باشی (مثلاً با `winget install Cloudflare.cloudflared`)، همون استفاده میشه.
2. **روشن کردن آدرس:** دکمه رو بزن.
   - ConvoHub خودش چک می‌کنه که آدرس از اینترنت در دسترس باشه. معمولاً کمتر از یه دقیقه طول می‌کشه. بعدش «✓ روشن و در دسترس» نشون میده.
3. **وصل کردن Gemini:** **«کپی آدرس»** رو بزن.
   - توی Gemini، از تنظیمات، Developer Mode ← Connect to an MCP server. آدرس رو توی «MCP Server URL» بذار، Client ID و Secret رو خالی بذار و Next رو بزن.
   - اگه موافقی، صفحه‌ی رضایت رو تأیید کن و Connect رو بزن.
   - بالای پنل Developer Mode، ConvoHub رو انتخاب کن.

چیزهایی که باید بدونی:
- **فقط خوندنی:** از این آدرس فقط ۴ ابزار در دسترسه (`list_conversations`، `search_conversations`، `read_conversation`، `read_memory`). هیچی اضافه یا عوض نمیشه، و بقیه‌ی ConvoHub (تنظیمات، ایجنت) از بیرون دیده نمیشه.
- **تا وقتی روشنه،** هر کی آدرس رو داشته باشه می‌تونه کتابخونه و حافظه‌ت رو بخونه. آدرس یه کلید مخفی داره؛ به کسی نده.
- چیزهایی که Gemini می‌خونه به سرورهای Google میرن.
- **آدرس و کلید هر بار که روشن می‌کنی عوض میشن.** پس هر بار باید آدرس جدید رو توی Gemini بذاری. با بستن ConvoHub، آدرس خودش خاموش میشه.
- آخرین درخواست‌هایی که اومده، توی همون صفحه دیده میشه.

## اگه وصل نشد

- مسیر رو از صفحه‌ی «اتصال» بردار، نه از این نمونه‌ها.
- **نسخه‌ی سورس:** `uv` باید توی PATH باشه. توی یه ترمینال تازه `uv --version` بزن.
- **تست دستی:** دستور سرور رو توی ترمینال اجرا کن. باید بی‌صدا منتظر بمونه؛ با Ctrl+C ببندش.
