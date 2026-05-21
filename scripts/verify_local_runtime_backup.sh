#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/verify_local_runtime_backup.sh <backup-dir>

Verify a local runtime backup:
  - incremental manifests are delegated to verify_local_runtime_incremental_backup.py
  - legacy manifests created by scripts/backup_local_runtime.sh are checked here
  - manifest is valid JSON
  - every manifest artifact exists, is non-empty, and matches sha256
  - PostgreSQL custom dumps can be listed with pg_restore
  - tar.gz archives can be listed
EOF
}

log() {
  printf '[verify-backup] %s\n' "$*" >&2
}

fail() {
  printf '[verify-backup][ERROR] %s\n' "$*" >&2
  exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

[[ $# -eq 1 ]] || {
  usage
  exit 2
}

BACKUP_DIR="$1"
[[ -d "$BACKUP_DIR" ]] || fail "Backup directory not found: $BACKUP_DIR"
[[ -f "$BACKUP_DIR/manifest.json" ]] || fail "manifest.json not found in $BACKUP_DIR"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose)
cd "$REPO_ROOT"

MANIFEST_MODE="$(python3 - "$BACKUP_DIR" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads((Path(sys.argv[1]) / "manifest.json").read_text(encoding="utf-8"))
print(manifest.get("mode") or "")
PY
)"

if [[ "$MANIFEST_MODE" == "incremental_runtime_backup" ]]; then
  python3 "$REPO_ROOT/scripts/verify_local_runtime_incremental_backup.py" "$BACKUP_DIR"
  exit 0
fi

log "checking manifest artifacts and checksums"
python3 - "$BACKUP_DIR" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
artifacts = manifest.get("artifacts")
if not isinstance(artifacts, list):
    raise SystemExit("manifest artifacts must be a list")
if not artifacts:
    raise SystemExit("manifest contains no artifacts")

for artifact in artifacts:
    rel = artifact.get("path")
    expected_size = int(artifact.get("bytes") or 0)
    expected_sha = str(artifact.get("sha256") or "")
    path = root / rel
    if not path.is_file():
        raise SystemExit(f"missing artifact: {rel}")
    actual_size = path.stat().st_size
    if actual_size <= 0:
        raise SystemExit(f"empty artifact: {rel}")
    if expected_size != actual_size:
        raise SystemExit(f"size mismatch for {rel}: expected {expected_size}, got {actual_size}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha = digest.hexdigest()
    if expected_sha != actual_sha:
        raise SystemExit(f"sha256 mismatch for {rel}: expected {expected_sha}, got {actual_sha}")

print(f"verified {len(artifacts)} artifacts")
PY

for dump in "$BACKUP_DIR"/postgres/*.dump; do
  [[ -e "$dump" ]] || continue
  log "checking PostgreSQL dump: ${dump#$BACKUP_DIR/}"
  "${COMPOSE[@]}" exec -T postgres sh -lc 'pg_restore --list' <"$dump" >/dev/null
done

for archive in "$BACKUP_DIR"/archives/*.tar.gz; do
  [[ -e "$archive" ]] || continue
  log "checking archive: ${archive#$BACKUP_DIR/}"
  tar -tzf "$archive" >/dev/null
done

log "backup verification passed: $BACKUP_DIR"
