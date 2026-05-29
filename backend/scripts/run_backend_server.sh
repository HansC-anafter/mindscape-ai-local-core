#!/bin/sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8200}"

python /app/backend/scripts/preflight_db.py

reload_enabled="$(python -c 'from backend.app.core.backend_runtime_mode import should_enable_uvicorn_reload; print("1" if should_enable_uvicorn_reload() else "0")')"
capability_reload_watch_enabled="$(python -c 'from backend.app.core.backend_runtime_mode import should_enable_capability_reload_watch; print("1" if should_enable_capability_reload_watch() else "0")')"

set -- uvicorn backend.app.main:app --host "${HOST}" --port "${PORT}"

if [ "${reload_enabled}" = "1" ]; then
  set -- "$@" --reload

  if [ "${capability_reload_watch_enabled}" = "1" ] && [ -d /app/backend/app/capabilities ]; then
    set -- "$@" --reload-dir /app/backend/app/capabilities
  fi
fi

exec "$@"
