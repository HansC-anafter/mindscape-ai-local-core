#!/usr/bin/env bash
# =========================================================
# start_ws_bridge.sh — Mac-side WS bridge for Antigravity
#
# Starts ide_ws_client.py as a persistent daemon on Mac.
# The client connects to backend WebSocket, receives task
# dispatches, and routes them to Antigravity for execution.
#
# Usage:
#   ./scripts/start_ws_bridge.sh
#   MINDSCAPE_WORKSPACE_ID=xxx ./scripts/start_ws_bridge.sh
# =========================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---- Virtual environment ----
VENV_DIR="${PROJECT_ROOT}/.venv-ws-bridge"
if [ ! -d "$VENV_DIR" ]; then
    echo "[setup] Creating virtual environment at ${VENV_DIR}..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# Install required packages if needed
if ! python3 -c "import websockets" 2>/dev/null; then
    echo "[setup] Installing required packages..."
    pip install --quiet websockets sqlalchemy psycopg2-binary
fi

# ---- Configuration ----
export MINDSCAPE_WS_HOST="${MINDSCAPE_WS_HOST:-localhost:8200}"
export MINDSCAPE_WORKSPACE_ID="${MINDSCAPE_WORKSPACE_ID:-bac7ce63-e768-454d-96f3-3a00e8e1df69}"
export MINDSCAPE_WORKSPACE_ROOT="${MINDSCAPE_WORKSPACE_ROOT:-/Users/shock/Projects_local/workspace}"

# IDE runtime bridge for NL tasks
export ANTIGRAVITY_IDE_RUNTIME_CMD="python3 ${PROJECT_ROOT}/scripts/antigravity_runtime_bridge.py"

# Ensure Python path covers backend modules
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/backend:${PYTHONPATH:-}"

# ---- Database connection (needed by TaskExecutor for MCP tools) ----
export DATABASE_URL_CORE="${DATABASE_URL_CORE:-postgresql://mindscape:mindscape_password@localhost:5432/mindscape_core}"
export POSTGRES_CORE_HOST="${POSTGRES_CORE_HOST:-localhost}"
export POSTGRES_CORE_PORT="${POSTGRES_CORE_PORT:-5432}"
export POSTGRES_CORE_DB="${POSTGRES_CORE_DB:-mindscape_core}"
export POSTGRES_CORE_USER="${POSTGRES_CORE_USER:-mindscape}"
export POSTGRES_CORE_PASSWORD="${POSTGRES_CORE_PASSWORD:-mindscape_password}"

echo "======================================"
echo " Antigravity WS Bridge"
echo "======================================"
echo " Workspace:  $MINDSCAPE_WORKSPACE_ID"
echo " Backend:    ws://$MINDSCAPE_WS_HOST"
echo " Root:       $MINDSCAPE_WORKSPACE_ROOT"
echo " Runtime:    $ANTIGRAVITY_IDE_RUNTIME_CMD"
echo " Venv:       $VENV_DIR"
echo "======================================"
echo ""

exec python3 -m backend.app.services.external_agents.agents.antigravity.ide_ws_client \
  --workspace-id "$MINDSCAPE_WORKSPACE_ID" \
  --host "$MINDSCAPE_WS_HOST"
