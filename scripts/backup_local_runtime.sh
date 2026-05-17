#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/backup_local_runtime.sh [options]

Create a verified local-runtime backup for Docker Local-Core.

This script is not incremental. The default mode writes fresh PostgreSQL dumps
and a fresh compressed archive of /app/data. Do not use the default mode as a
routine preflight gate when an existing verified backup already covers the risk.

By default this creates:
  - PostgreSQL custom dumps for mindscape_core and mindscape_vectors
  - PostgreSQL globals dump
  - A compressed archive of /app/data streamed from the host data mount,
    excluding postgres, existing backups, e2e traces, and IG thumbnail cache
  - Runtime metadata, profile-state validation report, manifest, and sha256s

Options:
  --output-dir DIR        Backup root directory. Default:
                         <LOCAL_CORE_DATA_HOST_DIR>/backups/local-runtime
  --name NAME            Backup directory name. Default:
                         mindscape_local_runtime_<UTC timestamp>
  --full                 Include IG thumbnail cache and e2e traces.
  --include-thumbnails   Include /app/data/ig_thumbnails.
  --include-e2e-traces   Include /app/data/e2e-traces.
  --include-logs         Include /app/logs as a separate archive.
  --skip-db              Skip PostgreSQL dumps.
  --skip-files           Skip /app/data archive.
  --dry-run              Print resolved plan without writing backup files.
  -h, --help             Show this help.

Environment:
  LOCAL_CORE_BACKUP_ROOT  Same as --output-dir.
  LOCAL_CORE_DATA_HOST_DIR
                         Used as fallback when Docker mount inspection is
                         unavailable.
EOF
}

log() {
  printf '[backup] %s\n' "$*" >&2
}

fail() {
  printf '[backup][ERROR] %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose)
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_NAME="mindscape_local_runtime_${TIMESTAMP}"
BACKUP_ROOT="${LOCAL_CORE_BACKUP_ROOT:-}"
INCLUDE_THUMBNAILS=0
INCLUDE_E2E_TRACES=0
INCLUDE_LOGS=0
SKIP_DB=0
SKIP_FILES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      [[ $# -ge 2 ]] || fail "--output-dir requires a value"
      BACKUP_ROOT="$2"
      shift 2
      ;;
    --name)
      [[ $# -ge 2 ]] || fail "--name requires a value"
      BACKUP_NAME="$2"
      shift 2
      ;;
    --full)
      INCLUDE_THUMBNAILS=1
      INCLUDE_E2E_TRACES=1
      shift
      ;;
    --include-thumbnails)
      INCLUDE_THUMBNAILS=1
      shift
      ;;
    --include-e2e-traces)
      INCLUDE_E2E_TRACES=1
      shift
      ;;
    --include-logs)
      INCLUDE_LOGS=1
      shift
      ;;
    --skip-db)
      SKIP_DB=1
      shift
      ;;
    --skip-files)
      SKIP_FILES=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

case "$BACKUP_NAME" in
  *[!A-Za-z0-9._-]*|'')
    fail "Backup name may contain only letters, numbers, dot, underscore, and dash"
    ;;
esac

require_cmd docker
require_cmd python3
require_cmd tar
require_cmd mktemp
require_cmd ln

cd "$REPO_ROOT"

backend_container="$("${COMPOSE[@]}" ps -q backend 2>/dev/null || true)"
data_host_dir=""
if [[ -n "$backend_container" ]]; then
  data_host_dir="$(docker inspect \
    --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}' \
    "$backend_container" \
    2>/dev/null || true)"
fi
if [[ -z "$data_host_dir" ]]; then
  data_host_dir="$("${COMPOSE[@]}" config 2>/dev/null | awk '
    /^[[:space:]]+- type: bind[[:space:]]*$/ { in_mount = 1; source = ""; next }
    in_mount && /^[[:space:]]+source:[[:space:]]*/ {
      line = $0
      sub(/^[[:space:]]+source:[[:space:]]*/, "", line)
      source = line
      next
    }
    in_mount && /^[[:space:]]+target:[[:space:]]*\/app\/data[[:space:]]*$/ {
      print source
      exit
    }
    in_mount && /^[[:space:]]+- type: / { in_mount = 0; source = "" }
  ' || true)"
