"""Agent settings stored in the SQLite settings table."""

import json
from pathlib import Path

DEFAULTS = {
    "allowed_folders": [],   # absolute paths the agent may read (and, with approval, change)
    "skill_folders": [],     # folders that contain skills (<skill>/SKILL.md); read-only for the agent
    "mcp_servers": {},       # same shape as "mcpServers" in Claude Code / Cline configs
    "mcp_always_allow": [],  # "server/tool" names the user chose to "always allow" (no approval card)
}


class SettingsError(ValueError):
    pass


def load(conn) -> dict:
    out = {k: (v.copy() if isinstance(v, (list, dict)) else v) for k, v in DEFAULTS.items()}
    for row in conn.execute("SELECT key, value FROM settings"):
        if row["key"] in DEFAULTS:
            out[row["key"]] = json.loads(row["value"])
    return out


def save(conn, new: dict) -> dict:
    clean = validate(new)
    for key, value in clean.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
    return load(conn)


def _folders(values, label: str) -> list[str]:
    if not isinstance(values, list):
        raise SettingsError(f"{label} باید لیست باشه.")
    out = []
    for raw in values:
        raw = str(raw).strip().strip('"')
        if not raw:
            continue
        p = Path(raw).expanduser()
        if not p.is_absolute():
            raise SettingsError(f"مسیر باید کامل باشه (مثل D:\\Projects\\MyApp): {raw}")
        if not p.is_dir():
            raise SettingsError(f"این پوشه وجود نداره: {raw}")
        if len(p.resolve().parts) <= 1:
            raise SettingsError(f"کل یه درایو رو نمیشه داد؛ یه پوشه‌ی مشخص بده: {raw}")
        s = str(p.resolve())
        if s not in out:
            out.append(s)
    return out


def validate(new: dict) -> dict:
    clean = {}
    if "allowed_folders" in new:
        clean["allowed_folders"] = _folders(new["allowed_folders"], "پوشه‌های مجاز")
    if "skill_folders" in new:
        clean["skill_folders"] = _folders(new["skill_folders"], "پوشه‌های skill")
    if "mcp_servers" in new:
        servers = new["mcp_servers"] or {}
        if isinstance(servers, dict) and "mcpServers" in servers:
            servers = servers["mcpServers"]  # accept a pasted whole config file
        if not isinstance(servers, dict):
            raise SettingsError("تنظیمات MCP باید یه آبجکت JSON باشه.")
        for name, cfg in servers.items():
            if not isinstance(cfg, dict) or not (cfg.get("command") or cfg.get("url")):
                raise SettingsError(f"سرور MCP «{name}» باید command یا url داشته باشه.")
            if "args" in cfg and not isinstance(cfg["args"], list):
                raise SettingsError(f"args سرور «{name}» باید لیست باشه.")
        clean["mcp_servers"] = servers
    if "mcp_always_allow" in new:
        items = new["mcp_always_allow"] or []
        if not isinstance(items, list) or not all(isinstance(x, str) and "/" in x for x in items):
            raise SettingsError("لیست «همیشه اجازه بده» خرابه.")
        clean["mcp_always_allow"] = list(dict.fromkeys(items))
    return clean
