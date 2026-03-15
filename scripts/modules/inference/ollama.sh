#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Ollama inference engine module
# Cross-platform: macOS (brew), Linux (official installer), Windows (winget)
# ─────────────────────────────────────────────────────────

# Install Ollama if not present
install_ollama() {
  if command -v ollama &>/dev/null; then
    echo "  ✓ Ollama already installed: $(ollama --version 2>/dev/null || echo 'unknown')"
    return 0
  fi

  echo "  Installing Ollama..."
  case "$PLATFORM" in
    macos)
      if command -v brew &>/dev/null; then
        if ! brew install ollama; then
          echo "  ⚠️  Homebrew failed to install Ollama. This might be a local tap/state issue."
          echo "     Please install manually from https://ollama.com/download"
          return 1
        fi
      else
        echo "  ✗ Homebrew not found. Install from https://ollama.com/download"
        return 1
      fi
      ;;
    linux)
      curl -fsSL https://ollama.com/install.sh | sh
      ;;
    *)
      echo "  ✗ Auto-install not supported on $PLATFORM."
      echo "    Install from https://ollama.com/download"
      return 1
      ;;
  esac
}

# Check disk space before pulling models
check_disk_space() {
  local required_gb="${1:-8}"
  local available_gb

  if [ "$PLATFORM" = "macos" ] || [ "$PLATFORM" = "linux" ]; then
    available_gb=$(df -BG "${HOME}" 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}' || echo "0")
    # Fallback for macOS df output (uses 512-byte blocks)
    if [ "$available_gb" = "0" ]; then
      available_gb=$(df -g "${HOME}" 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")
    fi
  fi

  if [ "${available_gb:-0}" -lt "$required_gb" ] 2>/dev/null; then
    echo "  ⚠️  Low disk space: ${available_gb}GB available, ${required_gb}GB recommended for model downloads"
    return 1
  fi
  return 0
}

# Ensure Ollama is running
ensure_ollama_running() {
  if ! pgrep -x ollama &>/dev/null; then
    echo "  Starting Ollama serve..."
    ollama serve &>/dev/null &
    sleep 2
  fi
  echo "  ✓ Ollama is running"
}
