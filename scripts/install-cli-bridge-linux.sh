#!/usr/bin/env bash
# Mindscape CLI Bridge - Linux Installation Script
#
# Installs a systemd --user service for the shared CLI bridge supervisor.
# Falls back to a nohup supervisor if a user systemd session is unavailable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="ai.mindscape.cli-bridge"
SUPERVISOR_SCRIPT="$PROJECT_DIR/scripts/start_cli_bridge_supervisor.sh"

append_path_once() {
    local current="$1"
    local entry="$2"
    case ":$current:" in
        *":$entry:"*) printf '%s' "$current" ;;
        *) printf '%s' "${current:+$current:}$entry" ;;
    esac
}

echo "Installing Mindscape CLI Bridge..."
echo "  Project: $PROJECT_DIR"

if [[ ! -f "$SUPERVISOR_SCRIPT" ]]; then
    echo "Error: supervisor script not found: $SUPERVISOR_SCRIPT" >&2
    exit 1
fi

mkdir -p "$PROJECT_DIR/logs"

BASH_BIN="$(command -v bash || true)"
if [[ -z "$BASH_BIN" ]]; then
    echo "Error: bash not found in PATH." >&2
    exit 1
fi

PATH_VALUE="${PATH:-}"
for entry in /usr/local/bin /usr/bin /bin /usr/sbin /sbin; do
    PATH_VALUE="$(append_path_once "$PATH_VALUE" "$entry")"
done

if command -v systemctl &>/dev/null && systemctl --user status &>/dev/null 2>&1; then
    loginctl enable-linger "$(whoami)" 2>/dev/null || true

    UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    UNIT_FILE="$UNIT_DIR/${SERVICE_NAME}.service"
    mkdir -p "$UNIT_DIR"

    cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Mindscape CLI Bridge
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
Environment=HOME=$HOME
Environment=PATH=$PATH_VALUE
Environment=MINDSCAPE_WORKSPACE_ROOT=$PROJECT_DIR
Environment=MINDSCAPE_BRIDGE_SURFACES=gemini_cli,codex_cli,claude_code_cli
ExecStart=$BASH_BIN $SUPERVISOR_SCRIPT --all
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE_NAME" 2>/dev/null || true
    systemctl --user restart "$SERVICE_NAME"

    echo "CLI Bridge installed as systemd --user service."
    echo "  Status:  systemctl --user status $SERVICE_NAME"
    echo "  Logs:    journalctl --user -u $SERVICE_NAME -f"
else
    if pgrep -f "start_cli_bridge_supervisor.sh" &>/dev/null; then
        echo "CLI Bridge supervisor already running (nohup fallback)"
        exit 0
    fi

    nohup "$BASH_BIN" "$SUPERVISOR_SCRIPT" --all > "$PROJECT_DIR/logs/cli-bridge.log" 2>&1 &
    echo "CLI Bridge started via nohup fallback (PID: $!)"
    echo "  Logs: tail -f $PROJECT_DIR/logs/cli-bridge.log"
fi
