#!/bin/sh
set -eu

secret_file="${POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE:-/run/secrets/postgres_vector_runtime_password}"
runtime_user="${POSTGRES_VECTOR_RUNTIME_USER:-mindscape_vector_runtime}"
vector_db="${POSTGRES_VECTOR_DB:-mindscape_vectors}"
core_user="${POSTGRES_CORE_USER:-mindscape}"
core_password="${POSTGRES_CORE_PASSWORD:-mindscape_password}"
postgres_host="${POSTGRES_DIRECT_HOST:-postgres}"

if [ ! -r "$secret_file" ]; then
  echo "[runtime-secret] vector runtime secret file is unavailable" >&2
  exit 1
fi
runtime_secret=""
IFS= read -r runtime_secret < "$secret_file" || true
secret_file_bytes="$(LC_ALL=C wc -c < "$secret_file")"
secret_value_bytes="$(LC_ALL=C printf '%s' "$runtime_secret" | wc -c)"
secret_final_byte="$(LC_ALL=C tail -c 1 "$secret_file" | od -An -tu1 | tr -d ' ')"
if [ "$secret_file_bytes" -eq "$secret_value_bytes" ]; then
  :
elif [ "$secret_file_bytes" -eq $((secret_value_bytes + 1)) ] && [ "$secret_final_byte" = "10" ]; then
  runtime_secret="${runtime_secret%$(printf '\r')}"
else
  echo "[runtime-secret] vector runtime secret must contain exactly one line" >&2
  exit 1
fi
case "$runtime_secret" in
  *"$(printf '\r')"*)
    echo "[runtime-secret] vector runtime secret is invalid" >&2
    exit 1
    ;;
esac
if [ -z "$runtime_secret" ] || [ "${#runtime_secret}" -gt 4096 ]; then
  echo "[runtime-secret] vector runtime secret is invalid" >&2
  exit 1
fi

export PGPASSWORD="$core_password"
role_state="$(
  psql -v ON_ERROR_STOP=1 -h "$postgres_host" -U "$core_user" -d "$vector_db" \
    --set=runtime_user="$runtime_user" -At <<'SQL'
SELECT concat_ws('|', 1, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolbypassrls)
FROM pg_roles
WHERE rolname = :'runtime_user';
SQL
)"

password_valid=0
if [ "$role_state" = "1|t|f|f|f|f|f" ]; then
  if PGPASSWORD="$runtime_secret" psql -v ON_ERROR_STOP=1 -h "$postgres_host" \
      -U "$runtime_user" -d "$vector_db" -Atc "SELECT 1" >/dev/null 2>&1; then
    password_valid=1
  fi
fi

if [ "$password_valid" -eq 1 ]; then
  echo "[runtime-secret] vector runtime role already converged"
  exit 0
fi

export POSTGRES_VECTOR_RUNTIME_PASSWORD="$runtime_secret"
export POSTGRES_VECTOR_RUNTIME_USER="$runtime_user"
psql -v ON_ERROR_STOP=1 -h "$postgres_host" -U "$core_user" -d "$vector_db" <<'SQL'
\getenv runtime_user POSTGRES_VECTOR_RUNTIME_USER
\getenv runtime_secret POSTGRES_VECTOR_RUNTIME_PASSWORD
SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
    :'runtime_user',
    :'runtime_secret'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime_user')
\gexec
SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
    :'runtime_user',
    :'runtime_secret'
)
\gexec
SQL
unset POSTGRES_VECTOR_RUNTIME_PASSWORD

if ! PGPASSWORD="$runtime_secret" psql -v ON_ERROR_STOP=1 -h "$postgres_host" \
    -U "$runtime_user" -d "$vector_db" -Atc "SELECT 1" >/dev/null 2>&1; then
  echo "[runtime-secret] vector runtime role verification failed" >&2
  exit 1
fi
echo "[runtime-secret] vector runtime role reconciled"
