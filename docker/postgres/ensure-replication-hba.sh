#!/usr/bin/env sh
set -eu

PGDATA_DIR="${PGDATA:-/var/lib/postgresql/data}"
PG_HBA_FILE="${PGDATA_DIR}/pg_hba.conf"
REPLICATION_USER="${POSTGRES_USER:-mindscape}"

ensure_replication_hba_entry() {
  if [ ! -f "$PG_HBA_FILE" ]; then
    return 0
  fi

  if ! grep -Eq "^[[:space:]]*host[[:space:]]+replication[[:space:]]+${REPLICATION_USER}[[:space:]]+0\\.0\\.0\\.0/0[[:space:]]" "$PG_HBA_FILE"; then
    printf 'host replication %s 0.0.0.0/0 scram-sha-256\n' "$REPLICATION_USER" >> "$PG_HBA_FILE"
  fi

  if ! grep -Eq "^[[:space:]]*host[[:space:]]+replication[[:space:]]+${REPLICATION_USER}[[:space:]]+::/0[[:space:]]" "$PG_HBA_FILE"; then
    printf 'host replication %s ::/0 scram-sha-256\n' "$REPLICATION_USER" >> "$PG_HBA_FILE"
  fi
}

ensure_replication_hba_entry
