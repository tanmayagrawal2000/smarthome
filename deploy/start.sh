#!/usr/bin/env bash
# Start the SmartHome server (Linux / macOS).
#
# Paths are derived from this script's location, so the repo can live
# anywhere. Override host/port with SMARTHOME_HOST / SMARTHOME_PORT env vars.
#
# Usage:   ./deploy/start.sh
#          SMARTHOME_PORT=9000 ./deploy/start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$REPO_ROOT/server"
PYTHON_BIN="$SERVER_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python venv not found at $PYTHON_BIN" >&2
    echo "Create it with: python3 -m venv \"$SERVER_DIR/.venv\" && \"$SERVER_DIR/.venv/bin/pip\" install -r \"$SERVER_DIR/requirements.txt\"" >&2
    exit 1
fi

HOST="${SMARTHOME_HOST:-0.0.0.0}"
PORT="${SMARTHOME_PORT:-8000}"

echo "Starting SmartHome on http://${HOST}:${PORT}/  (Ctrl+C to stop)"
exec "$PYTHON_BIN" -m uvicorn --app-dir "$SERVER_DIR" main:app --host "$HOST" --port "$PORT"
