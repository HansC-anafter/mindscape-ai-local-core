#!/usr/bin/env bash
set -euo pipefail

umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="ai.mindscape.remote-workbench-bridge"
DOMAIN="gui/$(id -u)"
PLIST_TEMPLATE="$PROJECT_ROOT/scripts/config/$LABEL.plist"
PLIST_DESTINATION="$HOME/Library/LaunchAgents/$LABEL.plist"
STATE_DIR="${REMOTE_WORKBENCH_BRIDGE_STATE_DIR:-$HOME/.mindscape/remote-workbench-bridge}"
STATUS_PATH="$STATE_DIR/status.json"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
ACTIVATION_HELPER="$PROJECT_ROOT/scripts/remote_workbench_bridge/activation.py"
LAUNCHER="$PROJECT_ROOT/scripts/start_remote_workbench_tunnel.sh"
LAUNCHCTL_BIN="/bin/launchctl"
PLUTIL_BIN="/usr/bin/plutil"
BRIDGE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

fail() {
  printf '[remote-workbench-bridge-install] ERROR: %s\n' "$*" >&2
  exit 1
}

escape_replacement() {
  printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

require_inputs() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "launchd activation is supported only on macOS"
  [[ "$PROJECT_ROOT" == /* && "$STATE_DIR" == /* && "$PYTHON_BIN" == /* ]] || fail "All activation paths must be absolute"
  [[ -x "$PYTHON_BIN" ]] || fail "Exact bridge Python is unavailable: $PYTHON_BIN"
  [[ -f "$PLIST_TEMPLATE" && ! -L "$PLIST_TEMPLATE" ]] || fail "Canonical plist template is unavailable"
  [[ -f "$ACTIVATION_HELPER" && ! -L "$ACTIVATION_HELPER" ]] || fail "Activation verifier is unavailable"
  [[ -x "$LAUNCHER" && ! -L "$LAUNCHER" ]] || fail "Canonical tunnel launcher is unavailable"
  [[ -x "$LAUNCHCTL_BIN" && -x "$PLUTIL_BIN" ]] || fail "launchd tooling is unavailable"
}

ensure_state_dir() {
  [[ ! -L "$STATE_DIR" ]] || fail "Bridge state directory must not be a symbolic link"
  mkdir -p "$STATE_DIR" "$HOME/Library/LaunchAgents" "$PROJECT_ROOT/logs"
  [[ -d "$STATE_DIR" ]] || fail "Bridge state path is not a directory"
  chmod 700 "$STATE_DIR"
}

current_build_id() {
  "$PYTHON_BIN" "$ACTIVATION_HELPER" build-id --project-root "$PROJECT_ROOT"
}

render_plist() {
  local build_id="$1"
  local temporary
  temporary="$(mktemp "$HOME/Library/LaunchAgents/.$LABEL.XXXXXX")"
  sed \
    -e "s|__PYTHON_BIN__|$(escape_replacement "$PYTHON_BIN")|g" \
    -e "s|__PROJECT_DIR__|$(escape_replacement "$PROJECT_ROOT")|g" \
    -e "s|__HOME__|$(escape_replacement "$HOME")|g" \
    -e "s|__PATH__|$BRIDGE_PATH|g" \
    -e "s|__STATE_DIR__|$(escape_replacement "$STATE_DIR")|g" \
    -e "s|__BUILD_ID__|$build_id|g" \
    "$PLIST_TEMPLATE" >"$temporary"
  "$PLUTIL_BIN" -lint "$temporary" >/dev/null || fail "Rendered plist is malformed"
  chmod 600 "$temporary"
  mv -f "$temporary" "$PLIST_DESTINATION"
  chmod 600 "$PLIST_DESTINATION"
}

verify_once() {
  local json_flag="${1:-}"
  local launchd_output
  launchd_output="$(mktemp "${TMPDIR:-/tmp}/remote-workbench-launchd.XXXXXX")"
  if ! "$LAUNCHCTL_BIN" print "$DOMAIN/$LABEL" >"$launchd_output" 2>/dev/null; then
    rm -f "$launchd_output"
    return 1
  fi
  local command=(
    "$PYTHON_BIN" "$ACTIVATION_HELPER" verify
    --project-root "$PROJECT_ROOT"
    --python-bin "$PYTHON_BIN"
    --installed-plist "$PLIST_DESTINATION"
    --launchd-output "$launchd_output"
    --status-path "$STATUS_PATH"
    --stale-seconds 60
  )
  [[ "$json_flag" == "--json" ]] && command+=(--json)
  local result=0
  "${command[@]}" || result=$?
  rm -f "$launchd_output"
  return "$result"
}

install_service() {
  ensure_state_dir
  local build_id
  build_id="$(current_build_id)" || fail "Could not compute the bridge source build ID"
  render_plist "$build_id"
  "$LAUNCHCTL_BIN" bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  local attempt
  for attempt in 1 2 3 4 5; do
    "$LAUNCHCTL_BIN" print "$DOMAIN/$LABEL" >/dev/null 2>&1 || break
    sleep 1
  done
  "$LAUNCHCTL_BIN" print "$DOMAIN/$LABEL" >/dev/null 2>&1 && fail "Previous supervisor did not unload"
  "$LAUNCHER" maintenance enter supervisor_activation || fail "Canonical launcher could not enter activation maintenance"
  local bootstrapped=false
  for attempt in 1 2 3; do
    if "$LAUNCHCTL_BIN" bootstrap "$DOMAIN" "$PLIST_DESTINATION" >/dev/null; then
      bootstrapped=true
      break
    fi
    sleep 2
  done
  [[ "$bootstrapped" == true ]] || fail "Supervisor bootstrap failed after three attempts"
  "$LAUNCHCTL_BIN" kickstart -k "$DOMAIN/$LABEL" >/dev/null || fail "Supervisor kickstart failed"
  for attempt in $(seq 1 30); do
    if verify_once >/dev/null 2>&1; then
      verify_once --json
      return
    fi
    sleep 1
  done
  fail "Current supervisor did not publish matching fresh activation state"
}

usage() {
  printf 'Usage: %s install|verify [--json]\n' "$0" >&2
}

main() {
  require_inputs
  case "${1:-}" in
    install)
      [[ $# -eq 1 ]] || fail "install accepts no additional arguments"
      install_service
      ;;
    verify)
      [[ $# -le 2 && ( $# -eq 1 || "${2:-}" == "--json" ) ]] || fail "verify accepts only --json"
      verify_once "${2:-}" || fail "Live supervisor activation is not conformant"
      ;;
    *)
      usage
      return 2
      ;;
  esac
}

main "$@"
