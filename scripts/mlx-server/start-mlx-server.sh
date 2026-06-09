#!/usr/bin/env bash
# ---------------------------------------------------------
# MLX VLM Server launcher (vision-capable)
# Starts an OpenAI-compatible server with vision support for the configured model.
#
# Config knobs (environment variables):
#   MLX_MODEL   - HuggingFace model repo (default: mlx-community/Qwen3.5-9B-4bit)
#   MLX_PORT    - listen port             (default: 8210)
#   MLX_HOST    - bind address            (default: 0.0.0.0)
# ---------------------------------------------------------
set -euo pipefail

MODEL="${MLX_MODEL:-mlx-community/Qwen3.5-9B-4bit}"
PORT="${MLX_PORT:-8210}"
HOST="${MLX_HOST:-0.0.0.0}"
PYTHON="/opt/miniconda3/bin/python"

# -- macOS Firewall: allow Docker VM -> host connections to MLX server --
# Without this, the application firewall silently drops connections from
# Docker's host.docker.internal (192.168.65.x) to this port.
FW="/usr/libexec/ApplicationFirewall/socketfilterfw"
if [ -x "$FW" ]; then
  # Check if already whitelisted (avoid repeated sudo prompts)
  if ! "$FW" --listapps 2>/dev/null | grep -q "$PYTHON"; then
    echo "[mlx-server] Adding $PYTHON to macOS firewall whitelist..."
    sudo "$FW" --add "$PYTHON" 2>/dev/null || true
    sudo "$FW" --unblockapp "$PYTHON" 2>/dev/null || true
  fi
fi

# Ensure mlx-vlm is installed
if ! "$PYTHON" -c "import mlx_vlm" 2>/dev/null; then
  echo "[mlx-server] Installing mlx-vlm..."
  "$PYTHON" -m pip install --quiet mlx-vlm
fi

# Check if model is already cached
CACHE_DIR="${HF_HOME:-$HOME/.cache/huggingface}/hub"
MODEL_DIR="models--${MODEL//\//-}"  # Replace / with -
# Correct HuggingFace cache dir name: models--org--name
MODEL_DIR="models--${MODEL//\//-}"
# Actually HF uses -- as separator
MODEL_DIR="models--$(echo "$MODEL" | sed 's|/|--|g')"

if [ ! -d "$CACHE_DIR/$MODEL_DIR" ]; then
  echo "[mlx-server] Model $MODEL not found in cache, downloading..."
  "$PYTHON" -c "from huggingface_hub import snapshot_download; snapshot_download('$MODEL')"
fi

# -- Watchdog config --
# Health check interval in seconds
WATCHDOG_INTERVAL="${MLX_WATCHDOG_INTERVAL:-60}"
# Consecutive failures before kill (60s x 10 = 10 min threshold).
# The hard timeout is the last-resort ceiling for a heartbeating local VLM
# request; it must allow occasional long analyses to exceed 2400s.
WATCHDOG_MAX_FAILURES="${MLX_WATCHDOG_MAX_FAILURES:-10}"
# Health check curl timeout (must be < WATCHDOG_INTERVAL)
WATCHDOG_CURL_TIMEOUT=5
# The backend/runner writes this through the Docker bind mount at
# /app/data/runtime/mlx-watchdog/inflight_request.json.
WATCHDOG_STATE_FILE="${MLX_WATCHDOG_STATE_FILE:-/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/runtime/mlx-watchdog/inflight_request.json}"
WATCHDOG_INFLIGHT_HARD_TIMEOUT="${MLX_WATCHDOG_INFLIGHT_HARD_TIMEOUT:-7200}"
WATCHDOG_INFLIGHT_HEARTBEAT_TIMEOUT="${MLX_WATCHDOG_INFLIGHT_HEARTBEAT_TIMEOUT:-120}"
WATCHDOG_STATE_HELPER="$(dirname "$0")/watchdog_state.py"
WATCHDOG_IDLE_FAILURE_MODE="${MLX_WATCHDOG_IDLE_FAILURE_MODE:-ignore}"
mkdir -p "$(dirname "$WATCHDOG_STATE_FILE")" 2>/dev/null || true
rm -f "$WATCHDOG_STATE_FILE" 2>/dev/null || true

echo "[mlx-server] Starting MLX VLM server: host=$HOST port=$PORT (model loaded on first request)"
echo "[mlx-server] Watchdog enabled: check every ${WATCHDOG_INTERVAL}s, kill after ${WATCHDOG_MAX_FAILURES} consecutive failures"
echo "[mlx-server] Watchdog inflight state: ${WATCHDOG_STATE_FILE}"

# Start MLX in background (instead of exec) so watchdog can monitor it
"$PYTHON" -m mlx_vlm.server \
  --port "$PORT" \
  --host "$HOST" &
MLX_PID=$!

cleanup_mlx_child() {
  if [ -n "${MLX_PID:-}" ] && kill -0 "$MLX_PID" 2>/dev/null; then
    kill "$MLX_PID" 2>/dev/null || true
    sleep 2
    kill -9 "$MLX_PID" 2>/dev/null || true
  fi
}

trap cleanup_mlx_child EXIT INT TERM

