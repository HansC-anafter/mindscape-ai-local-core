#!/bin/bash
# Mindscape Device Node - macOS Installation Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="/usr/local/lib/mindscape-device-node"
PLIST_SRC="$PROJECT_DIR/config/ai.mindscape.device-node.plist"
PLIST_DST="$HOME/Library/LaunchAgents/ai.mindscape.device-node.plist"

echo "🚀 Installing Mindscape Device Node..."

# Build the project
echo "📦 Building project..."
cd "$PROJECT_DIR"
npm install
npm run build

# Create installation directory
echo "📁 Creating installation directory..."
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r "$PROJECT_DIR/dist" "$INSTALL_DIR/"
sudo cp -r "$PROJECT_DIR/config" "$INSTALL_DIR/"
sudo cp "$PROJECT_DIR/package.json" "$INSTALL_DIR/"

# Install production dependencies
echo "📦 Installing production dependencies..."
cd "$INSTALL_DIR"
sudo npm install --production

# Create log directory
sudo mkdir -p /usr/local/var/log

# Install launchd plist
echo "🔧 Installing launchd service..."
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

# Unload if already loaded
launchctl unload "$PLIST_DST" 2>/dev/null || true

# Load the service
launchctl load "$PLIST_DST"

echo "✅ Mindscape Device Node installed successfully!"
echo ""
echo "To check status:"
echo "  launchctl list | grep mindscape"
echo ""
echo "To view logs:"
echo "  tail -f /usr/local/var/log/mindscape-device-node.log"
echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/ai.mindscape.device-node.plist"
echo "  rm ~/Library/LaunchAgents/ai.mindscape.device-node.plist"
echo "  sudo rm -rf /usr/local/lib/mindscape-device-node"
