#!/usr/bin/env bash
# Legacy Gemini-only convenience wrapper.
#
# Prefer scripts/start_cli_bridge.sh for the shared host bridge entrypoint.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export MINDSCAPE_SURFACE="${MINDSCAPE_SURFACE:-gemini_cli}"

exec "$REPO_ROOT/scripts/start_cli_bridge.sh" "$@"
