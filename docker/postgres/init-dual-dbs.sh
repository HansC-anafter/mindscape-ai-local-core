#!/usr/bin/env bash
set -euo pipefail

core_db="${POSTGRES_CORE_DB:-mindscape_core}"
vector_db="${POSTGRES_VECTOR_DB:-mindscape_vectors}"
vector_runtime_user="${POSTGRES_VECTOR_RUNTIME_USER:-mindscape_vector_runtime}"
vector_runtime_secret="${POSTGRES_VECTOR_RUNTIME_PASSWORD:?POSTGRES_VECTOR_RUNTIME_PASSWORD is required}"

if [ "${core_db}" != "${vector_db}" ]; then
  exists="$(psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${core_db}" -tAc "SELECT 1 FROM pg_database WHERE datname='${vector_db}'")"
  if [ "${exists}" != "1" ]; then
    psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${core_db}" -c "CREATE DATABASE \"${vector_db}\";"
  fi
fi

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${vector_db}" -c "CREATE EXTENSION IF NOT EXISTS vector;"

psql \
  -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${vector_db}" \
  --set=runtime_user="${vector_runtime_user}" \
  --set=runtime_secret="${vector_runtime_secret}" <<'SQL'
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
