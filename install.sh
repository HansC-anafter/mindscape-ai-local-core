#!/bin/bash
#
# Mindscape AI Local Core - One-Line Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/HansC-anafter/mindscape-ai-local-core/master/install.sh | bash
#
# Or with custom directory name:
#   curl -fsSL https://... | bash -s -- --dir my-mindscape
#

set -e

# Default settings
REPO_URL="https://github.com/HansC-anafter/mindscape-ai-local-core.git"
INSTALL_DIR=""
BRANCH="master"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║   Mindscape AI Local Core - Installer             ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# Check prerequisites
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ $1 is required but not installed."
        return 1
    fi
    echo "✓ $1 found"
}

echo "Checking prerequisites..."
check_command git || exit 1
check_command docker || exit 1

# Check if docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi
echo "✓ Docker is running"

# Check Ollama (optional but recommended for local LLM)
if command -v ollama &> /dev/null; then
    echo "✓ Ollama found"
    echo "  ℹ️  To use local LLM, pull a model:  ollama pull qwen3:8b"
else
    echo "⚠️  Ollama not found (optional, for local LLM support)"
    read -p "Install Ollama now? (Y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo "Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
        echo "  ℹ️  To use local LLM, pull a model:  ollama pull qwen3:8b"
    else
        echo "  Skipped. Install later from: https://ollama.com/download"
    fi
fi
echo ""

# Determine install directory
if [ -z "$INSTALL_DIR" ]; then
    # Use default name from repo
    INSTALL_DIR="mindscape-ai-local-core"
fi

# Check if directory already exists
if [ -d "$INSTALL_DIR" ]; then
    echo "⚠️  Directory '$INSTALL_DIR' already exists."
    read -p "Update existing installation? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Updating existing installation..."
        cd "$INSTALL_DIR"
        git pull origin "$BRANCH"
    else
        echo "Installation cancelled."
        exit 0
    fi
else
    echo "Cloning repository..."
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo ""
echo "Installing..."

# Run setup if exists
if [ -f "scripts/setup.sh" ]; then
    echo "Running setup..."
    chmod +x scripts/setup.sh
    ./scripts/setup.sh
fi

# macOS: whitelist Python for MLX firewall access (one-time sudo)
if [[ "$OSTYPE" == darwin* ]]; then
    FW="/usr/libexec/ApplicationFirewall/socketfilterfw"
    if [ -f "scripts/modules/inference/mlx.sh" ]; then
        source "scripts/modules/inference/mlx.sh"
        PYTHON_BIN="$(_find_mlx_python)"
        if [ -n "$PYTHON_BIN" ] && [ -x "$FW" ] && [ -x "$PYTHON_BIN" ]; then
            if ! "$FW" --listapps 2>/dev/null | grep -q "$PYTHON_BIN"; then
                echo "Setting up macOS firewall rules for MLX server ($PYTHON_BIN)..."
                sudo "$FW" --add "$PYTHON_BIN" 2>/dev/null || true
                sudo "$FW" --unblockapp "$PYTHON_BIN" 2>/dev/null || true
                echo "  ✓ Firewall rules configured"
            fi
        fi
    fi
fi

# Start services
if [ -f "scripts/start.sh" ]; then
    echo ""
    echo "Starting services..."
    chmod +x scripts/start.sh
    ./scripts/start.sh
fi

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║   ✅ Installation Complete!                       ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""
echo "Your Mindscape AI is running at:"
echo "  • Web Console: http://localhost:8300"
echo "  • Backend API: http://localhost:8200"
echo ""
echo "Next steps:"
echo "  cd $INSTALL_DIR"
echo "  # Configure API keys in .env (optional if using Ollama)"
echo ""
