#!/bin/bash

set -euo pipefail

API_URL="${API_URL:-http://localhost:8200}"
CONTAINER_API_URL="${CONTAINER_API_URL:-http://127.0.0.1:8200}"
API_TRANSPORT="${API_TRANSPORT:-auto}"
BACKEND_CONTAINER_NAME="${BACKEND_CONTAINER_NAME:-mindscape-ai-local-core-backend}"
CAPABILITY_CODE="performance_direction"
EXPECTED_UI_COMPONENT="PerformanceDirectionStoryboardEditorPage"
WORKSPACE_ID="${WORKSPACE_ID:-ws_pd_pack_smoke_$(date +%Y%m%d_%H%M%S)}"
EXPECTED_INVALID_DETAIL="invalid_scene_subject_adapter_contract:slot_requires_subject_scope:identity_face:subj_a_face"
CURL_MAX_TIME="${CURL_MAX_TIME:-15}"
REQUEST_RETRY_ATTEMPTS="${REQUEST_RETRY_ATTEMPTS:-4}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pd_pack_smoke.XXXXXX")"
REQUEST_STATUS=""

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
  local attempt=1
  local max_attempts="${REQUEST_RETRY_ATTEMPTS}"
  local curl_exit=1
  local raw_file="${TMP_DIR}/response.raw"
  local container_url="${url/${API_URL}/${CONTAINER_API_URL}}"

  REQUEST_STATUS=""

  while [ "${attempt}" -le "${max_attempts}" ]; do
    if [ "${API_TRANSPORT}" = "host" ] || [ "${API_TRANSPORT}" = "auto" ]; then
      if [ -n "${payload}" ]; then
        if curl -sS --max-time "${CURL_MAX_TIME}" --include -X "${method}" "${url}" -H 'Content-Type: application/json' -d "${payload}" > "${raw_file}"; then
          REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
          return 0
        else
          curl_exit=$?
        fi
      else
        if curl -sS --max-time "${CURL_MAX_TIME}" --include -X "${method}" "${url}" > "${raw_file}"; then
          REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
          return 0
        else
          curl_exit=$?
        fi
      fi
    fi

    if [ "${API_TRANSPORT}" = "container" ] || [ "${API_TRANSPORT}" = "auto" ]; then
      if [ -n "${payload}" ]; then
        if docker exec "${BACKEND_CONTAINER_NAME}" curl -sS --max-time "${CURL_MAX_TIME}" --include -X "${method}" "${container_url}" -H 'Content-Type: application/json' -d "${payload}" > "${raw_file}"; then
          REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
          return 0
        else
          curl_exit=$?
        fi
      else
        if docker exec "${BACKEND_CONTAINER_NAME}" curl -sS --max-time "${CURL_MAX_TIME}" --include -X "${method}" "${container_url}" > "${raw_file}"; then
          REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
          return 0
        else
          curl_exit=$?
        fi
      fi
    fi
    sleep 2
    attempt=$((attempt + 1))
  done

  return "${curl_exit}"
}

