#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Platform detection module
# Source this file: source "$SCRIPT_DIR/modules/platform.sh"
# ─────────────────────────────────────────────────────────

detect_platform() {
  case "$OSTYPE" in
    darwin*)  PLATFORM="macos" ;;
    linux*)   PLATFORM="linux" ;;
    msys*|cygwin*|win32*) PLATFORM="windows" ;;
    *)        PLATFORM="unknown" ;;
  esac
  export PLATFORM
}

detect_arch() {
  ARCH="$(uname -m)"
  case "$ARCH" in
    arm64|aarch64) ARCH="arm64" ;;
    x86_64|amd64)  ARCH="x86_64" ;;
  esac
  export ARCH
}

detect_gpu() {
  GPU="none"
  if [ "$PLATFORM" = "macos" ] && [ "$ARCH" = "arm64" ]; then
    GPU="apple-silicon"
  elif command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    GPU="nvidia"
  elif command -v rocm-smi &>/dev/null; then
    GPU="amd"
  fi
  export GPU
}

can_run_mlx() {
  # MLX runs on macOS Apple Silicon or Linux with NVIDIA (mlx-vlm CUDA)
  if [ "$PLATFORM" = "macos" ] && [ "$ARCH" = "arm64" ]; then
    return 0
  elif [ "$PLATFORM" = "linux" ] && [ "$GPU" = "nvidia" ]; then
    return 0
  fi
  return 1
}

can_run_ollama() {
  # We can always run or install Ollama on supported platforms
  if [ "$PLATFORM" = "macos" ] || [ "$PLATFORM" = "linux" ]; then
    return 0
  fi
  # Fallback for other platforms: true only if already installed
  if command -v ollama &>/dev/null; then
    return 0
  fi
  return 1
}
