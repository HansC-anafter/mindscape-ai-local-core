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

# ---- Configuration ----
export MINDSCAPE_WS_HOST="${MINDSCAPE_WS_HOST:-localhost:8000}"
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
echo "======================================"
echo ""

exec python3 -m backend.app.services.external_agents.agents.antigravity.ide_ws_client \
  --mode single \
  --workspace-id "$MINDSCAPE_WORKSPACE_ID" \
  --host "$MINDSCAPE_WS_HOST" \
  --workspace-root "$MINDSCAPE_WORKSPACE_ROOT"
