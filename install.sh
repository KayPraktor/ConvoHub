#!/usr/bin/env bash
# ConvoHub - install from source on macOS or Linux (needs uv: https://docs.astral.sh/uv/).
# Run once after downloading/cloning:  ./install.sh   (or: bash install.sh)
# It installs Python and the packages into .venv in this folder. Nothing outside this folder changes.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo
  echo "[!] uv is not installed."
  echo "    Install it with this command in Terminal, then open a new Terminal window and run ./install.sh again:"
  echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo
  exit 1
fi

echo "Installing Python and packages (first time can take a few minutes)..."
if ! uv sync --no-dev; then
  echo "[!] Installing packages failed. See the messages above."
  exit 1
fi

echo
echo "Done. Start ConvoHub with:  ./start.sh"
echo "It opens in your browser at http://127.0.0.1:28765 and asks for your OpenRouter key on first start."
