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

# Check Node.js (required for CLI agents like gemini-cli, claude-code)
if command -v node &> /dev/null; then
    NODE_VER=$(node --version 2>/dev/null)
    echo "✓ Node.js found ($NODE_VER)"
else
    echo "⚠️  Node.js not found (required for CLI agents: gemini-cli, claude-code, codex)"
    read -p "Install Node.js LTS now? (Y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        if [[ "$OSTYPE" == darwin* ]] && command -v brew &> /dev/null; then
            echo "Installing Node.js via Homebrew..."
            brew install node
        elif command -v apt-get &> /dev/null; then
            echo "Installing Node.js via apt..."
            curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
            sudo apt-get install -y nodejs
        elif command -v dnf &> /dev/null; then
            echo "Installing Node.js via dnf..."
            curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -
            sudo dnf install -y nodejs
        else
            echo "  Could not auto-install. Install Node.js from: https://nodejs.org/"
        fi
        if command -v node &> /dev/null; then
            echo "  ✓ Node.js installed ($(node --version))"
        fi
    else
        echo "  Skipped. Install later from: https://nodejs.org/"
        echo "  Without Node.js, CLI agents will not be available."
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

# Install Device Node + CLI agents (requires Node.js on host)
if command -v node &> /dev/null && command -v npm &> /dev/null; then
    echo ""
    echo "Setting up Device Node (CLI agent bridge)..."
    if [[ "$OSTYPE" == darwin* ]] && [ -f "device-node/scripts/install-macos.sh" ]; then
        chmod +x device-node/scripts/install-macos.sh
        device-node/scripts/install-macos.sh || echo "  ⚠️  Device Node setup failed (non-fatal)"
    elif [ -d "device-node" ]; then
        echo "  Building Device Node..."
        cd device-node && npm install --silent && npm run build && cd ..
        # Install gemini-cli if not present
        if ! command -v gemini &> /dev/null; then
            echo "  📦 Installing gemini-cli..."
            npm install -g @google/gemini-cli 2>/dev/null || echo "  ⚠️  gemini-cli install failed (non-fatal)"
        fi
    fi
else
    echo ""
    echo "⚠️  Node.js not found — skipping Device Node setup."
    echo "  Install Node.js >= 18 to enable CLI agents (gemini-cli, claude-code, codex)."
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
echo "  # CLI Bridge: ./scripts/start_cli_bridge.sh (for Gemini CLI / Claude Code)"
echo ""
