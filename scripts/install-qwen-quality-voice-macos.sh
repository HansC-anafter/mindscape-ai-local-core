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
REFERENCE_AUDIO="$RUNTIME_ROOT/reference/cheng-yi-jia-authoritative-ed7b564c.wav"
REFERENCE_AUDIO_SHA256="ed7b564c68cde5fea31089c602ae9ea6e5bcfb261a2eea160dd96f05bbcafc82"
REFERENCE_SOURCE_SHA256="7c1d2b380a681433a1f777b541816cde7b83c7a48340b845c4577cb571830e01"
SERVICE_ROOT="$RUNTIME_ROOT/service"
ACTIVE_SERVICE_ROOT="$SERVICE_ROOT/active"
STATE_DIR="${QWEN_QUALITY_STATE_DIR:-$HOME/.mindscape/qwen-quality-voice}"
LOG_DIR="${QWEN_QUALITY_LOG_DIR:-$HOME/.mindscape/logs/qwen-quality-voice}"
PYTHON_BIN="$RUNTIME_ROOT/venv/bin/python"
FFMPEG_BIN="${QWEN_QUALITY_FFMPEG_BIN:-/opt/homebrew/bin/ffmpeg}"

fail() {
  printf '[qwen-quality-voice-install] ERROR: %s\n' "$*" >&2
  exit 1
}

