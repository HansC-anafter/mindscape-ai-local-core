#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

exec "${PYTHON:-python3}" -m backend.app.services.host_runtime_sessions.bridge_client "$@"
