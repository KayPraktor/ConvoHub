#!/usr/bin/env bash
# Start ConvoHub from source on macOS or Linux. It opens in your browser at http://127.0.0.1:28765
# Stop it with the power button in the sidebar, or:  ./start.sh --stop
# Run ./install.sh once first.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Run ./install.sh first."
  exit 1
fi

exec uv run --no-dev python -m convohub "$@"
