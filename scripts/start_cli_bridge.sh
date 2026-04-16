#!/usr/bin/env bash
# =============================================================================
# Mindscape CLI Bridge Worker
#
# Internal per-surface worker script used by
# `scripts/start_cli_bridge_supervisor.sh`.
#
# Starts the IDE WebSocket client on the HOST machine to bridge
# external CLI agents (Gemini CLI, Claude Code, etc.) to the
# Mindscape backend running in Docker.
#
# For normal interactive use, prefer:
#   ./scripts/start_cli_bridge_supervisor.sh --surfaces codex_cli --all
#
# Requirements:
#   - Python 3.8+ with 'websockets' package
#   - Backend running at localhost:8200
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLIENT_SCRIPT="$PROJECT_DIR/backend/app/services/external_agents/bridge/host_ws_client.py"

# Default config
BACKEND_HOST="${MINDSCAPE_WS_HOST:-localhost:8200}"
WORKSPACE_ID="${MINDSCAPE_WORKSPACE_ID:-}"
SURFACE="${MINDSCAPE_SURFACE:-}"
CLIENT_ID="${MINDSCAPE_CLIENT_ID:-}"
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

LOCK_ROOT="${MINDSCAPE_BRIDGE_LOCK_ROOT:-/tmp/mindscape-cli-bridge-locks}"
LOCK_SIGNATURE=""
LOCK_KEY=""
LOCK_DIR=""
LOCK_PID_FILE=""
LOCK_HELD=false

python_has_websockets() {
    local python_bin="$1"
    [[ -n "$python_bin" && -x "$python_bin" ]] || return 1
    "$python_bin" -c "import websockets" >/dev/null 2>&1
}

resolve_python_bin() {
    local explicit_bin="${MINDSCAPE_PYTHON_BIN:-}"
    if [[ -n "$explicit_bin" ]]; then
        echo "$explicit_bin"
        return 0
    fi

    local candidates=()
    local candidate=""
    local resolved=""

    resolved="$(command -v python3 2>/dev/null || true)"
    [[ -n "$resolved" ]] && candidates+=("$resolved")
    resolved="$(command -v python 2>/dev/null || true)"
    [[ -n "$resolved" ]] && candidates+=("$resolved")
    candidates+=("/opt/miniconda3/bin/python3" "/opt/homebrew/bin/python3" "/usr/local/bin/python3")

    for candidate in "${candidates[@]}"; do
        [[ -n "$candidate" && -x "$candidate" ]] || continue
        if python_has_websockets "$candidate"; then
            echo "$candidate"
            return 0
        fi
    done

    resolved="$(command -v python3 2>/dev/null || true)"
    if [[ -n "$resolved" ]]; then
        echo "$resolved"
        return 0
    fi

    return 1
}

describe_process_context() {
    echo "pid=$$ ppid=$PPID"
}

reap_exit_code() {
    local pid="$1"
    local exit_code=0
    if wait "$pid"; then
        exit_code=0
    else
        exit_code=$?
    fi
    echo "$exit_code"
}

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
        --client-id)
            CLIENT_ID="$2"
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
            echo "  --surface SURFACE   Agent surface type (required)"
            echo "  --client-id ID      Explicit client ID (single-workspace mode only)"
            echo "  -h, --help          Show this help"
            echo ""
            echo "Environment variables:"
            echo "  MINDSCAPE_WS_HOST        Backend host (default: localhost:8200)"
            echo "  MINDSCAPE_WORKSPACE_ID   Workspace ID"
            echo "  MINDSCAPE_SURFACE        Surface type"
            echo "  MINDSCAPE_CLIENT_ID      Explicit client ID"
            echo "  MINDSCAPE_CODEX_HOME_AUTO_DISCOVER Optional auto-discovery for logged Codex homes (default: true)"
            echo "  MINDSCAPE_CODEX_HOME_SEED_REGISTRY Optional registry file for remembered Codex host-session seeds"
            echo "  MINDSCAPE_CODEX_HOME_POOL Optional ':'-separated list of Codex session homes for host-session pool registration"
            exit 0
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$SURFACE" ]]; then
    log_error "Surface is required. Pass --surface or set MINDSCAPE_SURFACE."
    exit 1
fi

if [[ "$ALL_MODE" == "true" && -n "$CLIENT_ID" ]]; then
    log_error "--client-id is only supported in single-workspace mode."
    exit 1
fi

