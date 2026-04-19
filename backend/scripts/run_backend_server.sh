#!/bin/sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8200}"

python /app/backend/scripts/preflight_db.py

reload_enabled="$(python -c 'from backend.app.core.backend_runtime_mode import should_enable_uvicorn_reload; print("1" if should_enable_uvicorn_reload() else "0")')"

set -- uvicorn backend.app.main:app --host "${HOST}" --port "${PORT}"

if [ "${reload_enabled}" = "1" ]; then
  set -- "$@" --reload

  if [ -d /app/backend/app/capabilities ]; then
    set -- "$@" --reload-dir /app/backend/app/capabilities
  fi
  if [ -d /mindscape-ai-cloud/capabilities ]; then
    set -- "$@" --reload-dir /mindscape-ai-cloud/capabilities
  fi
fi

exec "$@"
