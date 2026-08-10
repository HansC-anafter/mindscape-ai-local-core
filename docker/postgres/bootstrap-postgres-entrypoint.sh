#!/usr/bin/env sh
set -eu

PGDATA_DIR="${PGDATA:-/var/lib/postgresql/data}"

if [ -f "${PGDATA_DIR}/PG_VERSION" ] || [ -f "${PGDATA_DIR}/pg_hba.conf" ]; then
  /bin/sh /opt/mindscape/ensure-replication-hba.sh
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
