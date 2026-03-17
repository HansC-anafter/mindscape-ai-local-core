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

# ── Watchdog config ──
# Health check interval in seconds
WATCHDOG_INTERVAL="${MLX_WATCHDOG_INTERVAL:-60}"
# Consecutive failures before kill (60s × 10 = 10 min threshold)
# This is safely above the runner's httpx timeout of 300s (5 min),
# so a normal long inference won't be killed.
WATCHDOG_MAX_FAILURES="${MLX_WATCHDOG_MAX_FAILURES:-10}"
# Health check curl timeout (must be < WATCHDOG_INTERVAL)
WATCHDOG_CURL_TIMEOUT=5

echo "[mlx-server] Starting MLX VLM server: host=$HOST port=$PORT (model loaded on first request)"
echo "[mlx-server] Watchdog enabled: check every ${WATCHDOG_INTERVAL}s, kill after ${WATCHDOG_MAX_FAILURES} consecutive failures"

# Start MLX in background (instead of exec) so watchdog can monitor it
"$PYTHON" -m mlx_vlm.server \
  --port "$PORT" \
  --host "$HOST" &
MLX_PID=$!

# ── Liveness watchdog ──
# If MLX hangs mid-inference, it blocks the entire event loop and can't
# respond to any request (including /v1/models). This watchdog detects
# prolonged unresponsiveness and kills the process so that launchd's
# KeepAlive: true restarts it automatically.
failures=0
while kill -0 "$MLX_PID" 2>/dev/null; do
  sleep "$WATCHDOG_INTERVAL"

  if curl -sf -m "$WATCHDOG_CURL_TIMEOUT" "http://localhost:${PORT}/v1/models" > /dev/null 2>&1; then
    # Reset on any successful response
    if [ "$failures" -gt 0 ]; then
      echo "[mlx-watchdog] Health check OK, resetting failure count (was ${failures})"
    fi
    failures=0
  else
    failures=$((failures + 1))
    echo "[mlx-watchdog] Health check failed (${failures}/${WATCHDOG_MAX_FAILURES})"

    if [ "$failures" -ge "$WATCHDOG_MAX_FAILURES" ]; then
      echo "[mlx-watchdog] ${WATCHDOG_MAX_FAILURES} consecutive failures — killing MLX (PID ${MLX_PID})"
      kill "$MLX_PID" 2>/dev/null || true
      sleep 2
      # Force kill if still alive
      kill -9 "$MLX_PID" 2>/dev/null || true
      echo "[mlx-watchdog] MLX killed. Exiting so launchd KeepAlive restarts."
      exit 1
    fi
  fi
done

# MLX exited on its own — let launchd restart
wait "$MLX_PID"
EXIT_CODE=$?
echo "[mlx-server] MLX process exited with code ${EXIT_CODE}"
exit "$EXIT_CODE"
