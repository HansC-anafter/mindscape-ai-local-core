#!/usr/bin/env bash
# Keeps one bridge watcher process alive per CLI surface.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BRIDGE_SCRIPT="$PROJECT_DIR/scripts/start_cli_bridge.sh"
SURFACES_CSV="${MINDSCAPE_BRIDGE_SURFACES:-gemini_cli,codex_cli,claude_code_cli}"
BRIDGE_ARGS=()
RUNNING_SURFACES=()
RUNNING_PIDS=()

log_info()  { echo "[bridge-supervisor][INFO] $1"; }
log_warn()  { echo "[bridge-supervisor][WARN] $1"; }
log_error() { echo "[bridge-supervisor][ERROR] $1" >&2; }

usage() {
    cat <<'EOF'
Usage: ./scripts/start_cli_bridge_supervisor.sh [OPTIONS]

Options:
  --surfaces CSV   Comma-separated surfaces (default: gemini_cli,codex_cli,claude_code_cli)
  --all            Connect all workspaces for each surface
  --workspace-id   Passed through to start_cli_bridge.sh
  --host           Passed through to start_cli_bridge.sh
  -h, --help       Show this help

All other arguments are passed through to scripts/start_cli_bridge.sh.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --surfaces)
            SURFACES_CSV="$2"
            shift 2
            ;;
        --surface)
            log_error "Use --surfaces with the supervisor instead of --surface."
            exit 1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            BRIDGE_ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ ! -f "$BRIDGE_SCRIPT" ]]; then
    log_error "Bridge script not found: $BRIDGE_SCRIPT"
    exit 1
fi

if [[ ${#BRIDGE_ARGS[@]} -eq 0 ]]; then
    BRIDGE_ARGS=(--all)
fi

IFS=',' read -r -a SURFACES <<< "$SURFACES_CSV"
if [[ ${#SURFACES[@]} -eq 0 ]]; then
    log_error "No surfaces configured."
    exit 1
fi

spawn_surface() {
    local surface="$1"
    log_info "Starting surface watcher: $surface"
    bash "$BRIDGE_SCRIPT" "${BRIDGE_ARGS[@]}" --surface "$surface" &
    local pid=$!
    RUNNING_SURFACES+=("$surface")
    RUNNING_PIDS+=("$pid")
    log_info "Surface watcher PID $pid for $surface"
}

cleanup_all() {
    log_info "Stopping bridge supervisor children..."
    local pid
    for pid in "${RUNNING_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait || true
    exit 0
}
trap cleanup_all INT TERM

for surface in "${SURFACES[@]}"; do
    [[ -z "$surface" ]] && continue
    spawn_surface "$surface"
done

while true; do
    sleep 10
    for i in "${!RUNNING_PIDS[@]}"; do
        if ! kill -0 "${RUNNING_PIDS[$i]}" 2>/dev/null; then
            log_warn "Surface ${RUNNING_SURFACES[$i]} watcher exited; restarting"
            surface="${RUNNING_SURFACES[$i]}"
            unset 'RUNNING_PIDS['"$i"']'
            unset 'RUNNING_SURFACES['"$i"']'
            RUNNING_PIDS=("${RUNNING_PIDS[@]}")
            RUNNING_SURFACES=("${RUNNING_SURFACES[@]}")
            spawn_surface "$surface"
            break
        fi
    done
done
