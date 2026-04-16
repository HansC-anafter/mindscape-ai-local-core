#!/bin/bash

set -euo pipefail

API_URL="${API_URL:-http://localhost:8200}"
CONTAINER_API_URL="${CONTAINER_API_URL:-http://127.0.0.1:8200}"
API_TRANSPORT="${API_TRANSPORT:-container}"
BACKEND_CONTAINER_NAME="${BACKEND_CONTAINER_NAME:-mindscape-ai-local-core-backend}"
COMFY_HOST_URL="${COMFY_HOST_URL:-http://127.0.0.1:8188}"
COMFY_CONTAINER_URL="${COMFY_CONTAINER_URL:-http://host.docker.internal:8188}"
COMFY_OUTPUT_DIR="${COMFY_OUTPUT_DIR:-/Volumes/OWC Ultra 4T/comfyui/output}"
STAGED_ASSET_DIR="${STAGED_ASSET_DIR:-/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/.tmp/regional_live_preview_assets}"
SCENE_REFERENCE_SOURCE="${SCENE_REFERENCE_SOURCE:-/Volumes/OWC Ultra 4T/comfyui/output/mindscape_regional_multi_subject_preview_00001_.png}"
SUBJECT_A_REFERENCE_SOURCE="${SUBJECT_A_REFERENCE_SOURCE:-/Volumes/OWC Ultra 4T/comfyui/input/mindscape_facecard_ref_ae997ac8_00001_.png}"
SUBJECT_B_REFERENCE_SOURCE="${SUBJECT_B_REFERENCE_SOURCE:-/Volumes/OWC Ultra 4T/comfyui/input/mindscape_facecard_ref_ae997ac8_00002_.png}"
SUBJECT_A_MASK_SOURCE="${SUBJECT_A_MASK_SOURCE:-/Volumes/OWC Ultra 4T/comfyui/input/subj_a_mask.png}"
SUBJECT_B_MASK_SOURCE="${SUBJECT_B_MASK_SOURCE:-/Volumes/OWC Ultra 4T/comfyui/input/subj_b_mask.png}"
WORKSPACE_ID="${WORKSPACE_ID:-ws_regional_live_preview_$(date +%Y%m%d_%H%M%S)}"
PROMPT_TEXT="${PROMPT_TEXT:-two-subject editorial portrait, clean studio composition, balanced framing}"
OUTPUT_PREFIX="${OUTPUT_PREFIX:-mindscape_regional_multi_subject_preview}"
WIDTH="${WIDTH:-512}"
HEIGHT="${HEIGHT:-512}"
STEPS="${STEPS:-4}"
CFG="${CFG:-2}"
HISTORY_MAX_ATTEMPTS="${HISTORY_MAX_ATTEMPTS:-120}"
HISTORY_POLL_SECONDS="${HISTORY_POLL_SECONDS:-2}"
CURL_MAX_TIME="${CURL_MAX_TIME:-240}"
HEALTH_CURL_MAX_TIME="${HEALTH_CURL_MAX_TIME:-10}"
RUNTIME_CURL_MAX_TIME="${RUNTIME_CURL_MAX_TIME:-20}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/regional_live_preview.XXXXXX")"
REQUEST_STATUS=""

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

log() {
  printf '%s\n' "$1"
}

