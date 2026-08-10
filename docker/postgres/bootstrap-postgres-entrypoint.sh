#!/usr/bin/env sh
set -eu

PGDATA_DIR="${PGDATA:-/var/lib/postgresql/data}"
PG_HBA_FILE="${PGDATA_DIR}/pg_hba.conf"
REPLICATION_USER="${POSTGRES_USER:-mindscape}"
changed=0

ensure_replication_hba_entry() {
  if [ ! -f "$PG_HBA_FILE" ]; then
    return 0
  fi

  if ! grep -Eq "^[[:space:]]*host[[:space:]]+replication[[:space:]]+${REPLICATION_USER}[[:space:]]+0\\.0\\.0\\.0/0[[:space:]]" "$PG_HBA_FILE"; then
    printf 'host replication %s 0.0.0.0/0 scram-sha-256\n' "$REPLICATION_USER" >> "$PG_HBA_FILE"
    changed=1
  fi

  if ! grep -Eq "^[[:space:]]*host[[:space:]]+replication[[:space:]]+${REPLICATION_USER}[[:space:]]+::/0[[:space:]]" "$PG_HBA_FILE"; then
    printf 'host replication %s ::/0 scram-sha-256\n' "$REPLICATION_USER" >> "$PG_HBA_FILE"
    changed=1
  fi
}

if [ -f "${PG_HBA_FILE}" ] || [ -f "${PGDATA_DIR}/PG_VERSION" ]; then
  ensure_replication_hba_entry
fi

if [ "$changed" -eq 1 ]; then
  printf '[postgres-entrypoint-bootstrap] updated %s for replication user %s\n' "$PG_HBA_FILE" "$REPLICATION_USER" >&2
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
