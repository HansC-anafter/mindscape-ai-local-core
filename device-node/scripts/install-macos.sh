#!/bin/bash
# Mindscape Device Node - macOS Installation Script (dev-mode)
#
# Installs a launchd agent that runs Device Node directly from the project
# directory. No sudo required. Clone → npm install → npm run install:macos.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_TEMPLATE="$PROJECT_DIR/config/ai.mindscape.device-node.plist"
PLIST_DST="$HOME/Library/LaunchAgents/ai.mindscape.device-node.plist"

echo "🚀 Installing Mindscape Device Node (dev-mode)..."
echo "   Project: $PROJECT_DIR"

# ── 1. Build ─────────────────────────────────────────────────────────────
echo "📦 Building TypeScript..."
cd "$PROJECT_DIR"
npm install --silent
npm run build

# ── 2. Create logs directory ─────────────────────────────────────────────
mkdir -p "$PROJECT_DIR/logs"

# ── 3. Detect node binary ────────────────────────────────────────────────
NODE_BIN="$(which node)"
if [ -z "$NODE_BIN" ]; then
    echo "❌ Error: node not found in PATH. Please install Node.js >= 18."
    exit 1
fi
echo "   Node: $NODE_BIN ($(node --version))"

# ── 4. Generate plist from template ──────────────────────────────────────
echo "🔧 Installing launchd agent..."
mkdir -p "$HOME/Library/LaunchAgents"

sed \
    -e "s|__NODE_BIN__|${NODE_BIN}|g" \
    -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DST"

# ── 5. (Re)load the agent ────────────────────────────────────────────────
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo ""
echo "✅ Device Node installed and started!"
echo ""
echo "  Status:  launchctl list | grep mindscape"
echo "  Logs:    tail -f $PROJECT_DIR/logs/device-node.log"
echo "  Stop:    launchctl unload ~/Library/LaunchAgents/ai.mindscape.device-node.plist"
echo "  Restart: launchctl unload ~/Library/LaunchAgents/ai.mindscape.device-node.plist && \\"
echo "           launchctl load   ~/Library/LaunchAgents/ai.mindscape.device-node.plist"
echo ""
echo "  After code changes:  npm run build && launchctl unload ~/Library/LaunchAgents/ai.mindscape.device-node.plist && launchctl load ~/Library/LaunchAgents/ai.mindscape.device-node.plist"