LOCK_SIGNATURE="${SURFACE}|${ALL_MODE}|${WORKSPACE_ID}|${BACKEND_HOST}|${CLIENT_ID}"
LOCK_KEY="$(printf '%s' "$LOCK_SIGNATURE" | tr -cs '[:alnum:]' '_')"
LOCK_DIR="${LOCK_ROOT}/${LOCK_KEY}"
LOCK_PID_FILE="${LOCK_DIR}/pid"

release_bridge_lock() {
    if [[ "$LOCK_HELD" == "true" && -f "$LOCK_PID_FILE" ]]; then
        local owner_pid
        owner_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
        if [[ "$owner_pid" == "$$" ]]; then
            rm -rf "$LOCK_DIR" 2>/dev/null || true
        fi
    fi
}

acquire_bridge_lock() {
    mkdir -p "$LOCK_ROOT"

    while true; do
        if mkdir "$LOCK_DIR" 2>/dev/null; then
            printf '%s\n' "$$" >"$LOCK_PID_FILE"
            LOCK_HELD=true
            return 0
        fi

        local owner_pid=""
        owner_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
        if [[ -n "$owner_pid" ]] && kill -0 "$owner_pid" 2>/dev/null; then
            log_warn "Bridge watcher already active for $LOCK_SIGNATURE (pid=$owner_pid); exiting duplicate watcher"
            exit 0
        fi

        rm -rf "$LOCK_DIR" 2>/dev/null || true
    done
}

trap release_bridge_lock EXIT

print_banner
acquire_bridge_lock

# --- Pre-flight checks ---

# 1. Check Python
PYTHON_BIN="$(resolve_python_bin || true)"
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
    log_error "python3 not found. Please install Python 3.8+"
    exit 1
fi

# 2. Check websockets package
if ! python_has_websockets "$PYTHON_BIN"; then
    log_error "Selected Python cannot import 'websockets': $PYTHON_BIN"
    log_error "Set MINDSCAPE_PYTHON_BIN to a Python environment that already has the dependency."
    exit 1
fi
log_info "Using Python: $PYTHON_BIN"

# 3. Check client script exists
if [[ ! -f "$CLIENT_SCRIPT" ]]; then
    log_error "Client script not found: $CLIENT_SCRIPT"
    exit 1
fi

# 4. Check backend is reachable
BACKEND_HTTP="http://$BACKEND_HOST"
OWNER_USER_ID="${MINDSCAPE_OWNER_USER_ID:-default-user}"
if ! curl -s --connect-timeout 3 "$BACKEND_HTTP/health" &>/dev/null; then
    log_warn "Backend at $BACKEND_HTTP may not be ready (health check failed)"
    log_warn "Proceeding anyway -- the client will retry with backoff"
fi

# --- Helper: fetch active workspace IDs ---
# Only connect bridge watchers to workspaces that currently have live compile,
# meeting, or pending dispatch demand for this surface.
fetch_active_workspace_ids() {
    curl -s "$BACKEND_HTTP/api/v1/workspaces/active?owner_user_id=$OWNER_USER_ID&surface=$SURFACE" 2>/dev/null \
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
    curl -s "$BACKEND_HTTP/api/v1/workspaces/active?owner_user_id=$OWNER_USER_ID&surface=$SURFACE" 2>/dev/null \
        | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, dict) and 'workspaces' in data:
        ws = data['workspaces']
        if len(ws) > 0:
            print(ws[0]['id'])
    elif isinstance(data, list) and len(data) > 0:
        print(data[0]['id'])
except:
    pass
" 2>/dev/null
}

refresh_codex_seed_registry() {
    if [[ "$SURFACE" != "codex_cli" ]]; then
        return 0
    fi
    if [[ "${MINDSCAPE_CODEX_HOME_AUTO_DISCOVER:-true}" == "false" ]]; then
        return 0
    fi
    if ! "$PYTHON_BIN" "$CLIENT_SCRIPT" \
        --surface "$SURFACE" \
        --refresh-codex-seeds >/dev/null 2>&1; then
        log_warn "Codex seed refresh failed; watcher will keep polling"
    fi
}

# 5. Resolve workspace(s)
refresh_codex_seed_registry
if [[ "$ALL_MODE" == "true" ]]; then
    log_info "Fetching active workspaces for surface: $SURFACE"
    ALL_WS_IDS=$(fetch_active_workspace_ids)
    WS_COUNT=$(echo "$ALL_WS_IDS" | grep -c . || true)
    if [[ "$WS_COUNT" -eq 0 ]]; then
        log_warn "No active workspaces found."
    fi
    log_info "Found $WS_COUNT active workspace(s)"
