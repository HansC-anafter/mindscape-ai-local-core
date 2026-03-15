#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Linux systemd --user service management module
# Falls back to nohup if systemd user session is unavailable (FM3).
# ─────────────────────────────────────────────────────────

setup_device_node_systemd() {
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

  # Build if needed
  if [ ! -d "$dn_dir/dist" ]; then
    echo "  Building Device Node..."
    cd "$dn_dir"
    npm install --silent 2>/dev/null
    npm run build --silent 2>/dev/null
    cd "$project_root"
  fi

  local node_bin
  node_bin="$(which node)"
  local service_name="ai.mindscape.device-node"

  # ── Try systemd --user first ──
  if command -v systemctl &>/dev/null && systemctl --user status &>/dev/null 2>&1; then
    # Enable user linger so service survives logout (FM3)
    loginctl enable-linger "$(whoami)" 2>/dev/null || true

    local unit_dir="$HOME/.config/systemd/user"
    local unit_file="$unit_dir/${service_name}.service"
    mkdir -p "$unit_dir"

    cat > "$unit_file" << EOF
[Unit]
Description=Mindscape Device Node
After=network.target

[Service]
Type=simple
WorkingDirectory=$dn_dir
ExecStart=$node_bin $dn_dir/dist/index.js
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable "$service_name" 2>/dev/null || true
    systemctl --user restart "$service_name"
    sleep 2

    if systemctl --user is-active "$service_name" &>/dev/null; then
      echo "  ✓ Device Node started (systemd --user)"
      return 0
    else
      echo "  ⚠️  systemd --user failed, falling back to nohup"
    fi
  fi

  # ── Fallback: nohup (FM3 — no systemd user session) ──
  if pgrep -f "device-node/dist/index.js" &>/dev/null; then
    echo "  ✓ Device Node already running (nohup)"
    return 0
  fi

  mkdir -p "$dn_dir/logs"
  nohup "$node_bin" "$dn_dir/dist/index.js" > "$dn_dir/logs/device-node.log" 2>&1 &
  local pid=$!
  sleep 2
  if ps -p $pid > /dev/null 2>&1; then
    echo "  ✓ Device Node started (nohup, PID: $pid)"
  else
    echo "  ⚠️  Device Node failed to start. See $dn_dir/logs/device-node.log"
  fi
}
