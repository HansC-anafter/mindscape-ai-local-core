#!/usr/bin/env bash
set -euo pipefail

core_db="${POSTGRES_CORE_DB:-mindscape_core}"
vector_db="${POSTGRES_VECTOR_DB:-mindscape_vectors}"
vector_runtime_user="${POSTGRES_VECTOR_RUNTIME_USER:-mindscape_vector_runtime}"
vector_runtime_secret_file="${POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE:-/run/secrets/postgres_vector_runtime_password}"
if [ -r "${vector_runtime_secret_file}" ]; then
  vector_runtime_secret=""
  IFS= read -r vector_runtime_secret < "${vector_runtime_secret_file}" || true
  secret_file_bytes="$(LC_ALL=C wc -c < "${vector_runtime_secret_file}")"
  secret_value_bytes="$(LC_ALL=C printf '%s' "${vector_runtime_secret}" | wc -c)"
  secret_final_byte="$(LC_ALL=C tail -c 1 "${vector_runtime_secret_file}" | od -An -tu1 | tr -d ' ')"
  if [ "${secret_file_bytes}" -eq "${secret_value_bytes}" ]; then
    :
  elif [ "${secret_file_bytes}" -eq $((secret_value_bytes + 1)) ] && [ "${secret_final_byte}" = "10" ]; then
    vector_runtime_secret="${vector_runtime_secret%$'\r'}"
  else
    echo "[runtime-secret] vector runtime secret must contain exactly one line" >&2
    exit 1
  fi
else
  vector_runtime_secret="${POSTGRES_VECTOR_RUNTIME_PASSWORD:?POSTGRES_VECTOR_RUNTIME_PASSWORD_FILE is required}"
fi
if [ -z "${vector_runtime_secret}" ] || [ "${#vector_runtime_secret}" -gt 4096 ] ||
    [[ "${vector_runtime_secret}" == *$'\r'* || "${vector_runtime_secret}" == *$'\n'* ]]; then
  echo "[runtime-secret] vector runtime secret is invalid" >&2
  exit 1
fi

if [ "${core_db}" != "${vector_db}" ]; then
  exists="$(psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${core_db}" -tAc "SELECT 1 FROM pg_database WHERE datname='${vector_db}'")"
  if [ "${exists}" != "1" ]; then
    psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${core_db}" -c "CREATE DATABASE \"${vector_db}\";"
  fi
fi

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${vector_db}" -c "CREATE EXTENSION IF NOT EXISTS vector;"

export POSTGRES_VECTOR_RUNTIME_PASSWORD="${vector_runtime_secret}"
psql \
  -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${vector_db}" \
  --set=runtime_user="${vector_runtime_user}" <<'SQL'
\getenv runtime_secret POSTGRES_VECTOR_RUNTIME_PASSWORD
SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
    :'runtime_user',
    :'runtime_secret'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'runtime_user'
)
\gexec
SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
    :'runtime_user',
    :'runtime_secret'
)
\gexec
SQL
unset POSTGRES_VECTOR_RUNTIME_PASSWORD
