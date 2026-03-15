#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Inference engine detection and auto-selection
# Requires: platform.sh sourced first
# ─────────────────────────────────────────────────────────

select_inference_engine() {
  local modules_dir
  modules_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  if can_run_mlx; then
    echo "  → MLX detected ($GPU on $PLATFORM/$ARCH)"
    source "$modules_dir/mlx.sh"
    start_mlx_server > /dev/null 2>&1 &
    INFERENCE_ENGINE="mlx"
  elif can_run_ollama; then
    echo "  → Ollama detected"
    source "$modules_dir/ollama.sh"
    if install_ollama; then
      check_disk_space
      ensure_ollama_running
      INFERENCE_ENGINE="ollama"
    else
      echo "  ⚠️  Ollama installation failed or is unavailable."
      INFERENCE_ENGINE="none"
    fi
  else
    echo "  ⚠️  No local inference engine found."
    echo "    Install Ollama: https://ollama.com/download"
    INFERENCE_ENGINE="none"
  fi
  export INFERENCE_ENGINE
}
