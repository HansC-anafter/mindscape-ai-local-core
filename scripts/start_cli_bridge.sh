#!/usr/bin/env bash
# =============================================================================
# Mindscape CLI Bridge
#
# Starts the IDE WebSocket client on the HOST machine to bridge
# external CLI agents (Gemini CLI, Claude Code, etc.) to the
# Mindscape backend running in Docker.
#
# Usage:
#   ./scripts/start_cli_bridge.sh                    # auto-detect workspace
#   ./scripts/start_cli_bridge.sh --all              # connect ALL workspaces
#   ./scripts/start_cli_bridge.sh --workspace-id ID  # explicit workspace
#   ./scripts/start_cli_bridge.sh --help
#
# Requirements:
#   - Python 3.8+ with 'websockets' package
#   - Backend running at localhost:8200
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLIENT_SCRIPT="$PROJECT_DIR/backend/app/services/external_agents/agents/gemini_cli/ide_ws_client.py"

# Default config
BACKEND_HOST="${MINDSCAPE_WS_HOST:-localhost:8200}"
WORKSPACE_ID="${MINDSCAPE_WORKSPACE_ID:-}"
SURFACE="${MINDSCAPE_SURFACE:-gemini_cli}"
ALL_MODE=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║     Mindscape CLI Bridge             ║"
    echo "  ╚══════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse CLI args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workspace-id)
            WORKSPACE_ID="$2"
            shift 2
            ;;
        --host)
            BACKEND_HOST="$2"
            shift 2
            ;;
        --surface)
            SURFACE="$2"
            shift 2
            ;;
        --all)
            ALL_MODE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --workspace-id ID   Workspace to connect to (auto-detected if omitted)"
            echo "  --all               Connect to ALL workspaces"
            echo "  --host HOST:PORT    Backend host (default: localhost:8200)"
            echo "  --surface SURFACE   Agent surface type (default: gemini_cli)"
            echo "  -h, --help          Show this help"
            echo ""
            echo "Environment variables:"
            echo "  MINDSCAPE_WS_HOST        Backend host (default: localhost:8200)"
            echo "  MINDSCAPE_WORKSPACE_ID   Workspace ID"
            echo "  MINDSCAPE_SURFACE        Surface type (default: gemini_cli)"
            exit 0
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

print_banner

# --- Pre-flight checks ---

# 1. Check Python
if ! command -v python3 &>/dev/null; then
    log_error "python3 not found. Please install Python 3.8+"
    exit 1
fi

# 2. Check websockets package
if ! python3 -c "import websockets" 2>/dev/null; then
    log_warn "'websockets' package not found. Installing..."
    pip3 install websockets --quiet
    log_info "websockets installed"
fi

# 3. Check client script exists
if [[ ! -f "$CLIENT_SCRIPT" ]]; then
    log_error "Client script not found: $CLIENT_SCRIPT"
    exit 1
fi

# 4. Check backend is reachable
BACKEND_HTTP="http://$BACKEND_HOST"
if ! curl -s --connect-timeout 3 "$BACKEND_HTTP/health" &>/dev/null; then
    log_warn "Backend at $BACKEND_HTTP may not be ready (health check failed)"
    log_warn "Proceeding anyway -- the client will retry with backoff"
fi

# --- Helper: fetch workspace IDs that have at least one open project ---
fetch_active_workspace_ids() {
    curl -s "$BACKEND_HTTP/api/v1/workspaces/?owner_user_id=default-user" 2>/dev/null \
        | python3 -c "
import sys, json, urllib.request

backend = '${BACKEND_HTTP}'
try:
    data = json.load(sys.stdin)
    ws_ids = []
    if isinstance(data, list):
        ws_ids = [w['id'] for w in data if w.get('id')]
    elif isinstance(data, dict) and 'workspaces' in data:
        ws_ids = [w['id'] for w in data['workspaces'] if w.get('id')]

    for wid in ws_ids:
        try:
            url = f'{backend}/api/v1/workspaces/{wid}/projects'
            resp = urllib.request.urlopen(url, timeout=3)
            pdata = json.loads(resp.read())
            projects = pdata.get('projects', pdata) if isinstance(pdata, dict) else pdata
            if isinstance(projects, list) and any(p.get('state') == 'open' for p in projects):
                print(wid)
        except Exception:
            pass
except Exception:
    pass
" 2>/dev/null
}

