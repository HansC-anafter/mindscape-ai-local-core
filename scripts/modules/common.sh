#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Common helpers module
# Source this file: source "$SCRIPT_DIR/modules/common.sh"
# ─────────────────────────────────────────────────────────

# Resolve project root from any script location
resolve_project_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  # If called from scripts/modules/, go up 2 levels
  # If called from scripts/, go up 1 level
  if [[ "$script_dir" == */scripts/modules* ]]; then
    PROJECT_ROOT="$(cd "$script_dir/../.." && pwd)"
  elif [[ "$script_dir" == */scripts ]]; then
    PROJECT_ROOT="$(cd "$script_dir/.." && pwd)"
  else
    PROJECT_ROOT="$script_dir"
  fi
  export PROJECT_ROOT
}

check_docker() {
  if ! command -v docker &>/dev/null; then
    echo "  ✗ Docker command not found"
    return 1
  fi
  if ! docker info &>/dev/null; then
    echo "  ✗ Docker daemon is not running"
    return 1
  fi
  if ! docker compose version &>/dev/null; then
    echo "  ✗ Docker Compose not available"
    return 1
  fi
  return 0
}

log_info()  { echo "  ✓ $*"; }
log_warn()  { echo "  ⚠️  $*"; }
log_error() { echo "  ✗ $*"; }
log_step()  { echo ""; echo "$*"; }