escape_replacement() {
  printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

require_inputs() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "launchd activation is supported only on macOS"
  [[ "$PROJECT_ROOT" == /* && "$RUNTIME_ROOT" == /* ]] || fail "All runtime paths must be absolute"
  [[ -x "$PYTHON_BIN" ]] || fail "Pinned Qwen Python is unavailable: $PYTHON_BIN"
  [[ -d "$RUNTIME_ROOT/model" && ! -L "$RUNTIME_ROOT/model" ]] || fail "Pinned local model is unavailable"
  [[ -f "$PLIST_TEMPLATE" && ! -L "$PLIST_TEMPLATE" ]] || fail "Canonical plist template is unavailable"
  [[ -x "$PROJECT_ROOT/scripts/run-qwen-quality-voice-service.py" ]] || fail "Runtime entrypoint is unavailable"
  [[ -f "$PROJECT_ROOT/backend/app/services/host_services/qwen_quality_voice_runtime.py" ]] || fail "Runtime module is unavailable"
  [[ -f "$PROJECT_ROOT/backend/app/services/host_services/qwen_quality_voice_output_guard.py" ]] || fail "Output guard module is unavailable"
  [[ -f "$PROJECT_ROOT/backend/app/services/host_services/qwen_quality_voice_reference_contract.py" ]] || fail "Reference contract module is unavailable"
}

materialize_reference() {
  mkdir -p "$(dirname "$REFERENCE_AUDIO")" "$STATE_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"
  if [[ -n "$REFERENCE_SOURCE" ]]; then
    [[ -f "$REFERENCE_SOURCE" && ! -L "$REFERENCE_SOURCE" ]] || fail "Authorized reference source is unavailable"
    local source_digest temporary
    source_digest="$(shasum -a 256 "$REFERENCE_SOURCE" | awk '{print $1}')"
    temporary="$(mktemp "$(dirname "$REFERENCE_AUDIO")/.authoritative.XXXXXX")"
    if [[ "$source_digest" == "$REFERENCE_AUDIO_SHA256" ]]; then
      cp "$REFERENCE_SOURCE" "$temporary"
    elif [[ "$source_digest" == "$REFERENCE_SOURCE_SHA256" ]]; then
      [[ -x "$FFMPEG_BIN" ]] || fail "Pinned ffmpeg is unavailable: $FFMPEG_BIN"
      if ! "$FFMPEG_BIN" -nostdin -hide_banner -loglevel error -y \
        -ss 2.64 -to 10.60 -i "$REFERENCE_SOURCE" \
        -ar 24000 -ac 1 -c:a pcm_s16le -f wav "$temporary"; then
        rm -f "$temporary"
        fail "Unable to materialize authoritative reference clip"
      fi
    else
      rm -f "$temporary"
      fail "Reference source digest is not authorized"
    fi
    local materialized_digest
    materialized_digest="$(shasum -a 256 "$temporary" | awk '{print $1}')"
    if [[ "$materialized_digest" != "$REFERENCE_AUDIO_SHA256" ]]; then
      rm -f "$temporary"
      fail "Materialized reference digest does not match user acceptance"
    fi
    chmod 600 "$temporary"
    mv -f "$temporary" "$REFERENCE_AUDIO"
    chmod 600 "$REFERENCE_AUDIO"
  fi
  [[ -f "$REFERENCE_AUDIO" && ! -L "$REFERENCE_AUDIO" ]] || fail "Production reference audio is unavailable"
  local digest
  digest="$(shasum -a 256 "$REFERENCE_AUDIO" | awk '{print $1}')"
  [[ "$digest" == "$REFERENCE_AUDIO_SHA256" ]] || fail "Reference audio digest does not match user acceptance"
  find "$(dirname "$REFERENCE_AUDIO")" -maxdepth 1 -type f \
    ! -name "$(basename "$REFERENCE_AUDIO")" -delete
  chmod 700 "$STATE_DIR" "$LOG_DIR"
}

materialize_service_bundle() {
  mkdir -p "$SERVICE_ROOT"
  local staging previous
  staging="$(mktemp -d "$SERVICE_ROOT/.staging.XXXXXX")"
  mkdir -p "$staging/scripts" "$staging/backend/app/services/host_services"
  cp "$PROJECT_ROOT/scripts/run-qwen-quality-voice-service.py" "$staging/scripts/"
  cp \
    "$PROJECT_ROOT/backend/app/services/host_services/qwen_quality_voice_runtime.py" \
    "$PROJECT_ROOT/backend/app/services/host_services/qwen_quality_voice_output_guard.py" \
    "$PROJECT_ROOT/backend/app/services/host_services/qwen_quality_voice_reference_contract.py" \
    "$staging/backend/app/services/host_services/"
  chmod 700 "$staging/scripts/run-qwen-quality-voice-service.py"
  previous="$SERVICE_ROOT/.previous"
  rm -rf "$previous"
  if [[ -d "$ACTIVE_SERVICE_ROOT" ]]; then
    mv "$ACTIVE_SERVICE_ROOT" "$previous"
  fi
  mv "$staging" "$ACTIVE_SERVICE_ROOT"
  rm -rf "$previous"
}

render_plist() {
  local temporary
  temporary="$(mktemp "$HOME/Library/LaunchAgents/.$LABEL.XXXXXX")"
  sed \
    -e "s|__PYTHON_BIN__|$(escape_replacement "$PYTHON_BIN")|g" \
    -e "s|__SERVICE_ROOT__|$(escape_replacement "$ACTIVE_SERVICE_ROOT")|g" \
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
  printf '%s' "$response" | grep -q "\"reference_audio_sha256\": \"$REFERENCE_AUDIO_SHA256\"" || fail "Authoritative reference is not active"
  printf '%s' "$response" | grep -q '"reference_audio_verified": true' || fail "Authoritative reference is not verified"
  /bin/launchctl print "$DOMAIN/$LABEL" | grep -Fq "$ACTIVE_SERVICE_ROOT/scripts/run-qwen-quality-voice-service.py" || fail "LaunchAgent is not using the immutable service bundle"
  printf '%s\n' "$response"
}

install_service() {
  materialize_reference
  materialize_service_bundle
  render_plist
  /bin/launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  sleep 1
  local attempt
  local bootstrapped=false
  for attempt in 1 2 3; do
    if /bin/launchctl bootstrap "$DOMAIN" "$PLIST_DESTINATION"; then
      /bin/launchctl kickstart -k "$DOMAIN/$LABEL"
      bootstrapped=true
      break
    fi
    sleep 2
  done
  [[ "$bootstrapped" == "true" ]] || fail "Qwen quality-voice LaunchAgent bootstrap failed"
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