# Also keep a simple version for single-workspace auto-detect
fetch_first_workspace_id() {
    curl -s "$BACKEND_HTTP/api/v1/workspaces/?owner_user_id=default-user" 2>/dev/null \
        | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, list) and len(data) > 0:
        print(data[0]['id'])
    elif isinstance(data, dict) and 'workspaces' in data:
        ws = data['workspaces']
        if len(ws) > 0:
            print(ws[0]['id'])
except:
    pass
" 2>/dev/null
}

# 5. Resolve workspace(s)
if [[ "$ALL_MODE" == "true" ]]; then
    log_info "Fetching active workspaces (with open projects)..."
    ALL_WS_IDS=$(fetch_active_workspace_ids)
    WS_COUNT=$(echo "$ALL_WS_IDS" | grep -c . || true)
    if [[ "$WS_COUNT" -eq 0 ]]; then
        log_error "No active workspaces found (no workspaces with open projects)."
        exit 1
    fi
    log_info "Found $WS_COUNT active workspace(s)"
elif [[ -z "$WORKSPACE_ID" ]]; then
    log_info "Auto-detecting workspace ID..."
    WORKSPACE_ID=$(fetch_first_workspace_id)
    if [[ -z "$WORKSPACE_ID" ]]; then
        log_error "Could not auto-detect workspace ID."
        log_error "Please specify: $0 --workspace-id YOUR_WORKSPACE_ID"
        log_info "You can find your workspace ID in the web console URL or settings."
        exit 1
    fi
    log_info "Detected workspace: $WORKSPACE_ID"
fi

# --- Detect installed CLIs ---
log_info "Scanning for installed CLI agents..."
DETECTED=0
for cli in gemini claude codex openclaw aider; do
    if command -v "$cli" &>/dev/null; then
        VERSION=$("$cli" --version 2>/dev/null | head -1 || echo "unknown")
        log_info "  Found: $cli ($VERSION)"
        DETECTED=$((DETECTED + 1))
    fi
done

if [[ $DETECTED -eq 0 ]]; then
    log_warn "No CLI agents detected on this machine."
    log_warn "The bridge will still connect, but no agents will be available."
    log_warn "Install one with: npm install -g @google/gemini-cli"
fi

# --- Environment for TaskExecutor ---
export PYTHONPATH="$PROJECT_DIR:$PROJECT_DIR/backend:${PYTHONPATH:-}"
export GEMINI_CLI_RUNTIME_CMD="python3 $PROJECT_DIR/scripts/gemini_cli_runtime_bridge.py"
export MINDSCAPE_WORKSPACE_ROOT="${MINDSCAPE_WORKSPACE_ROOT:-$PROJECT_DIR}"

# --- Gemini auth (resolved by backend /api/v1/auth/cli-token) ---
export GEMINI_API_KEY="${GEMINI_API_KEY:-}"
export MINDSCAPE_BACKEND_API_URL="${MINDSCAPE_BACKEND_API_URL:-http://$BACKEND_HOST}"

# --- Start bridge ---
if [[ "$ALL_MODE" == "true" ]]; then
    log_info "Starting bridge for $WS_COUNT workspace(s)..."
    log_info "Surface:   $SURFACE"
    log_info "Runtime:   $GEMINI_CLI_RUNTIME_CMD"
    echo ""
    log_info "Press Ctrl+C to stop all bridges"
    echo ""

    PIDS=()
    while IFS= read -r ws_id; do
        [[ -z "$ws_id" ]] && continue
        log_info "  Connecting workspace: $ws_id"
        python3 "$CLIENT_SCRIPT" \
            --workspace-id "$ws_id" \
            --host "$BACKEND_HOST" \
            --surface "$SURFACE" \
            --workspace-root "$MINDSCAPE_WORKSPACE_ROOT" &
        PIDS+=($!)
    done <<< "$ALL_WS_IDS"

    # Trap Ctrl+C to kill all background processes
    trap 'log_info "Stopping all bridges..."; kill "${PIDS[@]}" 2>/dev/null; exit 0' INT TERM

    log_info "All bridges started (${#PIDS[@]} processes)"
    wait "${PIDS[@]}"
else
    log_info "Connecting to backend at ws://$BACKEND_HOST"
    log_info "Workspace: $WORKSPACE_ID"
    log_info "Surface:   $SURFACE"
    log_info "Runtime:   $GEMINI_CLI_RUNTIME_CMD"
    echo ""
    log_info "Press Ctrl+C to stop"
    echo ""

    exec python3 "$CLIENT_SCRIPT" \
        --workspace-id "$WORKSPACE_ID" \
        --host "$BACKEND_HOST" \
        --surface "$SURFACE" \
        --workspace-root "$MINDSCAPE_WORKSPACE_ROOT"
fi
