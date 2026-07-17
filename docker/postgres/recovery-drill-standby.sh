#!/bin/sh
set -eu

if [ ! -s "${PGDATA}/PG_VERSION" ]; then
  rm -rf "${PGDATA:?}"/*
  export PGPASSWORD="${POSTGRES_PASSWORD}"
  until psql \
    --host="${DRILL_PRIMARY_HOST}" \
    --username="${POSTGRES_USER}" \
    --dbname=postgres \
    --set=ON_ERROR_STOP=1 \
    --command="SELECT pg_create_physical_replication_slot('${DRILL_SLOT_NAME}') WHERE NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '${DRILL_SLOT_NAME}')"
  do
    sleep 2
  done
  until pg_basebackup \
    --host="${DRILL_PRIMARY_HOST}" \
    --username="${POSTGRES_USER}" \
    --pgdata="${PGDATA}" \
    --wal-method=stream \
    --write-recovery-conf \
    --slot="${DRILL_SLOT_NAME}"
  do
    sleep 2
  done
fi

exec docker-entrypoint.sh postgres
