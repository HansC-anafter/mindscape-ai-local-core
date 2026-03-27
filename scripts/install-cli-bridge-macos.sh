#!/bin/bash
# Mindscape CLI Bridge - macOS Installation Script
#
# Installs a launchd agent that keeps the shared CLI bridge supervisor
# running across reboots. No sudo required.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_TEMPLATE="$PROJECT_DIR/scripts/config/ai.mindscape.cli-bridge.plist"
PLIST_DST="$HOME/Library/LaunchAgents/ai.mindscape.cli-bridge.plist"

escape_sed_replacement() {
    printf '%s' "$1" | sed -e 's/[&|]/\\&/g'
}

append_path_once() {
    local current="$1"
    local entry="$2"
    case ":$current:" in
        *":$entry:"*) printf '%s' "$current" ;;
        *) printf '%s' "${current:+$current:}$entry" ;;
    esac
}

echo "Installing Mindscape CLI Bridge launchd agent..."
echo "   Project: $PROJECT_DIR"

if [[ ! -f "$PLIST_TEMPLATE" ]]; then
    echo "Error: plist template not found: $PLIST_TEMPLATE"
    exit 1
fi

BASH_BIN="$(command -v bash || true)"
if [[ -z "$BASH_BIN" ]]; then
    echo "Error: bash not found in PATH."
    exit 1
fi

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$HOME/Library/LaunchAgents"

PATH_VALUE="${PATH:-}"
for entry in /opt/homebrew/bin /usr/local/bin /usr/bin /bin /usr/sbin /sbin; do
    PATH_VALUE="$(append_path_once "$PATH_VALUE" "$entry")"
done

BASH_ESCAPED="$(escape_sed_replacement "$BASH_BIN")"
PROJECT_ESCAPED="$(escape_sed_replacement "$PROJECT_DIR")"
HOME_ESCAPED="$(escape_sed_replacement "$HOME")"
PATH_ESCAPED="$(escape_sed_replacement "$PATH_VALUE")"

sed \
    -e "s|__BASH_BIN__|${BASH_ESCAPED}|g" \
    -e "s|__PROJECT_DIR__|${PROJECT_ESCAPED}|g" \
    -e "s|__HOME__|${HOME_ESCAPED}|g" \
    -e "s|__PATH__|${PATH_ESCAPED}|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DST"

launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo ""
echo "CLI Bridge launchd agent installed and started."
echo ""
echo "  Status:  launchctl list | grep mindscape"
echo "  Logs:    tail -f $PROJECT_DIR/logs/cli-bridge.log"
echo "  Stop:    launchctl unload ~/Library/LaunchAgents/ai.mindscape.cli-bridge.plist"
echo "  Restart: launchctl unload ~/Library/LaunchAgents/ai.mindscape.cli-bridge.plist && \\"
echo "           launchctl load   ~/Library/LaunchAgents/ai.mindscape.cli-bridge.plist"
