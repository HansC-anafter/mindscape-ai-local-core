#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEST_ID="runtime-secret-$PPID-$$"
NETWORK="mindscape-$TEST_ID"
POSTGRES_CONTAINER="mindscape-$TEST_ID-postgres"
PGBOUNCER_CONTAINER="mindscape-$TEST_ID-pgbouncer"
POSTGRES_IMAGE="${LOCAL_CORE_POSTGRES_IMAGE:-mindscape-ai-local-core-postgres:pg16}"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mindscape-runtime-secret.XXXXXX")"
SECRET_FILE="$TEMP_ROOT/postgres_vector_runtime_password"
OLD_SECRET_FILE="$TEMP_ROOT/postgres_vector_runtime_password.old"
ADMIN_PASSWORD="runtime-secret-test-admin"
RUNTIME_USER="mindscape_vector_runtime"
VECTOR_DB="mindscape_vectors"

cleanup() {
  local residual
  for residual in $(docker ps -aq --filter "name=^/mindscape-$TEST_ID-"); do
    docker rm -f "$residual" >/dev/null 2>&1 || true
  done
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT INT TERM

generate_secret() {
  LC_ALL=C od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
}

write_secret() {
  local value="$1"
  umask 077
  printf '%s' "$value" > "$SECRET_FILE"
  chmod 600 "$SECRET_FILE"
}

wait_for_command() {
  local description="$1"
  local container="$2"
  shift 2
  local attempt
  for attempt in $(seq 1 30); do
    if "$@" >/dev/null 2>&1; then
      return 0
    fi
    if [ "$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || true)" = "exited" ]; then
      printf 'ERROR: %s exited before readiness\n' "$description" >&2
      return 1
    fi
    sleep 1
  done
  printf 'ERROR: timed out waiting for %s\n' "$description" >&2
  return 1
}

run_reconcile() {
  docker run --rm \
    --name "mindscape-$TEST_ID-reconcile" \
    --network "$NETWORK" \
    -e POSTGRES_CORE_USER=mindscape \
    -e POSTGRES_CORE_PASSWORD="$ADMIN_PASSWORD" \
    -e POSTGRES_VECTOR_DB="$VECTOR_DB" \
    -e POSTGRES_VECTOR_RUNTIME_USER="$RUNTIME_USER" \
    -e POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE=/run/secrets/postgres_vector_runtime_password \
    -e POSTGRES_DIRECT_HOST=postgres \
    -v "$SECRET_FILE:/run/secrets/postgres_vector_runtime_password:ro" \
    -v "$REPO_ROOT/docker/postgres/reconcile-vector-runtime-role.sh:/opt/mindscape/reconcile-vector-runtime-role.sh:ro" \
    "$POSTGRES_IMAGE" \
    sh /opt/mindscape/reconcile-vector-runtime-role.sh >/dev/null
}

runtime_probe() {
  local host="$1"
  local port="$2"
  local secret_path="$3"
  printf '%s\n' "$(cat "$secret_path")" \
    | docker exec -i "$POSTGRES_CONTAINER" sh -ec \
      'IFS= read -r runtime_password; PGPASSWORD="$runtime_password" exec psql -v ON_ERROR_STOP=1 -h "$1" -p "$2" -U "$3" -d "$4" -Atc "SELECT 1"' \
      probe "$host" "$port" "$RUNTIME_USER" "$VECTOR_DB" >/dev/null
}

require_runtime_probe() {
  local stage="$1"
  local host="$2"
  local port="$3"
  local secret_path="$4"
  if ! runtime_probe "$host" "$port" "$secret_path"; then
    printf 'ERROR: runtime credential probe failed at stage=%s\n' "$stage" >&2
    return 1
  fi
}

start_pgbouncer() {
  docker run -d \
    --name "$PGBOUNCER_CONTAINER" \
    --network "$NETWORK" \
    --network-alias pgbouncer \
    --user postgres \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=4m \
    --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=1m \
    -e POSTGRES_CORE_USER=mindscape \
    -e POSTGRES_CORE_PASSWORD="$ADMIN_PASSWORD" \
    -e POSTGRES_CORE_DB=mindscape_core \
    -e POSTGRES_VECTOR_DB="$VECTOR_DB" \
    -e POSTGRES_VECTOR_RUNTIME_USER="$RUNTIME_USER" \
    -e POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE=/run/secrets/postgres_vector_runtime_password \
    -v "$SECRET_FILE:/run/secrets/postgres_vector_runtime_password:ro" \
    -v "$REPO_ROOT/docker/pgbouncer/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro" \
    -v "$REPO_ROOT/docker/pgbouncer/start.sh:/opt/mindscape/start-pgbouncer.sh:ro" \
    "$POSTGRES_IMAGE" \
    sh /opt/mindscape/start-pgbouncer.sh >/dev/null
  wait_for_command "PgBouncer" "$PGBOUNCER_CONTAINER" docker exec "$PGBOUNCER_CONTAINER" \
    pg_isready -h 127.0.0.1 -p 6432 -U mindscape -d mindscape_core
}

old_secret="$(generate_secret)"
new_secret="$(generate_secret)"
printf '%s' "$old_secret" > "$OLD_SECRET_FILE"
chmod 600 "$OLD_SECRET_FILE"
write_secret "$old_secret"

docker network create "$NETWORK" >/dev/null
docker run -d \
  --name "$POSTGRES_CONTAINER" \
  --network "$NETWORK" \
  --network-alias postgres \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=256m \
  -e POSTGRES_DB=mindscape_core \
  -e POSTGRES_USER=mindscape \
  -e POSTGRES_PASSWORD="$ADMIN_PASSWORD" \
  -e POSTGRES_CORE_USER=mindscape \
  -e POSTGRES_CORE_PASSWORD="$ADMIN_PASSWORD" \
  -e POSTGRES_CORE_DB=mindscape_core \
  -e POSTGRES_VECTOR_DB="$VECTOR_DB" \
  -e POSTGRES_VECTOR_RUNTIME_USER="$RUNTIME_USER" \
  -e POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE=/run/secrets/postgres_vector_runtime_password \
  -e PGDATA=/var/lib/postgresql/data/pgdata \
  -v "$SECRET_FILE:/run/secrets/postgres_vector_runtime_password:ro" \
  -v "$REPO_ROOT/docker/postgres/init-dual-dbs.sh:/docker-entrypoint-initdb.d/00-init-dual-dbs.sh:ro" \
  -v "$REPO_ROOT/docker/postgres/reconcile-vector-runtime-role.sh:/opt/mindscape/reconcile-vector-runtime-role.sh:ro" \
  "$POSTGRES_IMAGE" >/dev/null

wait_for_command "PostgreSQL" "$POSTGRES_CONTAINER" docker exec "$POSTGRES_CONTAINER" \
  pg_isready -h 127.0.0.1 -U mindscape -d mindscape_core
run_reconcile
require_runtime_probe fresh-direct postgres 5432 "$SECRET_FILE"
start_pgbouncer
require_runtime_probe fresh-pooled pgbouncer 6432 "$SECRET_FILE"

role_hash_before="$(
  docker exec -e PGPASSWORD="$ADMIN_PASSWORD" "$POSTGRES_CONTAINER" \
    psql -U mindscape -d "$VECTOR_DB" -Atc \
    "SELECT rolpassword FROM pg_authid WHERE rolname='$RUNTIME_USER'"
)"
run_reconcile
role_hash_after="$(
  docker exec -e PGPASSWORD="$ADMIN_PASSWORD" "$POSTGRES_CONTAINER" \
    psql -U mindscape -d "$VECTOR_DB" -Atc \
    "SELECT rolpassword FROM pg_authid WHERE rolname='$RUNTIME_USER'"
)"
if [ -z "$role_hash_before" ] || [ "$role_hash_before" != "$role_hash_after" ]; then
  echo "ERROR: idempotent reconcile rewrote the runtime role credential" >&2
  exit 1
