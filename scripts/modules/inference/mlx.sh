#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# MLX inference engine module
# Extracted from start-mlx-server.sh
# Requires: platform.sh sourced first
# ─────────────────────────────────────────────────────────

# Find the best Python for MLX
_find_mlx_python() {
  if [ -x "/opt/miniconda3/bin/python" ]; then
    echo "/opt/miniconda3/bin/python"
  elif command -v python3 &>/dev/null; then
    echo "$(command -v python3)"
  else
    echo ""
  fi
}

# Setup macOS firewall rules for MLX server (Docker → host access)
setup_mlx_firewall() {
  local python_bin="${1:-$(_find_mlx_python)}"
  [ -z "$python_bin" ] && return 0

  local fw="/usr/libexec/ApplicationFirewall/socketfilterfw"
  if [ ! -x "$fw" ]; then
    return 0  # Not macOS or no firewall binary
  fi

  # Check if already whitelisted (avoid repeated sudo prompts)
  if ! "$fw" --listapps 2>/dev/null | grep -q "$python_bin"; then
    echo "  Adding $python_bin to macOS firewall whitelist..."
    sudo "$fw" --add "$python_bin" 2>/dev/null || true
    sudo "$fw" --unblockapp "$python_bin" 2>/dev/null || true
  fi
}

# Ensure mlx-vlm is installed
ensure_mlx_vlm() {
  local python_bin="${1:-$(_find_mlx_python)}"
  [ -z "$python_bin" ] && { echo "  ✗ No Python found for MLX"; return 1; }

  if ! "$python_bin" -c "import mlx_vlm" 2>/dev/null; then
    echo "  Installing mlx-vlm..."
    "$python_bin" -m pip install --quiet mlx-vlm
  fi
}

# Start MLX server
start_mlx_server() {
  local model="${MLX_MODEL:-mlx-community/Qwen3.5-9B-4bit}"
  local port="${MLX_PORT:-8210}"
  local host="${MLX_HOST:-0.0.0.0}"
  local python_bin
  python_bin="$(_find_mlx_python)"

  [ -z "$python_bin" ] && { echo "  ✗ No Python found for MLX"; return 1; }

  # Setup firewall if on macOS
  if [ "$PLATFORM" = "macos" ]; then
    setup_mlx_firewall "$python_bin"
  fi

  ensure_mlx_vlm "$python_bin"

  echo "  Starting MLX VLM server: host=$host port=$port"
  exec "$python_bin" -m mlx_vlm.server \
    --port "$port" \
    --host "$host"
}