fi
if [[ -z "$data_host_dir" ]]; then
  data_host_dir="${LOCAL_CORE_DATA_HOST_DIR:-$REPO_ROOT/data}"
fi

if [[ -z "$BACKUP_ROOT" ]]; then
  BACKUP_ROOT="$data_host_dir/backups/local-runtime"
fi

FINAL_DIR="$BACKUP_ROOT/$BACKUP_NAME"
STAGE_DIR="$BACKUP_ROOT/.${BACKUP_NAME}.partial"
LOCK_DIR="$BACKUP_ROOT/.backup.lock"

log "repo_root=$REPO_ROOT"
log "data_host_dir=$data_host_dir"
log "backup_root=$BACKUP_ROOT"
log "backup_name=$BACKUP_NAME"
log "include_thumbnails=$INCLUDE_THUMBNAILS include_e2e_traces=$INCLUDE_E2E_TRACES include_logs=$INCLUDE_LOGS"
log "skip_db=$SKIP_DB skip_files=$SKIP_FILES"

if [[ "$DRY_RUN" == "1" ]]; then
  log "dry-run: no files will be written"
  exit 0
fi

mkdir -p "$BACKUP_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  fail "Another backup appears to be running: $LOCK_DIR"
fi

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

[[ ! -e "$FINAL_DIR" ]] || fail "Backup already exists: $FINAL_DIR"
[[ ! -e "$STAGE_DIR" ]] || fail "Stale partial backup exists: $STAGE_DIR"

mkdir -p "$STAGE_DIR/postgres" "$STAGE_DIR/archives" "$STAGE_DIR/metadata"

assert_nonempty_file() {
  local path="$1"
  [[ -s "$path" ]] || fail "Expected non-empty file: $path"
}

write_command_output() {
  local path="$1"
  shift
  if "$@" >"$path.tmp" 2>"$path.stderr.tmp"; then
    mv "$path.tmp" "$path"
    if [[ -s "$path.stderr.tmp" ]]; then
      mv "$path.stderr.tmp" "$path.stderr"
    else
      rm -f "$path.stderr.tmp"
    fi
  else
    mv "$path.tmp" "$path.failed" 2>/dev/null || true
    mv "$path.stderr.tmp" "$path.stderr" 2>/dev/null || true
    log "warning: metadata command failed for $path"
  fi
}

