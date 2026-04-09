#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# MLX VLM Server launcher (vision-capable)
# Starts an OpenAI-compatible server with vision support for the configured model.
#
# Config knobs (environment variables):
#   MLX_MODEL   – HuggingFace model repo (default: mlx-community/Qwen3.5-9B-4bit)
#   MLX_PORT    – listen port             (default: 8210)
#   MLX_HOST    – bind address            (default: 0.0.0.0)
# ─────────────────────────────────────────────────────────
set -euo pipefail

MODEL="${MLX_MODEL:-mlx-community/Qwen3.5-9B-4bit}"
PORT="${MLX_PORT:-8210}"
HOST="${MLX_HOST:-0.0.0.0}"
PYTHON="/opt/miniconda3/bin/python"
RUN_DIR="${MLX_SERVER_RUN_DIR:-/tmp/mindscape-mlx-server-run}"

# ── macOS Firewall: allow Docker VM → host connections to MLX server ──
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
if ! "$PYTHON" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('mlx_vlm') else 1)" 2>/dev/null; then
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

# ── Watchdog config ──
# Health check interval in seconds.
# Keep this short so a wedged MLX server is recycled before IG analyze
# requests spend minutes failing against a half-dead listener.
WATCHDOG_INTERVAL="${MLX_WATCHDOG_INTERVAL:-20}"
# Consecutive failures before kill (20s × 4 ≈ 80s detection window).
WATCHDOG_MAX_FAILURES="${MLX_WATCHDOG_MAX_FAILURES:-4}"
# Health check curl timeout (must be < WATCHDOG_INTERVAL)
WATCHDOG_CURL_TIMEOUT=5
WATCHDOG_STATE_DIR="${MLX_WATCHDOG_STATE_DIR:-$(cd "$(dirname "$0")/../../logs" && pwd)/mlx-watchdog}"
WATCHDOG_STATE_FILE="${WATCHDOG_STATE_DIR}/inflight_request.json"
WATCHDOG_STATE_HELPER="$(dirname "$0")/watchdog_state.py"
WATCHDOG_SERVER_WRAPPER="$(dirname "$0")/mindscape_mlx_vlm_server.py"
WATCHDOG_INFLIGHT_HEARTBEAT_TTL="${MLX_WATCHDOG_INFLIGHT_HEARTBEAT_TTL:-45}"
# Align hard-timeout with runner-side multimodal timeouts so a single hung
# request is cut off after the current MLX server's worst-case vision latency
# instead of letting the backend client timeout first and misclassify the run
# as provider_unavailable.
WATCHDOG_INFLIGHT_HARD_TIMEOUT="${MLX_WATCHDOG_INFLIGHT_HARD_TIMEOUT:-1800}"
WATCHDOG_INFLIGHT_PREFILL_TIMEOUT="${MLX_WATCHDOG_INFLIGHT_PREFILL_TIMEOUT:-1800}"
# Local multimodal requests can sit in model_ready / generating for many
# minutes before the next observable progress event lands. Keep the active
# phase window aligned with the hard timeout so the watchdog only recycles
# truly stale requests instead of killing slow but healthy runs.
WATCHDOG_INFLIGHT_ACTIVE_PHASE_TIMEOUT="${MLX_WATCHDOG_INFLIGHT_ACTIVE_PHASE_TIMEOUT:-1500}"
# Cold starts for the local MLX vision stack can legitimately exceed 5 minutes
# while Python, mlx_vlm, and the model server warm up. Keep startup grace long
# enough that healthy cold boots are not killed before the first successful
# /v1/models response lands.
WATCHDOG_STARTUP_GRACE_SECONDS="${MLX_WATCHDOG_STARTUP_GRACE_SECONDS:-900}"

mkdir -p "$WATCHDOG_STATE_DIR"
mkdir -p "$RUN_DIR"

