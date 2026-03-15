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

echo "[mlx-server] Starting MLX VLM server: host=$HOST port=$PORT (model loaded on first request)"
exec "$PYTHON" -m mlx_vlm.server \
  --port "$PORT" \
  --host "$HOST"
