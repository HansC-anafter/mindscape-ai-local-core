#!/usr/bin/env bash
# Start one Host Runtime Session bridge for a single workspace.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

HOST="${MINDSCAPE_WS_HOST:-127.0.0.1:8220}"
WORKSPACE_ID="${MINDSCAPE_WORKSPACE_ID:-}"
RUNTIME_SURFACE="${HOST_RUNTIME_SURFACE:-codex_cli}"
RUNTIME_ID="${HOST_RUNTIME_ID:-codex_cli}"
BRIDGE_ID="${HOST_RUNTIME_BRIDGE_ID:-}"
WORKSPACE_ROOT="${MINDSCAPE_WORKSPACE_ROOT:-$PROJECT_DIR}"
MAX_DURATION="${HOST_RUNTIME_MAX_DURATION:-600}"
PYTHON_BIN="${MINDSCAPE_PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python}"

usage() {
    cat <<'EOF'
Usage: scripts/start_host_runtime_bridge.sh --workspace-id WORKSPACE_ID [options]

Options:
  --workspace-id ID       Workspace served by this host-runtime bridge.
  --host HOST:PORT        Backend/control host for host-runtime WS (default: 127.0.0.1:8220).
  --runtime-surface NAME  Runtime surface (default: codex_cli).
  --runtime-id ID         Runtime id (default: codex_cli).
  --bridge-id ID          Stable bridge id.
  --workspace-root PATH   Host workspace root for CLI execution.
  --max-duration SECONDS  Per-turn max duration.
  -h, --help              Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --workspace-id)
            WORKSPACE_ID="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --runtime-surface)
            RUNTIME_SURFACE="$2"
            shift 2
            ;;
        --runtime-id)
            RUNTIME_ID="$2"
            shift 2
            ;;
        --bridge-id)
            BRIDGE_ID="$2"
            shift 2
            ;;
        --workspace-root)
            WORKSPACE_ROOT="$2"
            shift 2
            ;;
        --max-duration)
            MAX_DURATION="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$WORKSPACE_ID" ]]; then
    echo "Missing --workspace-id or MINDSCAPE_WORKSPACE_ID." >&2
    exit 2
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python runtime not found or not executable: $PYTHON_BIN" >&2
    exit 1
fi

if ! "$PYTHON_BIN" -c "import websockets" >/dev/null 2>&1; then
    echo "Python runtime lacks websockets: $PYTHON_BIN" >&2
    exit 1
fi

if [[ -z "${MINDSCAPE_BACKEND_API_URL:-}" ]]; then
    if [[ "$HOST" == http://* || "$HOST" == https://* ]]; then
        export MINDSCAPE_BACKEND_API_URL="$HOST"
    else
        export MINDSCAPE_BACKEND_API_URL="http://$HOST"
    fi
fi
export MINDSCAPE_WS_HOST="$HOST"
export MINDSCAPE_WORKSPACE_ROOT="$WORKSPACE_ROOT"
export CODEX_CLI_PATH="${CODEX_CLI_PATH:-/Applications/Codex.app/Contents/Resources/codex}"

exec "$PYTHON_BIN" -m backend.app.services.host_runtime_sessions.bridge_client \
    --workspace-id "$WORKSPACE_ID" \
    --host "$HOST" \
    --runtime-surface "$RUNTIME_SURFACE" \
    --runtime-id "$RUNTIME_ID" \
    --bridge-id "$BRIDGE_ID" \
    --workspace-root "$WORKSPACE_ROOT" \
    --max-duration "$MAX_DURATION"
