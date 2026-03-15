#!/usr/bin/env bash
set -euo pipefail

core_db="${POSTGRES_CORE_DB:-mindscape_core}"
vector_db="${POSTGRES_VECTOR_DB:-mindscape_vectors}"

if [ "${core_db}" != "${vector_db}" ]; then
  exists="$(psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${core_db}" -tAc "SELECT 1 FROM pg_database WHERE datname='${vector_db}'")"
  if [ "${exists}" != "1" ]; then
    psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${core_db}" -c "CREATE DATABASE \"${vector_db}\";"
  fi
fi

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${vector_db}" -c "CREATE EXTENSION IF NOT EXISTS vector;"
