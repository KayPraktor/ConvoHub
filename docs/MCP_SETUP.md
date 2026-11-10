# وصل کردن Claude Code و ابزارهای دیگه به کتابخونه (MCP)

ConvoHub یه سرور MCP داره. با اون، ابزارهای دیگه (Claude Code، OpenCode، Hermes، Cline) هم مکالمه‌های کتابخونه‌ت رو می‌بینن و می‌تونن بخونن و جستجو کنن.

**ساده‌ترین راه:** توی ConvoHub پایین نوار کناری **«🔌 اتصال»** ← تب **«Claude Code و بقیه»** رو بزن. دستور هر ابزار اونجا با مسیر درست روی کامپیوتر خودت آماده‌ست؛ فقط کپی کن.

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

## اگه وصل نشد

- مسیر رو از صفحه‌ی «🔌 اتصال» بردار، نه از این نمونه‌ها.
- **نسخه‌ی سورس:** `uv` باید توی PATH باشه. توی یه ترمینال تازه `uv --version` بزن.
- **تست دستی:** دستور سرور رو توی ترمینال اجرا کن. باید بی‌صدا منتظر بمونه؛ با Ctrl+C ببندش.
