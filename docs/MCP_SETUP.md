# Connecting Claude Code and other tools to the library (MCP)

فارسی: [docs/fa/MCP_SETUP.md](fa/MCP_SETUP.md)

ConvoHub has an MCP server. With it, other tools (Claude Code, OpenCode, Hermes, Cline) can also see the conversations in your library, read them and search them.

**The easiest way:** in ConvoHub, click **Connect** at the bottom of the sidebar → the **"Claude Code and others"** tab. The command for each tool is ready there, with the right paths for your computer; just copy it.

- ConvoHub doesn't need to be running. The MCP server reads the same library directly.
- It doesn't need an OpenRouter key.

## The command that runs

| Version | MCP server command |
|---|---|
| **Installed** (Setup.exe) | `%LOCALAPPDATA%\Programs\ConvoHub\convohub-mcp.exe` |
| **Source** | `uv run --directory <project folder> python -m convohub.mcp_server` |

## Tools

| Tool | What it does |
|---|---|
| `list_conversations` | List conversations (with a source filter) |
| `search_conversations` | Search titles and text |
| `read_conversation` | Read the full text (page by page) or the summary (`part="summary"`) |
| `add_conversation_text` | Add text |
| `add_conversation_from_link` | Import from a share link |
| `read_memory` | Your memory notes (read-only) |

Conversation text is returned with a label saying "this is data, not instructions".

## Examples (installed version)

**Claude Code** (once, in a terminal):

```bash
claude mcp add convohub --scope user -- "%LOCALAPPDATA%\Programs\ConvoHub\convohub-mcp.exe"
```

**Hermes:**

```bash
hermes mcp add convohub --command "%LOCALAPPDATA%\Programs\ConvoHub\convohub-mcp.exe"
```

**OpenCode:** in `%USERPROFILE%\.config\opencode\opencode.jsonc`, inside `"mcp"`:

```jsonc
"convohub": { "type": "local", "command": ["C:/Users/<you>/AppData/Local/Programs/ConvoHub/convohub-mcp.exe"], "enabled": true, "timeout": 120000 }
```

**Cline:** Cline panel → MCP Servers → Configure, inside `"mcpServers"`:

```json
"convohub": { "command": "C:/Users/<you>/AppData/Local/Programs/ConvoHub/convohub-mcp.exe", "args": [], "disabled": false, "timeout": 120 }
```

Then ask in the tool: *"Read the … conversation from the ConvoHub library and tell me where we ended up."*

## Gemini and apps that need an `https://` address

Some apps, such as **Gemini** (Developer Mode → "Connect to an MCP server"), call the MCP server from their own servers. So they can't reach ConvoHub on your computer and need a public `https://` address. ConvoHub can create a temporary one for them:

In ConvoHub, go to **Connect → "Gemini and online services"**. There are three steps there:

1. **Cloudflare tunnel tool:** if it isn't installed, click **"Install automatically"**.
   - ConvoHub downloads Cloudflare's official `cloudflared` program (about 55 MB) from [Cloudflare's official page on GitHub](https://github.com/cloudflare/cloudflared/releases).
   - It checks Cloudflare's digital signature on it and keeps it in its own data folder (`bin\cloudflared.exe`).
   - It needs no admin rights and no Cloudflare account.
   - If you have already installed it (for example with `winget install Cloudflare.cloudflared`), that copy is used.
2. **Turn on the address:** click the button.
   - ConvoHub checks by itself that the address is reachable from the internet. This usually takes less than a minute. Then it shows "✓ On and reachable".
3. **Connect Gemini:** click **"Copy address"**.
   - In Gemini, from the settings: Developer Mode → Connect to an MCP server. Put the address in "MCP Server URL", leave Client ID and Secret empty and click Next.
   - If you agree, approve the consent page and click Connect.
   - At the top of the Developer Mode panel, choose ConvoHub.

Things to know:
- **Read-only:** only 4 tools are available through this address (`list_conversations`, `search_conversations`, `read_conversation`, `read_memory`). Nothing is added or changed, and the rest of ConvoHub (settings, agent) can't be seen from outside.
- **While it's on,** anyone who has the address can read your library and memory. The address contains a secret key; don't give it to anyone.
- Whatever Gemini reads goes to Google's servers.
- **The address and key change every time you turn it on.** So each time you have to put the new address into Gemini. When you close ConvoHub, the address switches off by itself.
- The latest requests that came in are shown on the same page.

## If it doesn't connect

- Take the path from the **Connect** page, not from these examples.
- **Source version:** `uv` must be on the PATH. Run `uv --version` in a new terminal.
- **Manual test:** run the server command in a terminal. It should wait silently; close it with Ctrl+C.