warn() {
  printf 'WARN: %s\n' "$1" >&2
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
  local curl_max_time="${5:-${CURL_MAX_TIME}}"
  local raw_file="${TMP_DIR}/response.raw"
  local container_url="${url/${API_URL}/${CONTAINER_API_URL}}"

  REQUEST_STATUS=""

  if [ "${API_TRANSPORT}" = "host" ] || [ "${API_TRANSPORT}" = "auto" ]; then
    if [ -n "${payload}" ]; then
      if curl -sS --max-time "${curl_max_time}" --include -X "${method}" "${url}" -H 'Content-Type: application/json' -d "${payload}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
        return 0
      fi
    else
      if curl -sS --max-time "${curl_max_time}" --include -X "${method}" "${url}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
        return 0
      fi
    fi
  fi

  if [ "${API_TRANSPORT}" = "container" ] || [ "${API_TRANSPORT}" = "auto" ]; then
    if [ -n "${payload}" ]; then
      if docker exec "${BACKEND_CONTAINER_NAME}" curl -sS --max-time "${curl_max_time}" --include -X "${method}" "${container_url}" -H 'Content-Type: application/json' -d "${payload}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
        return 0
      fi
    else
      if docker exec "${BACKEND_CONTAINER_NAME}" curl -sS --max-time "${curl_max_time}" --include -X "${method}" "${container_url}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response "${raw_file}" "${output_file}")"
        return 0
      fi
    fi
  fi

  return 1
}

request_comfy_json() {
  local path="$1"
  local output_file="$2"

  if curl -fsS --max-time 30 "${COMFY_HOST_URL}${path}" > "${output_file}"; then
    return 0
  fi

  docker exec "${BACKEND_CONTAINER_NAME}" curl -fsS --max-time 30 "${COMFY_CONTAINER_URL}${path}" > "${output_file}"
}

