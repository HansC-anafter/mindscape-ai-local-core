#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# macOS launchd service management module
# Delegates to device-node/scripts/install-macos.sh instead of
# duplicating the launchd logic (fixes E20).
# ─────────────────────────────────────────────────────────

setup_device_node_launchd() {
  local project_root="${PROJECT_ROOT:-.}"
  local dn_dir="$project_root/device-node"

  if [ ! -d "$dn_dir" ]; then
    echo "  ⚠️  device-node directory not found, skipping"
    return 0
  fi

  if ! command -v node &>/dev/null; then
    echo "  ⚠️  Node.js not found, skipping Device Node setup"
    return 0
  fi

  # Check if launchd agent is already running
  if launchctl list 2>/dev/null | grep -q "ai.mindscape.device-node"; then
    echo "  ✓ Device Node launchd agent running"
    return 0
  fi

  local plist_dst="$HOME/Library/LaunchAgents/ai.mindscape.device-node.plist"

  if [ -f "$plist_dst" ]; then
    # Plist exists but not loaded — load it
    echo "  Loading Device Node launchd agent..."
    launchctl load "$plist_dst"
    sleep 2
    if launchctl list 2>/dev/null | grep -q "ai.mindscape.device-node"; then
      echo "  ✓ Device Node started via launchd"
    else
      echo "  ⚠️  Device Node launchd agent failed to start"
    fi
  else
    # First run — delegate to install-macos.sh
    local install_script="$dn_dir/scripts/install-macos.sh"
    if [ -f "$install_script" ]; then
      echo "  First-time setup: running install-macos.sh..."
      bash "$install_script"
    else
      # Fallback: inline install (same logic as install-macos.sh)
      echo "  First-time setup: installing Device Node launchd agent..."
      cd "$dn_dir"
      npm install --silent 2>/dev/null
      npm run build --silent 2>/dev/null
      mkdir -p logs

      local node_bin
      node_bin="$(which node)"
      local plist_template="$dn_dir/config/ai.mindscape.device-node.plist"

      mkdir -p "$HOME/Library/LaunchAgents"
      sed \
        -e "s|__NODE_BIN__|${node_bin}|g" \
        -e "s|__PROJECT_DIR__|${dn_dir}|g" \
        "$plist_template" > "$plist_dst"

      launchctl load "$plist_dst"
      sleep 2
      if launchctl list 2>/dev/null | grep -q "ai.mindscape.device-node"; then
        echo "  ✓ Device Node installed and started (launchd, port 3100)"
      else
        echo "  ⚠️  Device Node install failed. Run manually: cd device-node && npm run install:macos"
      fi
      cd "$project_root"
    fi
  fi
}