echo "[mlx-server] Starting MLX VLM server: host=$HOST port=$PORT (model loaded on first request)"
echo "[mlx-server] Watchdog enabled: check every ${WATCHDOG_INTERVAL}s, kill after ${WATCHDOG_MAX_FAILURES} consecutive failures"

_list_port_listener_pids() {
  lsof -nP -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

_kill_pid_tree() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  local children child
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  for child in $children; do
    _kill_pid_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

_kill_pid_tree_force() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  local children child
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  for child in $children; do
    _kill_pid_tree_force "$child"
  done
  kill -9 "$pid" 2>/dev/null || true
}

_cleanup_stale_port_listeners() {
  local pids pid remaining
  pids="$(_list_port_listener_pids)"
  [ -z "$pids" ] && return 0

  echo "[mlx-server] Clearing stale listeners on port ${PORT}: $(echo "$pids" | tr '\n' ' ')"
  for pid in $pids; do
    _kill_pid_tree "$pid"
  done
  sleep 2

  remaining="$(_list_port_listener_pids)"
  if [ -n "$remaining" ]; then
    echo "[mlx-server] Forcing stale listeners off port ${PORT}: $(echo "$remaining" | tr '\n' ' ')"
    for pid in $remaining; do
      _kill_pid_tree_force "$pid"
    done
    sleep 1
  fi
}

_terminate_mlx_server() {
  local reason="$1"
  echo "[mlx-watchdog] ${reason} — killing MLX process tree rooted at PID ${MLX_PID}"
  _kill_pid_tree "$MLX_PID"
  sleep 2
  if kill -0 "$MLX_PID" 2>/dev/null; then
    _kill_pid_tree_force "$MLX_PID"
  fi
  _cleanup_stale_port_listeners
  rm -f "$WATCHDOG_STATE_FILE" 2>/dev/null || true
}

rm -f "$WATCHDOG_STATE_FILE" 2>/dev/null || true
_cleanup_stale_port_listeners

# mlx_vlm.server currently starts under a watchfiles-based reloader.
# If its cwd is the script/log directory, every log append can trigger
# a self-reload loop. Run it from a quiet runtime directory instead.
cd "$RUN_DIR"

export MLX_WATCHDOG_STATE_DIR="$WATCHDOG_STATE_DIR"

# Start MLX in background (instead of exec) so watchdog can monitor it
"$PYTHON" "$WATCHDOG_SERVER_WRAPPER" \
  --port "$PORT" \
  --host "$HOST" &
MLX_PID=$!

# ── Liveness watchdog ──
# If MLX hangs mid-inference, it blocks the entire event loop and can't
# respond to any request (including /v1/models). This watchdog detects
# prolonged unresponsiveness and kills the process so that launchd's
# KeepAlive: true restarts it automatically.
#
# Detection: track '200 OK' lines in stdout log. Each completed inference
# produces a POST 200 OK line. If no new 200 OK lines appear across
# WATCHDOG_MAX_FAILURES consecutive checks, AND health check also fails,
# the process is truly hung.
STDOUT_LOG="$(dirname "$0")/logs/mlx-server.log"

_count_ok_lines() {
  grep -c "200 OK" "$STDOUT_LOG" 2>/dev/null || echo 0
}

_read_inflight_state() {
  if [ ! -f "$WATCHDOG_STATE_FILE" ]; then
    return 1
  fi

  "$PYTHON" "$WATCHDOG_STATE_HELPER" \
    "$WATCHDOG_STATE_FILE" \
    --heartbeat-ttl "$WATCHDOG_INFLIGHT_HEARTBEAT_TTL" \
    --hard-timeout "$WATCHDOG_INFLIGHT_HARD_TIMEOUT" \
    --active-phase-timeout "$WATCHDOG_INFLIGHT_ACTIVE_PHASE_TIMEOUT" \
    --prefill-timeout "$WATCHDOG_INFLIGHT_PREFILL_TIMEOUT"
}