wait_for_backend_health() {
  local health_file="${TMP_DIR}/backend_health.json"
  local attempt=1
  local max_attempts=60

  while [ "${attempt}" -le "${max_attempts}" ]; do
    if request_json GET "${API_URL}/health" "" "${health_file}" "${HEALTH_CURL_MAX_TIME}" 2>/dev/null && [ "${REQUEST_STATUS}" = "200" ] && [ -s "${health_file}" ]; then
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
safe_builtins = {"any": any, "all": all, "len": len, "sorted": sorted}
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

stage_assets() {
  mkdir -p "${STAGED_ASSET_DIR}"

  [ -f "${SCENE_REFERENCE_SOURCE}" ] || fail "scene reference source not found: ${SCENE_REFERENCE_SOURCE}"
  [ -f "${SUBJECT_A_REFERENCE_SOURCE}" ] || fail "subject A reference source not found: ${SUBJECT_A_REFERENCE_SOURCE}"
  [ -f "${SUBJECT_B_REFERENCE_SOURCE}" ] || fail "subject B reference source not found: ${SUBJECT_B_REFERENCE_SOURCE}"
  [ -f "${SUBJECT_A_MASK_SOURCE}" ] || fail "subject A mask source not found: ${SUBJECT_A_MASK_SOURCE}"
  [ -f "${SUBJECT_B_MASK_SOURCE}" ] || fail "subject B mask source not found: ${SUBJECT_B_MASK_SOURCE}"

  cp "${SCENE_REFERENCE_SOURCE}" "${STAGED_ASSET_DIR}/scene_reference.png"
  cp "${SUBJECT_A_REFERENCE_SOURCE}" "${STAGED_ASSET_DIR}/subj_a_ref.png"
  cp "${SUBJECT_B_REFERENCE_SOURCE}" "${STAGED_ASSET_DIR}/subj_b_ref.png"
  cp "${SUBJECT_A_MASK_SOURCE}" "${STAGED_ASSET_DIR}/subj_a_mask.png"
  cp "${SUBJECT_B_MASK_SOURCE}" "${STAGED_ASSET_DIR}/subj_b_mask.png"
}

wait_for_history_completion() {
  local prompt_id="$1"
  local history_file="$2"
  local attempt=1

  while [ "${attempt}" -le "${HISTORY_MAX_ATTEMPTS}" ]; do
    request_comfy_json "/history/${prompt_id}" "${history_file}" || true

    if python3 - "${history_file}" "${prompt_id}" <<'PY'
import json
import sys

history_path = sys.argv[1]
prompt_id = sys.argv[2]

with open(history_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)

entry = data.get(prompt_id) or {}
status = entry.get("status") or {}
outputs = entry.get("outputs") or {}

if status.get("status_str") == "success" and status.get("completed") is True and outputs:
    raise SystemExit(0)

if status.get("status_str") in {"error", "failed"}:
    raise SystemExit(2)

raise SystemExit(1)
PY
    then
      return 0
    else
      history_status=$?
      if [ "${history_status}" = "2" ]; then
        fail "ComfyUI history reports failed execution for prompt_id=${prompt_id}"
      fi
    fi

    sleep "${HISTORY_POLL_SECONDS}"
    attempt=$((attempt + 1))
  done

  fail "ComfyUI history did not complete for prompt_id=${prompt_id}"
}

extract_history_output_path() {
  local history_file="$1"
  local prompt_id="$2"

  python3 - "${history_file}" "${prompt_id}" "${COMFY_OUTPUT_DIR}" <<'PY'
import json
import os
import sys

history_path = sys.argv[1]
prompt_id = sys.argv[2]
output_root = sys.argv[3]

with open(history_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)

entry = data.get(prompt_id) or {}
outputs = entry.get("outputs") or {}

for node_output in outputs.values():
    images = node_output.get("images") or []
    for image in images:
        filename = str(image.get("filename") or "").strip()
        if not filename:
            continue
        subfolder = str(image.get("subfolder") or "").strip()
        full_path = os.path.join(output_root, subfolder, filename) if subfolder else os.path.join(output_root, filename)
        print(full_path)
        raise SystemExit(0)

raise SystemExit(1)
PY
}

log "Regional multi-subject live preview smoke"
log "API_URL=${API_URL}"
log "API_TRANSPORT=${API_TRANSPORT}"
log "COMFY_HOST_URL=${COMFY_HOST_URL}"
log "WORKSPACE_ID=${WORKSPACE_ID}"
log ""

log "1. Waiting for backend health"
wait_for_backend_health
log "   backend healthy"

log "2. Verifying runtime-health regional readiness"
if request_json GET "${API_URL}/api/v1/capabilities/comfyui_runtime/workbench/runtime-health" "" "${TMP_DIR}/runtime_health.json" "${RUNTIME_CURL_MAX_TIME}" && [ "${REQUEST_STATUS}" = "200" ]; then
  assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health did not report live_health_state=ok" "data.get('live_health_state') == 'ok'"
  assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health did not report dispatch_state=ready" "data.get('dispatch_state') == 'ready'"
  assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health did not report multi_subject_preview ready" "((data.get('recommended_for') or {}).get('multi_subject_preview') == 'ready')"
  assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health did not report regional_multi_subject_preview ready" "((data.get('lane_verdicts') or {}).get('regional_multi_subject_preview') == 'ready')"
  assert_json_predicate "${TMP_DIR}/runtime_health.json" "runtime-health still returned active failures" "not data.get('active_failures')"
  log "   runtime-health ready"
else
  warn "runtime-health probe was unavailable; continuing because live render submission is the authoritative gate"
fi

log "3. Staging real subject references and masks into backend workspace"
stage_assets
log "   staged assets under ${STAGED_ASSET_DIR}"

log "4. Submitting live regional multi-subject preview"
payload="$(jq -n \
  --arg workspace_id "${WORKSPACE_ID}" \
  --arg prompt "${PROMPT_TEXT}" \
  --arg scene_ref "${STAGED_ASSET_DIR}/scene_reference.png" \
  --arg subj_a_ref "${STAGED_ASSET_DIR}/subj_a_ref.png" \
  --arg subj_b_ref "${STAGED_ASSET_DIR}/subj_b_ref.png" \
  --arg subj_a_mask "${STAGED_ASSET_DIR}/subj_a_mask.png" \
  --arg subj_b_mask "${STAGED_ASSET_DIR}/subj_b_mask.png" \
  --argjson width "${WIDTH}" \
  --argjson height "${HEIGHT}" \
  --argjson steps "${STEPS}" \
  --argjson cfg "${CFG}" \
  '{
    workspace_id: $workspace_id,
    prompt: $prompt,
    reference_image: {file_path: $scene_ref},
    scene_subjects: [
      {subject_id: "subj_a", display_name: "Subject A", role: "lead", cast_id: "cast_a"},
      {subject_id: "subj_b", display_name: "Subject B", role: "support", cast_id: "cast_b"}
    ],
    character_adapter_slots: [
      {slot_id: "subj_a_face", slot_role: "identity_face", scope_kind: "subject", subject_id: "subj_a", binding_mode: "reference_only"},
      {slot_id: "subj_b_face", slot_role: "identity_face", scope_kind: "subject", subject_id: "subj_b", binding_mode: "reference_only"},
      {slot_id: "scene_style", slot_role: "style", scope_kind: "scene", binding_mode: "adapter_only"}
    ],
    subject_assets: [
      {subject_id: "subj_a", subject_reference_image: {file_path: $subj_a_ref}, subject_mask_image: {file_path: $subj_a_mask}},
      {subject_id: "subj_b", subject_reference_image: {file_path: $subj_b_ref}, subject_mask_image: {file_path: $subj_b_mask}}
    ],
    width: $width,
    height: $height,
    steps: $steps,
    cfg: $cfg,
    policy_mode: "speed",
    allow_specialized_runtime_auto_install: false,
    dry_run: false
  }')"