# -- Liveness watchdog --
# If MLX hangs mid-inference, it blocks the entire event loop and can't
# respond to any request (including /v1/models). This watchdog detects
# prolonged unresponsiveness and kills the process so that launchd's
# KeepAlive: true restarts it automatically.
#
# Detection:
# 1. Count completed HTTP requests from stdout ("200 OK" lines).
# 2. Track stderr log growth while MLX is busy loading/prefilling.
# If /v1/models stops responding and neither counter advances across
# WATCHDOG_MAX_FAILURES consecutive checks, treat the process as hung.
LOG_DIR="${MLX_LOG_DIR:-$(dirname "$0")/logs}"
mkdir -p "$LOG_DIR" 2>/dev/null || true
STDOUT_LOG="${LOG_DIR}/mlx-server.log"
STDERR_LOG="${LOG_DIR}/mlx-server.error.log"

_count_ok_lines() {
  grep -c "200 OK" "$STDOUT_LOG" 2>/dev/null || echo 0
}

_file_size() {
  stat -f "%z" "$1" 2>/dev/null || echo 0
}

failures=0
last_ok_count=$(_count_ok_lines)
last_stderr_size=$(_file_size "$STDERR_LOG")

while kill -0 "$MLX_PID" 2>/dev/null; do
  sleep "$WATCHDOG_INTERVAL"

  if curl -sf -m "$WATCHDOG_CURL_TIMEOUT" "http://localhost:${PORT}/v1/models" > /dev/null 2>&1; then
    # Health check OK - reset
    if [ "$failures" -gt 0 ]; then
      echo "[mlx-watchdog] Health check OK, resetting failure count (was ${failures})"
    fi
    failures=0
    last_ok_count=$(_count_ok_lines)
    last_stderr_size=$(_file_size "$STDERR_LOG")
  else
    # Health check failed - did MLX complete any request or emit progress since last check?
    current_ok_count=$(_count_ok_lines)
    current_stderr_size=$(_file_size "$STDERR_LOG")
    inflight_active=0
    state_msg=""
    if [ -f "$WATCHDOG_STATE_HELPER" ]; then
      set +e
      state_msg="$("$PYTHON" "$WATCHDOG_STATE_HELPER" --state-file "$WATCHDOG_STATE_FILE" --hard-timeout "$WATCHDOG_INFLIGHT_HARD_TIMEOUT" --heartbeat-timeout "$WATCHDOG_INFLIGHT_HEARTBEAT_TIMEOUT" 2>&1)"
      state_status=$?
      set -e
      if [ "$state_status" -eq 0 ]; then
        inflight_active=1
      fi
    fi
    if [ "$inflight_active" -eq 1 ]; then
      # A VLM request is actively heartbeating from the runner. Qwen3.5 can block
      # /v1/models during long generation, so do not count this as a hung server.
      echo "[mlx-watchdog] Health check failed but inflight request is still active (${state_msg}) - not counting"
      failures=0
      last_ok_count=$current_ok_count
      last_stderr_size=$current_stderr_size
    elif [ "$current_ok_count" -gt "$last_ok_count" ]; then
      # New 200 OK lines appeared - MLX completed work, just busy with next request
      echo "[mlx-watchdog] Health check failed but MLX completed requests (${last_ok_count}->${current_ok_count}) - not counting"
      failures=0
      last_ok_count=$current_ok_count
      last_stderr_size=$current_stderr_size
    elif [ "$current_stderr_size" -gt "$last_stderr_size" ]; then
      # stderr grows during model load/prefill and some runtime error paths.
      # Treat recent log activity as evidence the process is still alive.
      echo "[mlx-watchdog] Health check failed but MLX emitted stderr progress (${last_stderr_size}->${current_stderr_size}) - not counting"
      failures=0
      last_stderr_size=$current_stderr_size
    elif [ "$WATCHDOG_IDLE_FAILURE_MODE" = "ignore" ]; then
      # Idle runtimes should stay resident. When there is no active request,
      # let the backend reconcile loop handle dead runtimes instead of
      # repeatedly killing and respawning the host-side worker.
      echo "[mlx-watchdog] Health check failed with no active inflight request; leaving idle runtime untouched"
      failures=0
      last_ok_count=$current_ok_count
      last_stderr_size=$current_stderr_size
    else
      failures=$((failures + 1))
      echo "[mlx-watchdog] Health check failed while idle (${failures}/${WATCHDOG_MAX_FAILURES})"

      if [ "$failures" -ge "$WATCHDOG_MAX_FAILURES" ]; then
        echo "[mlx-watchdog] ${WATCHDOG_MAX_FAILURES} idle failures - killing MLX (PID ${MLX_PID})"
        kill "$MLX_PID" 2>/dev/null || true
        sleep 2
        kill -9 "$MLX_PID" 2>/dev/null || true
        echo "[mlx-watchdog] MLX killed after idle failures. Exiting so launchd KeepAlive restarts."
        exit 1
      fi
    fi
  fi
done

# MLX exited on its own - let launchd restart
wait "$MLX_PID"
EXIT_CODE=$?
echo "[mlx-server] MLX process exited with code ${EXIT_CODE}"
exit "$EXIT_CODE"
