"""PyInstaller entry point for convohub-mcp.exe (stdio MCP server for Claude Code, OpenCode, Cline, Hermes)."""
from convohub.mcp_server import mcp

if __name__ == "__main__":
    mcp.run(show_banner=False)