request_json POST "${API_URL}/api/v1/capabilities/video_renderer/render-local-preview" "${payload}" "${TMP_DIR}/live_preview.json"
[ "${REQUEST_STATUS}" = "200" ] || fail "render-local-preview returned HTTP ${REQUEST_STATUS:-000}"
assert_json_predicate "${TMP_DIR}/live_preview.json" "preview did not stay on live mode" "data.get('mode') == 'live'"
assert_json_predicate "${TMP_DIR}/live_preview.json" "preview did not select vr_regional_multi_subject_preview" "data.get('profile_id') == 'vr_regional_multi_subject_preview'"
assert_json_predicate "${TMP_DIR}/live_preview.json" "preview did not select the regional multi-subject template" "data.get('template_id') == 'sdxl_lightning_regional_multi_subject_img2img_preview_v1'"
assert_json_predicate "${TMP_DIR}/live_preview.json" "preview did not resolve all five expected asset bindings" "len(((data.get('reasoning') or {}).get('resolved_asset_bindings') or [])) == 5"
assert_json_predicate "${TMP_DIR}/live_preview.json" "preview left unresolved asset bindings" "all(item.get('status') == 'resolved' for item in (((data.get('reasoning') or {}).get('resolved_asset_bindings') or [])))"
assert_json_predicate "${TMP_DIR}/live_preview.json" "preview did not preserve the two subject-scoped adapter slots" "sorted((((data.get('reasoning') or {}).get('character_slot_contract') or {}).get('subject_scoped_adapter_subject_ids') or [])) == ['subj_a', 'subj_b']"
assert_json_predicate "${TMP_DIR}/live_preview.json" "preview returned an unexpected terminal error" "data.get('status') in ['success', 'queued', 'running']"
prompt_id="$(extract_json_value "${TMP_DIR}/live_preview.json" "data['prompt_id']")"
log "   prompt_id=${prompt_id}"

log "5. Waiting for ComfyUI history completion"
wait_for_history_completion "${prompt_id}" "${TMP_DIR}/history.json"
assert_json_predicate "${TMP_DIR}/history.json" "ComfyUI history did not report success" "((data.get('${prompt_id}') or {}).get('status') or {}).get('status_str') == 'success'"
output_path="$(extract_history_output_path "${TMP_DIR}/history.json" "${prompt_id}")"
[ -n "${output_path}" ] || fail "could not resolve output path from ComfyUI history"
[ -s "${output_path}" ] || fail "render output file not found or empty: ${output_path}"
case "${output_path}" in
  *"${OUTPUT_PREFIX}"*.png) ;;
  *) fail "render output file does not match expected prefix ${OUTPUT_PREFIX}: ${output_path}" ;;
esac
log "   completed output=${output_path}"

log ""
log "Smoke passed"
