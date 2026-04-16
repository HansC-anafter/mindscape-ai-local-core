#!/bin/bash

set -euo pipefail

API_URL="${API_URL:-http://localhost:8200}"
CONTAINER_API_URL="${CONTAINER_API_URL:-http://127.0.0.1:8200}"
API_TRANSPORT="${API_TRANSPORT:-container}"
BACKEND_CONTAINER_NAME="${BACKEND_CONTAINER_NAME:-mindscape-ai-local-core-backend}"
COMFY_HOST_URL="${COMFY_HOST_URL:-http://127.0.0.1:8188}"
COMFY_STABILITY_WAIT_SECONDS="${COMFY_STABILITY_WAIT_SECONDS:-8}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/comfyui_runtime_smoke.XXXXXX")"
REQUEST_STATUS=""

INSTALLED_BOOTSTRAP_SCRIPT="/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/comfyui_runtime/scripts/bootstrap_local_comfyui_preview.sh"
INSTALLED_REGIONAL_READINESS_SCRIPT="/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/comfyui_runtime/scripts/check_local_comfyui_regional_adapter_readiness.sh"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

log() {
  printf '%s\n' "$1"
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

parse_raw_response() {
  local raw_file="$1"
  local output_file="$2"

  python3 - "${raw_file}" "${output_file}" <<'PY'
import re
import sys

raw_path = sys.argv[1]
body_path = sys.argv[2]

raw = open(raw_path, "rb").read()
parts = re.split(br"\r?\n\r?\n", raw)
status_code = "000"
body = b""

if parts:
    body = parts[-1]
    for chunk in parts[:-1]:
        lines = chunk.splitlines()
        first_line = lines[0] if lines else b""
        if first_line.startswith(b"HTTP/"):
            fields = first_line.split()
            if len(fields) >= 2:
                status_code = fields[1].decode("utf-8", "replace")

with open(body_path, "wb") as handle:
    handle.write(body)

print(status_code, end="")
PY
}

request_json() {
  local method="$1"
  local url="$2"
  local payload="${3:-}"
  local output_file="$4"
  local raw_file="${TMP_DIR}/response.raw"
  local container_url="${url/${API_URL}/${CONTAINER_API_URL}}"

  REQUEST_STATUS=""

  if [ "${API_TRANSPORT}" = "host" ] || [ "${API_TRANSPORT}" = "auto" ]; then
    if [ -n "${payload}" ]; then
      if curl -sS --max-time 20 --include -X "${method}" "${url}" -H 'Content-Type: application/json' -d "${payload}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
        return 0
      fi
    else
      if curl -sS --max-time 20 --include -X "${method}" "${url}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
        return 0
      fi
    fi
  fi

  if [ "${API_TRANSPORT}" = "container" ] || [ "${API_TRANSPORT}" = "auto" ]; then
    if [ -n "${payload}" ]; then
      if docker exec "${BACKEND_CONTAINER_NAME}" curl -sS --max-time 20 --include -X "${method}" "${container_url}" -H 'Content-Type: application/json' -d "${payload}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
        return 0
      fi
    else
      if docker exec "${BACKEND_CONTAINER_NAME}" curl -sS --max-time 20 --include -X "${method}" "${container_url}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
        return 0
      fi
    fi
  fi

  return 1
}

wait_for_backend_health() {
  local health_file="${TMP_DIR}/health.json"
  local attempt=1
  local max_attempts=60

  while [ "${attempt}" -le "${max_attempts}" ]; do
    if request_json GET "${API_URL}/health" "" "${health_file}" 2>/dev/null && [ "${REQUEST_STATUS}" = "200" ] && [ -s "${health_file}" ]; then
      if python3 - "${health_file}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

sys.exit(0 if payload.get("status") == "healthy" else 1)
PY
      then
        return 0
      fi
    fi
    sleep 2
    attempt=$((attempt + 1))
  done

  fail "backend did not become healthy at ${API_URL}/health"
}

assert_json_predicate() {
  local file_path="$1"
  local error_message="$2"
  local predicate="$3"

  if ! python3 - "${file_path}" "${predicate}" <<'PY'
import json
import sys

file_path = sys.argv[1]
predicate = sys.argv[2]

with open(file_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)

scope = {"data": data}
safe_builtins = {"any": any, "all": all, "len": len}
if not eval(predicate, {"__builtins__": safe_builtins}, scope):
    raise SystemExit(1)
PY
  then
    fail "${error_message}"
  fi
}

probe_system_stats() {
  local output_file="$1"
  curl -sS --max-time 20 "${COMFY_HOST_URL}/system_stats" > "${output_file}"
  python3 - "${output_file}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

system = payload.get("system") or {}
devices = payload.get("devices") or []
if not system or not isinstance(devices, list):
    raise SystemExit(1)
print(system.get("comfyui_version") or "unknown", end="")
PY
}

log "ComfyUI runtime smoke"
log "API_URL=${API_URL}"
log "API_TRANSPORT=${API_TRANSPORT}"
log "COMFY_HOST_URL=${COMFY_HOST_URL}"
log ""

log "1. Waiting for backend health"
wait_for_backend_health
log "   backend healthy"

[ -f "${INSTALLED_BOOTSTRAP_SCRIPT}" ] || fail "installed bootstrap script not found: ${INSTALLED_BOOTSTRAP_SCRIPT}"
[ -f "${INSTALLED_REGIONAL_READINESS_SCRIPT}" ] || fail "installed regional readiness script not found: ${INSTALLED_REGIONAL_READINESS_SCRIPT}"

log "2. Restarting installed ComfyUI preview runtime"
bash "${INSTALLED_BOOTSTRAP_SCRIPT}" restart > "${TMP_DIR}/bootstrap.log" 2>&1 || {
  cat "${TMP_DIR}/bootstrap.log" >&2
  fail "installed bootstrap restart failed"
}
grep -q "healthy:" "${TMP_DIR}/bootstrap.log" || fail "bootstrap restart did not report a healthy ComfyUI endpoint"
log "   restart completed"

log "3. Probing host ComfyUI system_stats twice"
first_version="$(probe_system_stats "${TMP_DIR}/system_stats_first.json")" || fail "first system_stats probe failed"
sleep "${COMFY_STABILITY_WAIT_SECONDS}"
second_version="$(probe_system_stats "${TMP_DIR}/system_stats_second.json")" || fail "second system_stats probe failed"
[ -n "${first_version}" ] || fail "first system_stats probe returned no ComfyUI version"
[ -n "${second_version}" ] || fail "second system_stats probe returned no ComfyUI version"
log "   system_stats stable (${first_version} -> ${second_version})"

log "4. Verifying installed regional readiness"
bash "${INSTALLED_REGIONAL_READINESS_SCRIPT}" --json > "${TMP_DIR}/regional_readiness.json" || true
assert_json_predicate "${TMP_DIR}/regional_readiness.json" "regional readiness did not report ready" "data.get('ready') is True"
assert_json_predicate "${TMP_DIR}/regional_readiness.json" "regional readiness did not report repo contract ready" "data.get('repo_contract_ready') is True"
assert_json_predicate "${TMP_DIR}/regional_readiness.json" "regional readiness still reports missing runtime features" "not data.get('missing_runtime_features')"
assert_json_predicate "${TMP_DIR}/regional_readiness.json" "regional readiness still reports missing model files" "not data.get('missing_model_files')"
log "   regional readiness ready"

log "5. Verifying runtime-health API contract"
request_json GET "${API_URL}/api/v1/capabilities/comfyui_runtime/workbench/runtime-health" "" "${TMP_DIR}/runtime_health.json"
[ "${REQUEST_STATUS}" = "200" ] || fail "runtime-health returned HTTP ${REQUEST_STATUS:-000}"
assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health did not report live_health_state=ok" "data.get('live_health_state') == 'ok'"
assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health did not report dispatch_state=ready" "data.get('dispatch_state') == 'ready'"
assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health did not report multi_subject_preview ready" "((data.get('recommended_for') or {}).get('multi_subject_preview') == 'ready')"
assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health did not report regional_multi_subject_preview ready" "((data.get('lane_verdicts') or {}).get('regional_multi_subject_preview') == 'ready')"
assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health still returned active failures" "not data.get('active_failures')"
assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime_ref unexpectedly includes runtime_snapshot" "'runtime_snapshot' not in ((data.get('runtime_ref') or {}))"
log "   runtime-health ready"

log ""
log "Smoke passed"