failures=0
last_ok_count=$(_count_ok_lines)
watchdog_started_at=$(date +%s)
has_seen_ready=0

while kill -0 "$MLX_PID" 2>/dev/null; do
  sleep "$WATCHDOG_INTERVAL"

  if curl -sf -m "$WATCHDOG_CURL_TIMEOUT" "http://localhost:${PORT}/v1/models" > /dev/null 2>&1; then
    # Health check OK — reset
    if [ "$has_seen_ready" -eq 0 ]; then
      now_epoch=$(date +%s)
      startup_age=$((now_epoch - watchdog_started_at))
      echo "[mlx-watchdog] First health check OK after ${startup_age}s"
    fi
    has_seen_ready=1
    if [ "$failures" -gt 0 ]; then
      echo "[mlx-watchdog] Health check OK, resetting failure count (was ${failures})"
    fi
    failures=0
    last_ok_count=$(_count_ok_lines)
  else
    now_epoch=$(date +%s)
    startup_age=$((now_epoch - watchdog_started_at))
    if [ "$has_seen_ready" -eq 0 ] && [ "$startup_age" -lt "$WATCHDOG_STARTUP_GRACE_SECONDS" ]; then
      echo "[mlx-watchdog] Health check failed during startup grace (${startup_age}s/${WATCHDOG_STARTUP_GRACE_SECONDS}s) — not counting"
      continue
    fi

    # Health check failed — did MLX complete any request since last check?
    current_ok_count=$(_count_ok_lines)
    if [ "$current_ok_count" -gt "$last_ok_count" ]; then
      # New 200 OK lines appeared — MLX completed work, just busy with next request
      echo "[mlx-watchdog] Health check failed but MLX completed requests (${last_ok_count}→${current_ok_count}) — not counting"
      failures=0
      last_ok_count=$current_ok_count
    else
      inflight_info="$(_read_inflight_state 2>/dev/null || true)"
      if [ -n "$inflight_info" ]; then
        IFS=$'\t' read -r inflight_status inflight_request_id inflight_request_age inflight_heartbeat_age inflight_phase inflight_progress_age <<EOF
$inflight_info
EOF
        if [ "$inflight_status" = "heartbeat_fresh" ] || [ "$inflight_status" = "progress_fresh" ] || [ "$inflight_status" = "phase_active" ]; then
          echo "[mlx-watchdog] Health check failed but inflight request is still active status=${inflight_status} request_id=${inflight_request_id} phase=${inflight_phase} age=${inflight_request_age}s heartbeat_age=${inflight_heartbeat_age}s progress_age=${inflight_progress_age}s — not counting"
          failures=0
          continue
        fi

        if [ "$inflight_status" = "hard_timeout" ]; then
          echo "[mlx-watchdog] Inflight request exceeded hard timeout request_id=${inflight_request_id} phase=${inflight_phase} age=${inflight_request_age}s heartbeat_age=${inflight_heartbeat_age}s progress_age=${inflight_progress_age}s"
          _terminate_mlx_server "Inflight request hard-timeout"
          echo "[mlx-watchdog] MLX killed after inflight hard-timeout. Exiting so launchd KeepAlive restarts."
          exit 1
        fi
      fi

      failures=$((failures + 1))
      echo "[mlx-watchdog] Health check failed, no new completions (${failures}/${WATCHDOG_MAX_FAILURES})"

      if [ "$failures" -ge "$WATCHDOG_MAX_FAILURES" ]; then
        _terminate_mlx_server "${WATCHDOG_MAX_FAILURES} consecutive health failures"
        echo "[mlx-watchdog] MLX killed. Exiting so launchd KeepAlive restarts."
        exit 1
      fi
    fi
  fi
done

# MLX exited on its own — let launchd restart
wait "$MLX_PID"
EXIT_CODE=$?
echo "[mlx-server] MLX process exited with code ${EXIT_CODE}"
exit "$EXIT_CODE"
