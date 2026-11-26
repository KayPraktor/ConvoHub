# ConvoHub design notes

فارسی: [docs/fa/DESIGN.md](fa/DESIGN.md)

A summary of the main decisions, for anyone who wants to understand or change the code.

## Principles

- **Personal and local:**
  - One user, one computer.
  - No user accounts, no cloud deployment, no telemetry.
  - The server listens only on `127.0.0.1`.
- **No login to AI services:**
  - We never log in to Gemini, ChatGPT, Claude or Grok with the user's account. We don't keep their cookies or tokens and we don't call their private endpoints.
  - Conversations come in only through these routes: paste, an official export file, a public share link, and an extension that reads only the DOM of the page the user has open.
- **Imported text is data, not instructions:**
  - It is given to the model inside a `<transcript>` tag with an explicit warning.
  - Tool output also comes back with a "data, not instructions" label.
- **Nothing on the system changes without the user's approval:**
  - Writing, editing, deleting (to the Recycle Bin), running commands and MCP tools show an approval card every time.
  - Reading is allowed only inside the permitted folders, and secret files are never read.

## Components

| File or folder | What it does |
|---|---|
| `convohub/main.py` | The FastAPI app. Host checks (against DNS rebinding) and Origin checks, so other sites can't use the user's browser to send ConvoHub requests that change anything |
| `convohub/api.py` | All the `/api` endpoints |
| `convohub/library.py`, `db.py` | The library on SQLite, and search with FTS5 trigram over text whose Persian and Arabic spelling has been normalized |
| `convohub/prompting.py` | Builds the messages for the model. References go in the system message so they hit the prompt cache |
| `convohub/openrouter.py` | Model list and streaming (OpenAI-compatible, with function calling) |
| `convohub/agent/` | Agent mode: folder limits (`fs.py`), the loop and permissions (`runner.py`), the user's MCP servers and skills |
| `convohub/panel.py` | Multi-model: parallel answers, and an optional summary by an orchestrator model |
| `convohub/importers/` | Paste, file, share link (Playwright with the system's own Chrome or Edge), and merging the messages the extension sends |
| `convohub/mcp_server.py` | MCP server over the library, for other tools (FastMCP, stdio) |
| `convohub/keystore.py` | The OpenRouter key, encrypted with DPAPI, kept apart from the database (so it never goes into backups) |
| `convohub/backup.py` | Backups with SQLite's own backup API. Automatic once a day; the last 14 are kept |
| `convohub/static/` | The interface: plain HTML, CSS and JS, no build step |
| `extension/` | The Chrome and Edge extension (Manifest V3) |
| `packaging/` | PyInstaller and Inno Setup for ConvoHub-Setup.exe |

## Data

- **Where it's stored:**
  - Installed version: `%LOCALAPPDATA%\ConvoHub`.
  - Source version: `<project>/data`.
  - `CONVOHUB_DATA_DIR` changes the location for both.
- **OpenRouter key:** an environment variable or `.env` takes priority; after that, the key saved in the interface.
- **Extension:** only an extension whose ID has been approved can use `/api/extension/`. The first time, the user clicks **Accept** in the interface.

## Some specific decisions

- **Plain chat mode** has only the reading tools. Agent mode adds the tools that change things, and MCP. A tool that wasn't given to the model in a mode isn't run, even if the model names it.
- **Paths are shown to the model with `/`,** because models break backslashes when they write JSON.
- **The extension's automatic sync** only adds messages and never replaces any. A full send happens only when the user clicks.
- **System dialogs** (`alert`, `confirm`, `prompt`) are drawn inside the page itself, because some browsers block them silently.