write_metadata() {
  log "writing runtime metadata"
  write_command_output "$STAGE_DIR/metadata/docker-compose-ps.txt" "${COMPOSE[@]}" ps
  write_command_output "$STAGE_DIR/metadata/docker-compose-services.txt" "${COMPOSE[@]}" config --services

  if [[ -n "$backend_container" ]]; then
    write_command_output "$STAGE_DIR/metadata/backend-mounts.json" docker inspect --format '{{json .Mounts}}' "$backend_container"
  fi

  write_command_output "$STAGE_DIR/metadata/postgres-sizes.txt" \
    "${COMPOSE[@]}" exec -T postgres sh -lc \
    'psql -U "${POSTGRES_USER:-mindscape}" -d "${POSTGRES_CORE_DB:-mindscape_core}" -c "select current_database(), pg_database_size(current_database()) as bytes;" && psql -U "${POSTGRES_USER:-mindscape}" -d "${POSTGRES_VECTOR_DB:-mindscape_vectors}" -c "select current_database(), pg_database_size(current_database()) as bytes;"'

  write_command_output "$STAGE_DIR/metadata/redis-persistence.txt" \
    "${COMPOSE[@]}" exec -T redis redis-cli CONFIG GET save appendonly dir dbfilename appendfilename

  cat >"$STAGE_DIR/metadata/backup-options.env" <<EOF
BACKUP_NAME=$BACKUP_NAME
DATA_HOST_DIR=$data_host_dir
APP_DATA_ARCHIVE_SOURCE=host_mount
INCLUDE_THUMBNAILS=$INCLUDE_THUMBNAILS
INCLUDE_E2E_TRACES=$INCLUDE_E2E_TRACES
INCLUDE_LOGS=$INCLUDE_LOGS
SKIP_DB=$SKIP_DB
SKIP_FILES=$SKIP_FILES
EOF

  if "${COMPOSE[@]}" exec -T backend python - <<'PY' >"$STAGE_DIR/metadata/profile-state-report.json.tmp"; then
import json
from pathlib import Path

root = Path("/app/data/ig-browser-profiles")
profiles = []
for path in sorted(root.glob("*/storage_state.json")):
    item = {
        "profile": path.parent.name,
        "path": str(path),
        "size": path.stat().st_size,
        "valid": True,
        "error": None,
    }
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        item["valid"] = False
        item["error"] = f"{type(exc).__name__}: {exc}"
    profiles.append(item)

print(json.dumps({"profiles": profiles}, indent=2, sort_keys=True))
PY
    mv "$STAGE_DIR/metadata/profile-state-report.json.tmp" "$STAGE_DIR/metadata/profile-state-report.json"
  else
    mv "$STAGE_DIR/metadata/profile-state-report.json.tmp" "$STAGE_DIR/metadata/profile-state-report.failed" 2>/dev/null || true
    log "warning: profile-state report failed"
  fi
}

dump_custom_database() {
  local label="$1"
  local db_expr="$2"
  local outfile="$STAGE_DIR/postgres/${label}.dump"
  local listfile="$STAGE_DIR/postgres/${label}.dump.list"

  log "dumping PostgreSQL database: $label"
  "${COMPOSE[@]}" exec -T postgres sh -lc \
    "pg_dump -U \"\${POSTGRES_USER:-mindscape}\" -d \"${db_expr}\" --format=custom --no-owner --no-privileges" \
    >"${outfile}.tmp"
  assert_nonempty_file "${outfile}.tmp"

  "${COMPOSE[@]}" exec -T postgres sh -lc 'pg_restore --list' \
    <"${outfile}.tmp" >"${listfile}.tmp"
  assert_nonempty_file "${listfile}.tmp"

  mv "${outfile}.tmp" "$outfile"
  mv "${listfile}.tmp" "$listfile"
}

dump_postgres() {
  [[ "$SKIP_DB" == "0" ]] || {
    log "skipping PostgreSQL dumps"
    return
  }

  dump_custom_database "mindscape_core" '${POSTGRES_CORE_DB:-mindscape_core}'
  dump_custom_database "mindscape_vectors" '${POSTGRES_VECTOR_DB:-mindscape_vectors}'

  log "dumping PostgreSQL globals"
  "${COMPOSE[@]}" exec -T postgres sh -lc \
    'pg_dumpall -U "${POSTGRES_USER:-mindscape}" --globals-only' \
    >"$STAGE_DIR/postgres/globals.sql.tmp"
  assert_nonempty_file "$STAGE_DIR/postgres/globals.sql.tmp"
  mv "$STAGE_DIR/postgres/globals.sql.tmp" "$STAGE_DIR/postgres/globals.sql"
}

