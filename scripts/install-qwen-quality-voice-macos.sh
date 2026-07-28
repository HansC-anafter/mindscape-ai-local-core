#!/usr/bin/env bash
set -euo pipefail

umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="ai.mindscape.qwen-quality-voice"
DOMAIN="gui/$(id -u)"
PLIST_TEMPLATE="$PROJECT_ROOT/scripts/config/$LABEL.plist"
PLIST_DESTINATION="$HOME/Library/LaunchAgents/$LABEL.plist"
RUNTIME_ROOT="${QWEN_QUALITY_RUNTIME_ROOT:?QWEN_QUALITY_RUNTIME_ROOT is required}"
REFERENCE_SOURCE="${QWEN_QUALITY_REFERENCE_SOURCE:-}"
REFERENCE_AUDIO="${QWEN_QUALITY_REFERENCE_AUDIO:-$RUNTIME_ROOT/reference/cheng-yi-jia-selected.wav}"
STATE_DIR="${QWEN_QUALITY_STATE_DIR:-$HOME/.mindscape/qwen-quality-voice}"
LOG_DIR="${QWEN_QUALITY_LOG_DIR:-$HOME/.mindscape/logs/qwen-quality-voice}"
PYTHON_BIN="$RUNTIME_ROOT/venv/bin/python"

fail() {
  printf '[qwen-quality-voice-install] ERROR: %s\n' "$*" >&2
  exit 1
}

escape_replacement() {
  printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

require_inputs() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "launchd activation is supported only on macOS"
  [[ "$PROJECT_ROOT" == /* && "$RUNTIME_ROOT" == /* && "$REFERENCE_AUDIO" == /* ]] || fail "All runtime paths must be absolute"
  [[ -x "$PYTHON_BIN" ]] || fail "Pinned Qwen Python is unavailable: $PYTHON_BIN"
  [[ -d "$RUNTIME_ROOT/model" && ! -L "$RUNTIME_ROOT/model" ]] || fail "Pinned local model is unavailable"
  [[ -f "$PLIST_TEMPLATE" && ! -L "$PLIST_TEMPLATE" ]] || fail "Canonical plist template is unavailable"
  [[ -x "$PROJECT_ROOT/scripts/run-qwen-quality-voice-service.py" ]] || fail "Runtime entrypoint is unavailable"
}

materialize_reference() {
  mkdir -p "$(dirname "$REFERENCE_AUDIO")" "$STATE_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"
  if [[ -n "$REFERENCE_SOURCE" ]]; then
    [[ -f "$REFERENCE_SOURCE" && ! -L "$REFERENCE_SOURCE" ]] || fail "Authorized reference source is unavailable"
    cp "$REFERENCE_SOURCE" "$REFERENCE_AUDIO"
    chmod 600 "$REFERENCE_AUDIO"
  fi
  [[ -f "$REFERENCE_AUDIO" && ! -L "$REFERENCE_AUDIO" ]] || fail "Production reference audio is unavailable"
  local digest
  digest="$(shasum -a 256 "$REFERENCE_AUDIO" | awk '{print $1}')"
  [[ "$digest" == "36e745aa605ce820ad618e2dab36c47ef574db40d18e127b0d7c098934af1434" ]] || fail "Reference audio digest does not match the qualified selection"
  chmod 700 "$STATE_DIR" "$LOG_DIR"
}

render_plist() {
  local temporary
  temporary="$(mktemp "$HOME/Library/LaunchAgents/.$LABEL.XXXXXX")"
  sed \
    -e "s|__PYTHON_BIN__|$(escape_replacement "$PYTHON_BIN")|g" \
    -e "s|__PROJECT_ROOT__|$(escape_replacement "$PROJECT_ROOT")|g" \
    -e "s|__RUNTIME_ROOT__|$(escape_replacement "$RUNTIME_ROOT")|g" \
    -e "s|__REFERENCE_AUDIO__|$(escape_replacement "$REFERENCE_AUDIO")|g" \
    -e "s|__STATE_DIR__|$(escape_replacement "$STATE_DIR")|g" \
    -e "s|__LOG_DIR__|$(escape_replacement "$LOG_DIR")|g" \
    "$PLIST_TEMPLATE" > "$temporary"
  /usr/bin/plutil -lint "$temporary" >/dev/null || fail "Rendered plist is malformed"
  chmod 600 "$temporary"
  mv -f "$temporary" "$PLIST_DESTINATION"
}

verify_service() {
  /bin/launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 || fail "LaunchAgent is not active"
  local response
  response="$(curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8184/health)" || fail "Health endpoint is unavailable"
  printf '%s' "$response" | grep -q '"status": "ok"' || fail "Health response is not ready"
  printf '%s' "$response" | grep -q '"voice_display_name": "乘以加"' || fail "Selected voice is not active"
  printf '%s\n' "$response"
}

install_service() {
  materialize_reference
  render_plist
  /bin/launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  /bin/launchctl bootstrap "$DOMAIN" "$PLIST_DESTINATION"
  /bin/launchctl kickstart -k "$DOMAIN/$LABEL"
  local attempt
  for attempt in $(seq 1 30); do
    if curl --fail --silent --max-time 2 http://127.0.0.1:8184/health >/dev/null 2>&1; then
      verify_service
      return
    fi
    sleep 1
  done
  fail "Qwen quality-voice service did not become ready"
}

case "${1:-}" in
  install)
    require_inputs
    install_service
    ;;
  verify)
    require_inputs
    verify_service
    ;;
  *)
    printf 'Usage: QWEN_QUALITY_RUNTIME_ROOT=/absolute/path %s install|verify\n' "$0" >&2
    exit 2
    ;;
esac
