#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=runtime_secrets/runtime_secrets.sh
source "$SCRIPT_DIR/runtime_secrets/runtime_secrets.sh"
mindscape_initialize_runtime_secrets "$PROJECT_ROOT"
cd "$PROJECT_ROOT"
exec docker compose "$@"
