#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/maintenance/postgres_reclaim_preflight.sh [--verified-backup-dir <dir>] [preflight args...]

Run the PostgreSQL reclaim preflight inside the backend container with the
repository and optional verified backup directory mounted read-only.
EOF
}

fail() {
  printf '[postgres-reclaim-preflight][ERROR] %s\n' "$*" >&2
  exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR=""
REPORT_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --verified-backup-dir)
      [[ $# -ge 2 ]] || fail "--verified-backup-dir requires a directory"
      BACKUP_DIR="$2"
      shift 2
      ;;
    --verified-backup-dir=*)
      BACKUP_DIR="${1#*=}"
      shift
      ;;
    *)
      REPORT_ARGS+=("$1")
      shift
      ;;
  esac
done

RUN_ARGS=(
  run
  --rm
  --no-deps
  -v "$REPO_ROOT:/repo:ro"
  -e LOCAL_CORE_PROJECT_ROOT=/repo
  -e PYTHONPYCACHEPREFIX=/tmp/pycache
  -w /repo
)

if [[ -n "$BACKUP_DIR" ]]; then
  [[ -d "$BACKUP_DIR" ]] || fail "Backup directory not found: $BACKUP_DIR"
  BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd -P)"
  RUN_ARGS+=(-v "$BACKUP_DIR:/verified-backup:ro")
  REPORT_ARGS+=(--verified-backup-dir /verified-backup)
fi

cd "$REPO_ROOT"
exec docker compose "${RUN_ARGS[@]}" backend sh -lc \
  'PYTHONPATH=/repo:/repo/backend python backend/scripts/postgres_runtime_preflight_report.py --compose-file /repo/docker-compose.yml "$@"' \
  postgres-reclaim-preflight "${REPORT_ARGS[@]}"