wait_for_health() {
  local health_file="${TMP_DIR}/health.json"
  local attempt=1
  local max_attempts=120

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

extract_json_value() {
  local file_path="$1"
  local expression="$2"

  python3 - "${file_path}" "${expression}" <<'PY'
import json
import sys

file_path = sys.argv[1]
expression = sys.argv[2]

with open(file_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)

value = eval(expression, {"__builtins__": {}}, {"data": data})
if value is None:
    raise SystemExit(1)
print(value)
PY
}

log "Performance Direction pack smoke"
log "API_URL=${API_URL}"
log "WORKSPACE_ID=${WORKSPACE_ID}"
log ""

log "1. Waiting for backend health"
wait_for_health
log "   backend healthy"

pack_file="${TMP_DIR}/pack.json"
log "2. Verifying installed pack registry"
request_json GET "${API_URL}/api/v1/capability-packs/" "" "${pack_file}"
pack_status="${REQUEST_STATUS}"
[ "${pack_status}" = "200" ] || fail "capability pack registry returned HTTP ${pack_status}"
assert_json_predicate "${pack_file}" "performance_direction pack not found or not installed" "any(row.get('id') == '${CAPABILITY_CODE}' and row.get('installed') is True for row in data)"
log "   pack registered and installed"

ui_file="${TMP_DIR}/ui_components.json"
log "3. Verifying installed UI metadata"
request_json GET "${API_URL}/api/v1/capability-packs/installed-capabilities/${CAPABILITY_CODE}/ui-components" "" "${ui_file}"
ui_status="${REQUEST_STATUS}"
[ "${ui_status}" = "200" ] || fail "ui-components endpoint returned HTTP ${ui_status}"
assert_json_predicate "${ui_file}" "expected UI component not registered" "any(component.get('code') == '${EXPECTED_UI_COMPONENT}' for component in data)"
log "   ui component metadata present"

session_file="${TMP_DIR}/session.json"
session_payload=$(printf '{"workspace_id":"%s","intent":{"goal":"performance_direction installed pack smoke"},"cast":[],"reference_ids":[]}' "${WORKSPACE_ID}")
log "4. Creating direction session"
request_json POST "${API_URL}/api/v1/capabilities/${CAPABILITY_CODE}/sessions" "${session_payload}" "${session_file}"
session_status="${REQUEST_STATUS}"
[ "${session_status}" = "200" ] || fail "session create returned HTTP ${session_status}"
session_id=$(extract_json_value "${session_file}" "data['session']['session_id']")
log "   session_id=${session_id}"

valid_storyboard_file="${TMP_DIR}/valid_storyboard.json"
valid_storyboard_payload=$(printf '{"workspace_id":"%s","source_type":"generative","scene_specs":[{"scene_id":"sc01","shot_prompt":"single subject test frame","framing":"medium"}]}' "${WORKSPACE_ID}")
log "5. Generating minimal valid storyboard"
request_json POST "${API_URL}/api/v1/capabilities/${CAPABILITY_CODE}/sessions/${session_id}/storyboard" "${valid_storyboard_payload}" "${valid_storyboard_file}"
valid_storyboard_status="${REQUEST_STATUS}"
[ "${valid_storyboard_status}" = "200" ] || fail "valid storyboard generation returned HTTP ${valid_storyboard_status}"
artifact_id=$(extract_json_value "${valid_storyboard_file}" "data['artifact']['artifact_id']")
log "   artifact_id=${artifact_id}"

invalid_generate_file="${TMP_DIR}/invalid_generate.json"
invalid_generate_payload=$(printf '{"workspace_id":"%s","source_type":"generative","scene_specs":[{"scene_id":"sc_invalid_generate","shot_prompt":"invalid contract"}],"scene_subjects":[{"subject_id":"subj_a","cast_id":"cast_a","role_id":"lead"}],"character_adapter_slots":[{"slot_id":"subj_a_face","slot_role":"identity_face","scope_kind":"scene","subject_id":""}]}' "${WORKSPACE_ID}")
log "6. Verifying invalid generate request returns 422"
request_json POST "${API_URL}/api/v1/capabilities/${CAPABILITY_CODE}/sessions/${session_id}/storyboard" "${invalid_generate_payload}" "${invalid_generate_file}"
invalid_generate_status="${REQUEST_STATUS}"
[ "${invalid_generate_status}" = "422" ] || fail "invalid generate request returned HTTP ${invalid_generate_status}, expected 422"
assert_json_predicate "${invalid_generate_file}" "invalid generate detail mismatch" "data.get('detail') == '${EXPECTED_INVALID_DETAIL}'"
log "   invalid generate returned expected 422"

invalid_patch_file="${TMP_DIR}/invalid_patch.json"
invalid_patch_payload=$(printf '{"scene_id":"sc01","artifact_id":"%s","storyboard_scene_patch":{"scene_subjects":[{"subject_id":"subj_a","cast_id":"cast_a","role_id":"lead"}],"character_adapter_slots":[{"slot_id":"subj_a_face","slot_role":"identity_face","scope_kind":"scene","subject_id":""}]}}' "${artifact_id}")
log "7. Verifying invalid scene-patch returns 422"
request_json POST "${API_URL}/api/v1/capabilities/${CAPABILITY_CODE}/sessions/${session_id}/storyboard/scene-patch" "${invalid_patch_payload}" "${invalid_patch_file}"
invalid_patch_status="${REQUEST_STATUS}"
[ "${invalid_patch_status}" = "422" ] || fail "invalid scene-patch returned HTTP ${invalid_patch_status}, expected 422"
assert_json_predicate "${invalid_patch_file}" "invalid scene-patch detail mismatch" "data.get('detail') == '${EXPECTED_INVALID_DETAIL}'"
log "   invalid scene-patch returned expected 422"

wait_for_health
log "8. Final health check passed"
log ""
log "Performance Direction pack smoke passed"