elif [[ -z "$WORKSPACE_ID" ]]; then
    log_info "Auto-detecting active workspace ID..."
    WORKSPACE_ID=$(fetch_first_workspace_id)
    if [[ -z "$WORKSPACE_ID" ]]; then
        log_error "Could not auto-detect an active workspace ID."
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

# --- Environment for HostBridgeTaskExecutor ---
export PYTHONPATH="$PROJECT_DIR:$PROJECT_DIR/backend:${PYTHONPATH:-}"
export MINDSCAPE_WORKSPACE_ROOT="${MINDSCAPE_WORKSPACE_ROOT:-$PROJECT_DIR}"
export MINDSCAPE_OWNER_USER_ID="$OWNER_USER_ID"
if [[ "$SURFACE" == "gemini_cli" ]]; then
    export MINDSCAPE_CLI_RUNTIME_CMD="$PYTHON_BIN $PROJECT_DIR/scripts/gemini_cli_runtime_bridge.py"
    export GEMINI_CLI_RUNTIME_CMD="${GEMINI_CLI_RUNTIME_CMD:-$MINDSCAPE_CLI_RUNTIME_CMD}"
fi

# --- Gemini auth (resolved by backend /api/v1/auth/cli-token) ---
export GEMINI_API_KEY="${GEMINI_API_KEY:-}"
export MINDSCAPE_BACKEND_API_URL="${MINDSCAPE_BACKEND_API_URL:-http://$BACKEND_HOST}"
if [[ "$SURFACE" == "codex_cli" && -n "${MINDSCAPE_CODEX_HOME_POOL:-}" ]]; then
    log_info "Codex host-session pool configured via MINDSCAPE_CODEX_HOME_POOL"
fi
if [[ "$SURFACE" == "codex_cli" && "${MINDSCAPE_CODEX_HOME_AUTO_DISCOVER:-true}" != "false" ]]; then
    log_info "Codex host-session seed discovery is enabled"
fi

# --- Start bridge ---
if [[ "$ALL_MODE" == "true" ]]; then
    log_info "Starting bridge with workspace watcher..."
    log_info "Surface:   $SURFACE"
    log_info "Runtime:   ${MINDSCAPE_CLI_RUNTIME_CMD:-${GEMINI_CLI_RUNTIME_CMD:-surface-native}}"
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
        log_info "  Spawning bridge for workspace: $ws_id ($(describe_process_context))"
        "$PYTHON_BIN" "$CLIENT_SCRIPT" \
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
        release_bridge_lock
        exit 0
    }
    trap cleanup_all INT TERM

    # Initial fetch
    ALL_WS_IDS=$(fetch_active_workspace_ids)
    WS_COUNT=$(echo "$ALL_WS_IDS" | grep -c . || true)
    if [[ "$WS_COUNT" -eq 0 ]]; then
        log_warn "No active workspaces found. Watcher will poll for new ones..."
    else
        log_info "Found $WS_COUNT active workspace(s)"
        while IFS= read -r ws_id; do
            [[ -z "$ws_id" ]] && continue
            spawn_bridge "$ws_id"
        done <<< "$ALL_WS_IDS"
    fi

    log_info "Watcher active — polling every 15s for workspace changes"

    # Watcher loop: poll for workspace changes every 15s
    while true; do
        sleep 15
        refresh_codex_seed_registry

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
                exit_code=$(reap_exit_code "${RUNNING_PIDS[$i]}")
                log_warn "Bridge PID ${RUNNING_PIDS[$i]} for ${RUNNING_WS_IDS[$i]} exited with code ${exit_code}, will respawn"
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
        CURRENT_WS_IDS=$(fetch_active_workspace_ids 2>/dev/null)
        FETCH_STATUS=$?
        if [[ "$FETCH_STATUS" -ne 0 ]]; then
            log_warn "Active workspace poll failed for surface ${SURFACE}; keeping current bridges"
            continue
        fi

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
    log_info "Runtime:   ${MINDSCAPE_CLI_RUNTIME_CMD:-${GEMINI_CLI_RUNTIME_CMD:-surface-native}}"
    echo ""
    log_info "Press Ctrl+C to stop"
    echo ""

    CLIENT_ARGS=()
    if [[ -n "$CLIENT_ID" ]]; then
        CLIENT_ARGS+=(--client-id "$CLIENT_ID")
    fi
    refresh_codex_seed_registry

    exec "$PYTHON_BIN" "$CLIENT_SCRIPT" \
        --workspace-id "$WORKSPACE_ID" \
        --host "$BACKEND_HOST" \
        --surface "$SURFACE" \
        "${CLIENT_ARGS[@]}" \
        --workspace-root "$MINDSCAPE_WORKSPACE_ROOT"
fi
