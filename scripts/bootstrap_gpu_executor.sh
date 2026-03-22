#!/bin/bash
# Bootstrap a headless GPU executor node after docker compose startup.
# Phase A installs only the minimum required pack set and verifies tool exposure.

set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:${GPU_EXECUTOR_PORT:-8200}}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-180}"
WAIT_INTERVAL_SECONDS="${WAIT_INTERVAL_SECONDS:-3}"
ALLOW_OVERWRITE="${ALLOW_OVERWRITE:-true}"
REQUIRED_TOOL="${REQUIRED_TOOL:-core_llm.multimodal_analyze}"

usage() {
  cat <<'EOF'
Usage:
  bootstrap_gpu_executor.sh /path/to/core_llm.mindpack [more.mindpack ...]

Environment overrides:
  API_URL                  Backend API base URL. Default: http://127.0.0.1:8200
  WAIT_TIMEOUT_SECONDS     Health wait timeout. Default: 180
  WAIT_INTERVAL_SECONDS    Health poll interval. Default: 3
  ALLOW_OVERWRITE          install-from-file overwrite flag. Default: true
  REQUIRED_TOOL            Tool that must exist after bootstrap.
  PACK_FILES               Space-separated alternative to positional arguments.
EOF
}

log() {
  printf '[gpu-executor-bootstrap] %s\n' "$*"
}

wait_for_health() {
  local deadline
  deadline=$(( $(date +%s) + WAIT_TIMEOUT_SECONDS ))

  while [ "$(date +%s)" -lt "${deadline}" ]; do
    if curl -fsS "${API_URL}/health" >/dev/null 2>&1; then
      log "Backend health check passed at ${API_URL}"
      return 0
    fi
    sleep "${WAIT_INTERVAL_SECONDS}"
  done

  log "Backend did not become healthy within ${WAIT_TIMEOUT_SECONDS}s"
  return 1
}

install_pack() {
  local pack_path="$1"
  local response

  if [ ! -f "${pack_path}" ]; then
    log "Pack file not found: ${pack_path}"
    return 1
  fi

  log "Installing pack: ${pack_path}"
  response="$(curl -fsS -X POST "${API_URL}/api/v1/capability-packs/install-from-file" \
    -F "file=@${pack_path}" \
    -F "allow_overwrite=${ALLOW_OVERWRITE}")"

  RESPONSE_JSON="${response}" python3 - "${pack_path}" <<'PY'
import json
import os
import sys

pack_path = sys.argv[1]
raw = os.environ.get("RESPONSE_JSON", "")
data = json.loads(raw)
if not data.get("success"):
    raise SystemExit(f"install failed for {pack_path}: {raw}")
print(f"installed {pack_path}: capability={data.get('capability_code')} version={data.get('version')}")
PY
}

verify_tool() {
  local response
  response="$(curl -fsS "${API_URL}/api/v1/tools/")"

  RESPONSE_JSON="${response}" REQUIRED_TOOL="${REQUIRED_TOOL}" python3 - <<'PY'
import json
import os

required = os.environ["REQUIRED_TOOL"]
raw = os.environ.get("RESPONSE_JSON", "[]")
tools = json.loads(raw)

def tool_id(item):
    if isinstance(item, dict):
        return item.get("tool_id") or item.get("id") or item.get("origin_capability_id")
    return None

for item in tools:
    if tool_id(item) == required:
        print(f"verified tool: {required}")
        raise SystemExit(0)

raise SystemExit(f"required tool not found: {required}")
PY
}

main() {
  local -a packs=()

  if [ "$#" -gt 0 ]; then
    packs=("$@")
  elif [ -n "${PACK_FILES:-}" ]; then
    # shellcheck disable=SC2206
    packs=(${PACK_FILES})
  else
    usage
    exit 1
  fi

  wait_for_health

  local pack
  for pack in "${packs[@]}"; do
    install_pack "${pack}"
  done

  verify_tool
  log "GPU executor bootstrap completed successfully"
}

main "$@"
