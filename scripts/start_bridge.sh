#!/usr/bin/env bash
# ============================================================
# start_bridge.sh — Host-side Gemini CLI Bridge
#
# Runs ide_ws_client.py on the Host so it can call
# `gemini` CLI for NL task execution.
#
# Prerequisites:
#   - Gemini CLI is installed on this machine
#   - Backend is reachable at localhost:8200
#   - Python 3.11+ with websockets installed
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ADAPTER_PATH="$REPO_ROOT/backend/app/services/external_agents/agents/gemini_cli/gemini_cli_chat_adapter.py"
VENV_DIR="$REPO_ROOT/.venv-bridge"
PYTHON="$VENV_DIR/bin/python3"

# ---- Ensure venv exists ----
if [ ! -f "$PYTHON" ]; then
    echo "[setup] Creating venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet websockets
    echo "[setup] venv ready."
fi

# ---- Configuration ----
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/backend:$REPO_ROOT/backend/app"
export GEMINI_CLI_RUNTIME_CMD="$PYTHON $ADAPTER_PATH"
export MINDSCAPE_WS_HOST="${MINDSCAPE_WS_HOST:-localhost:8200}"
export MINDSCAPE_BACKEND_API_URL="${MINDSCAPE_BACKEND_API_URL:-http://localhost:8200}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# --- Gemini auth (resolved by backend /api/v1/auth/cli-token) ---
# GEMINI_API_KEY can also be set here as env-level override.
export GEMINI_API_KEY="${GEMINI_API_KEY:-}"

# ---- Preflight checks ----
echo "[preflight] Checking Gemini CLI..."
GEMINI_CLI="${GEMINI_CLI_PATH:-gemini}"
if ! command -v "$GEMINI_CLI" > /dev/null 2>&1; then
    echo "[ERROR] Gemini CLI not found: $GEMINI_CLI"
    exit 1
fi
echo "[preflight] Gemini CLI: $(command -v "$GEMINI_CLI")"

echo "[preflight] Checking backend connectivity..."
if ! curl -sf "http://${MINDSCAPE_WS_HOST}/health" > /dev/null 2>&1; then
    echo "[WARNING] Backend health check failed at http://${MINDSCAPE_WS_HOST}/health"
    echo "          Bridge will retry connection on startup."
fi

echo "[preflight] Checking adapter script..."
if [ ! -f "$ADAPTER_PATH" ]; then
    echo "[ERROR] Adapter not found at $ADAPTER_PATH"
    exit 1
fi
echo "[preflight] Adapter: $ADAPTER_PATH"

echo ""
echo "============================================================"
echo " Starting Gemini CLI Bridge (Host-side)"
echo " WS Host:  $MINDSCAPE_WS_HOST"
echo " API URL:  $MINDSCAPE_BACKEND_API_URL"
echo " Runtime:  $GEMINI_CLI_RUNTIME_CMD"
echo " Python:   $PYTHON"
echo "============================================================"
echo ""

# ---- Launch bridge ----
exec "$PYTHON" -m backend.app.services.external_agents.agents.gemini_cli.ide_ws_client \
    --mode auto \
    --host "$MINDSCAPE_WS_HOST" \
    --backend-api-url "$MINDSCAPE_BACKEND_API_URL" \
    --client-id "gemini-cli-bridge-host" \
    --surface "gemini_cli" \
    --workspace-root "$REPO_ROOT"