fi

write_secret "$new_secret"
run_reconcile
require_runtime_probe upgrade-direct postgres 5432 "$SECRET_FILE"
if runtime_probe postgres 5432 "$OLD_SECRET_FILE" >/dev/null 2>&1; then
  echo "ERROR: old vector runtime password remained valid after reconcile" >&2
  exit 1
fi

docker rm -f "$PGBOUNCER_CONTAINER" >/dev/null
start_pgbouncer
require_runtime_probe upgrade-pooled pgbouncer 6432 "$SECRET_FILE"
if runtime_probe pgbouncer 6432 "$OLD_SECRET_FILE" >/dev/null 2>&1; then
  echo "ERROR: PgBouncer accepted the old vector runtime password" >&2
  exit 1
fi

for container in "$POSTGRES_CONTAINER" "$PGBOUNCER_CONTAINER"; do
  if docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container" \
      | grep -Fq "$new_secret"; then
    echo "ERROR: vector runtime secret leaked into container Config.Env" >&2
    exit 1
  fi
done

role_flags="$(
  docker exec -e PGPASSWORD="$ADMIN_PASSWORD" "$POSTGRES_CONTAINER" \
    psql -U mindscape -d "$VECTOR_DB" -Atc \
    "SELECT concat_ws('|', rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolbypassrls) FROM pg_roles WHERE rolname='$RUNTIME_USER'"
)"
if [ "$role_flags" != "t|f|f|f|f|f" ]; then
  echo "ERROR: vector runtime role flags drifted" >&2
  exit 1
fi

printf '{"validation_passed":true,"fresh":true,"upgrade":true,"idempotent":true,"direct":true,"pooled":true,"old_secret_rejected":true,"config_env_redacted":true,"role_flags":"LOGIN|NOSUPERUSER|NOCREATEDB|NOCREATEROLE|NOINHERIT|NOBYPASSRLS"}\n'
