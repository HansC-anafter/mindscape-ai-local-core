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

# --- Helper: fetch all workspace IDs ---
# Connects bridge to every workspace. Previously filtered by open projects,
# but that excluded valid workspaces with no projects yet.
fetch_active_workspace_ids() {
    curl -s "$BACKEND_HTTP/api/v1/workspaces/?owner_user_id=default-user" 2>/dev/null \
        | python3 -c "
import sys, json

try:
    data = json.load(sys.stdin)
    ws_list = []
    if isinstance(data, list):
        ws_list = data
    elif isinstance(data, dict) and 'workspaces' in data:
        ws_list = data['workspaces']

    for w in ws_list:
        wid = w.get('id')
        if wid:
            print(wid)
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
    log_info "Fetching all workspaces..."
    ALL_WS_IDS=$(fetch_active_workspace_ids)
    WS_COUNT=$(echo "$ALL_WS_IDS" | grep -c . || true)
    if [[ "$WS_COUNT" -eq 0 ]]; then
        log_error "No workspaces found."
        exit 1
    fi
    log_info "Found $WS_COUNT workspace(s)"
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
    log_warn "No CLI agents detected. Attempting to install gemini-cli..."
    if command -v npm &>/dev/null; then
        npm install -g @google/gemini-cli 2>/dev/null \
            && { log_info "gemini-cli installed successfully"; DETECTED=1; } \
            || log_warn "Auto-install failed. Install manually: npm install -g @google/gemini-cli"
    else
        log_warn "npm not found. Install Node.js first, then: npm install -g @google/gemini-cli"
    fi
    if [[ $DETECTED -eq 0 ]]; then
        log_warn "The bridge will still connect, but no agents will be available."
    fi
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
    log_info "Starting bridge with workspace watcher..."
    log_info "Surface:   $SURFACE"
    log_info "Runtime:   $GEMINI_CLI_RUNTIME_CMD"
    echo ""
    log_info "Press Ctrl+C to stop all bridges"
    echo ""

    # Indexed arrays for macOS bash 3.2 compatibility (no associative arrays)
    RUNNING_WS_IDS=()
    RUNNING_PIDS=()

    # Helper: find index of a workspace ID in RUNNING_WS_IDS
    find_ws_index() {
        local target="$1"
        local i
        for i in "${!RUNNING_WS_IDS[@]}"; do
            if [[ "${RUNNING_WS_IDS[$i]}" == "$target" ]]; then
                echo "$i"
                return 0
            fi
        done
        echo "-1"
        return 1
    }

    # Spawn a bridge for a workspace
    spawn_bridge() {
        local ws_id="$1"
        log_info "  Spawning bridge for workspace: $ws_id"
        python3 "$CLIENT_SCRIPT" \
            --workspace-id "$ws_id" \
            --host "$BACKEND_HOST" \
            --surface "$SURFACE" \
            --workspace-root "$MINDSCAPE_WORKSPACE_ROOT" &
        local pid=$!
        RUNNING_WS_IDS+=("$ws_id")
        RUNNING_PIDS+=("$pid")
        log_info "  Bridge PID $pid started for $ws_id"
    }

    # Cleanup handler for Ctrl+C
    cleanup_all() {
        log_info "Stopping all bridges..."
        for pid in "${RUNNING_PIDS[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
        exit 0
    }
    trap cleanup_all INT TERM

    # Initial fetch
    ALL_WS_IDS=$(fetch_active_workspace_ids)
    WS_COUNT=$(echo "$ALL_WS_IDS" | grep -c . || true)
    if [[ "$WS_COUNT" -eq 0 ]]; then
        log_warn "No workspaces found. Watcher will poll for new ones..."
    else
        log_info "Found $WS_COUNT workspace(s)"
        while IFS= read -r ws_id; do
            [[ -z "$ws_id" ]] && continue
            spawn_bridge "$ws_id"
        done <<< "$ALL_WS_IDS"
    fi

    log_info "Watcher active — polling every 15s for workspace changes"

    # Watcher loop: poll for workspace changes every 15s
    while true; do
        sleep 15

        # 1. Detect dead child processes — collect indices first to avoid
        #    mutating arrays during iteration (bash mutation-during-iteration bug)
        DEAD_INDICES=()
        for i in "${!RUNNING_PIDS[@]}"; do
            if ! kill -0 "${RUNNING_PIDS[$i]}" 2>/dev/null; then
                DEAD_INDICES+=("$i")
            fi
        done

        # Process dead entries (iterate collected indices, rebuild arrays once)
        if [[ ${#DEAD_INDICES[@]} -gt 0 ]]; then
            RESPAWN_WS=()
            for i in "${DEAD_INDICES[@]}"; do
                log_warn "Bridge PID ${RUNNING_PIDS[$i]} for ${RUNNING_WS_IDS[$i]} died, will respawn"
                RESPAWN_WS+=("${RUNNING_WS_IDS[$i]}")
                unset 'RUNNING_PIDS['"$i"']'
                unset 'RUNNING_WS_IDS['"$i"']'
            done
            # Re-compact arrays once after all removals
            RUNNING_PIDS=("${RUNNING_PIDS[@]}")
            RUNNING_WS_IDS=("${RUNNING_WS_IDS[@]}")
            # Respawn all dead workspaces
            for ws_id in "${RESPAWN_WS[@]}"; do
                spawn_bridge "$ws_id"
            done
        fi

        # 2. Fetch current workspaces
        CURRENT_WS_IDS=$(fetch_active_workspace_ids 2>/dev/null || true)
        [[ -z "$CURRENT_WS_IDS" ]] && continue

        # 3. Spawn bridges for NEW workspaces
        while IFS= read -r ws_id; do
            [[ -z "$ws_id" ]] && continue
            idx=$(find_ws_index "$ws_id" 2>/dev/null || echo "-1")
            if [[ "$idx" == "-1" ]]; then
                log_info "New workspace discovered: $ws_id"
                spawn_bridge "$ws_id"
            fi
        done <<< "$CURRENT_WS_IDS"

        # 4. Kill bridges for REMOVED workspaces — collect first, then remove
        REMOVE_INDICES=()
        for i in "${!RUNNING_WS_IDS[@]}"; do
            local_ws="${RUNNING_WS_IDS[$i]}"
            if ! echo "$CURRENT_WS_IDS" | grep -q "^${local_ws}$"; then
                REMOVE_INDICES+=("$i")
            fi
        done
        if [[ ${#REMOVE_INDICES[@]} -gt 0 ]]; then
            for i in "${REMOVE_INDICES[@]}"; do
                log_info "Workspace removed: ${RUNNING_WS_IDS[$i]}, stopping bridge PID ${RUNNING_PIDS[$i]}"
                kill "${RUNNING_PIDS[$i]}" 2>/dev/null || true
                unset 'RUNNING_PIDS['"$i"']'
                unset 'RUNNING_WS_IDS['"$i"']'
            done
            # Re-compact arrays after removals
            RUNNING_PIDS=("${RUNNING_PIDS[@]}")
            RUNNING_WS_IDS=("${RUNNING_WS_IDS[@]}")
        fi
    done
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
