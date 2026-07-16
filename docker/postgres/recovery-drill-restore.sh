#!/bin/sh
set -eu

test -s /restore/base/PG_VERSION || {
  echo "restore_base_pg_version_missing" >&2
  exit 64
}
test -n "${RECOVERY_TARGET_TIME:-}" || {
  echo "recovery_target_time_required" >&2
  exit 65
}

if [ ! -s "${PGDATA}/PG_VERSION" ]; then
  rm -rf "${PGDATA:?}"/*
  cp -a /restore/base/. "${PGDATA}/"
  rm -f "${PGDATA}/postmaster.pid" "${PGDATA}/standby.signal"
  chmod 0700 "${PGDATA}"
  cat >>"${PGDATA}/postgresql.auto.conf" <<EOF
restore_command = 'cp /restore/wal/%f %p'
recovery_target_time = '${RECOVERY_TARGET_TIME}'
recovery_target_action = 'promote'
recovery_target_timeline = 'latest'
EOF
  touch "${PGDATA}/recovery.signal"
fi

exec docker-entrypoint.sh postgres