archive_app_data() {
  [[ "$SKIP_FILES" == "0" ]] || {
    log "skipping file archive"
    return
  }

  local archive="$STAGE_DIR/archives/app-data.tar.gz"
  local -a excludes=(
    "--exclude=app/data/postgres"
    "--exclude=app/data/backups"
  )
  if [[ "$INCLUDE_THUMBNAILS" != "1" ]]; then
    excludes+=("--exclude=app/data/ig_thumbnails")
  fi
  if [[ "$INCLUDE_E2E_TRACES" != "1" ]]; then
    excludes+=("--exclude=app/data/e2e-traces")
  fi

  [[ -d "$data_host_dir" ]] || fail "Resolved /app/data host path is not a directory: $data_host_dir"

  local archive_root
  archive_root="$(mktemp -d "${TMPDIR:-/tmp}/mindscape-app-data-archive.XXXXXX")"
  mkdir -p "$archive_root/app"
  ln -s "$data_host_dir" "$archive_root/app/data"

  log "archiving /app/data from host mount: $data_host_dir"
  if tar -C "$archive_root" -h "${excludes[@]}" -czf "${archive}.tmp" app/data; then
    rm -rf "$archive_root"
  else
    local tar_status=$?
    rm -rf "$archive_root"
    return "$tar_status"
  fi
  assert_nonempty_file "${archive}.tmp"

  tar -tzf "${archive}.tmp" >"${archive}.list.tmp"
  assert_nonempty_file "${archive}.list.tmp"

  mv "${archive}.tmp" "$archive"
  mv "${archive}.list.tmp" "${archive}.list"
}

archive_logs() {
  [[ "$INCLUDE_LOGS" == "1" ]] || return 0

  local archive="$STAGE_DIR/archives/logs.tar.gz"
  log "archiving /app/logs"
  "${COMPOSE[@]}" exec -T backend tar -C / -czf - app/logs >"${archive}.tmp"
  assert_nonempty_file "${archive}.tmp"
  tar -tzf "${archive}.tmp" >"${archive}.list.tmp"
  assert_nonempty_file "${archive}.list.tmp"
  mv "${archive}.tmp" "$archive"
  mv "${archive}.list.tmp" "${archive}.list"
}

write_manifest() {
  log "writing manifest and checksums"
  local git_commit
  git_commit="$(git rev-parse HEAD 2>/dev/null || true)"
  BACKUP_CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  BACKUP_NAME="$BACKUP_NAME" \
  REPO_ROOT="$REPO_ROOT" \
  DATA_HOST_DIR="$data_host_dir" \
  GIT_COMMIT="$git_commit" \
  INCLUDE_THUMBNAILS="$INCLUDE_THUMBNAILS" \
  INCLUDE_E2E_TRACES="$INCLUDE_E2E_TRACES" \
  INCLUDE_LOGS="$INCLUDE_LOGS" \
  SKIP_DB="$SKIP_DB" \
  SKIP_FILES="$SKIP_FILES" \
  python3 - "$STAGE_DIR" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
artifacts = []
sha_lines = []

for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    if path.name in {"manifest.json", "SHA256SUMS"}:
        continue
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    rel = path.relative_to(root).as_posix()
    hexdigest = digest.hexdigest()
    artifacts.append(
        {
            "path": rel,
            "bytes": path.stat().st_size,
            "sha256": hexdigest,
        }
    )
    sha_lines.append(f"{hexdigest}  {rel}\n")

(root / "SHA256SUMS").write_text("".join(sha_lines), encoding="utf-8")

manifest = {
    "schema_version": "1.0",
    "backup_name": os.environ["BACKUP_NAME"],
    "created_at": os.environ["BACKUP_CREATED_AT"],
    "repo_root": os.environ["REPO_ROOT"],
    "git_commit": os.environ.get("GIT_COMMIT") or None,
    "data_host_dir": os.environ["DATA_HOST_DIR"],
    "options": {
        "include_thumbnails": os.environ["INCLUDE_THUMBNAILS"] == "1",
        "include_e2e_traces": os.environ["INCLUDE_E2E_TRACES"] == "1",
        "include_logs": os.environ["INCLUDE_LOGS"] == "1",
        "skip_db": os.environ["SKIP_DB"] == "1",
        "skip_files": os.environ["SKIP_FILES"] == "1",
    },
    "artifacts": artifacts,
}
(root / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

write_metadata
dump_postgres
archive_app_data
archive_logs
write_manifest

mv "$STAGE_DIR" "$FINAL_DIR"
log "backup completed: $FINAL_DIR"
log "verify with: scripts/verify_local_runtime_backup.sh '$FINAL_DIR'"
