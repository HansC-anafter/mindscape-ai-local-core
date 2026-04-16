#!/bin/bash

set -euo pipefail

API_URL="${API_URL:-http://localhost:8200}"
CONTAINER_API_URL="${CONTAINER_API_URL:-http://127.0.0.1:8200}"
API_TRANSPORT="${API_TRANSPORT:-auto}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:8300}"
BROWSER_FRONTEND_URL="${BROWSER_FRONTEND_URL:-${FRONTEND_URL/http:\/\/localhost/http:\/\/host.docker.internal}}"
BROWSER_FRONTEND_URL="${BROWSER_FRONTEND_URL/http:\/\/127.0.0.1/http:\/\/host.docker.internal}"
BACKEND_CONTAINER_NAME="${BACKEND_CONTAINER_NAME:-mindscape-ai-local-core-backend}"
OWNER_USER_ID="${OWNER_USER_ID:-default-user-id}"
CAPABILITY_CODE="performance_direction"
COMPONENT_CODE="PerformanceDirectionStoryboardEditorPage"
WORKSPACE_TITLE="${WORKSPACE_TITLE:-PD Browser Smoke $(date +%Y%m%d_%H%M%S)}"
UPDATED_CAST_ID="${UPDATED_CAST_ID:-cast_browser_roundtrip_$(date +%H%M%S)}"
KEEP_WORKSPACE="${KEEP_WORKSPACE:-0}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pd_browser_roundtrip.XXXXXX")"
REQUEST_STATUS=""
workspace_id=""

cleanup_all() {
  set +e
  if [ -n "${workspace_id}" ] && [ "${KEEP_WORKSPACE}" != "1" ]; then
    request DELETE "${API_URL}/api/v1/workspaces/${workspace_id}" "${TMP_DIR}/workspace_delete.json" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}
trap cleanup_all EXIT

log() {
  printf '%s\n' "$1"
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

json_value() {
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

json_assert() {
  local file_path="$1"
  local expression="$2"
  local error_message="$3"

  if ! python3 - "${file_path}" "${expression}" <<'PY'
import json
import sys

file_path = sys.argv[1]
expression = sys.argv[2]

with open(file_path, "r", encoding="utf-8") as handle:
    data = json.load(handle)

if not eval(expression, {"__builtins__": {"any": any, "all": all, "len": len}}, {"data": data}):
    raise SystemExit(1)
PY
  then
    fail "${error_message}"
  fi
}

request() {
  local method="$1"
  local url="$2"
  local output_file="$3"
  local payload="${4:-}"
  local raw_file="${TMP_DIR}/response.raw"
  local container_url="${url/${API_URL}/${CONTAINER_API_URL}}"

  parse_raw_response() {
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

  REQUEST_STATUS=""

  if [ "${API_TRANSPORT}" = "host" ] || [ "${API_TRANSPORT}" = "auto" ]; then
    if [ -n "${payload}" ]; then
      if curl -sS --max-time 20 --include -X "${method}" "${url}" -H 'Content-Type: application/json' -d "${payload}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response)"
        return 0
      fi
    else
      if curl -sS --max-time 20 --include -X "${method}" "${url}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response)"
        return 0
      fi
    fi
  fi

  if [ "${API_TRANSPORT}" = "container" ] || [ "${API_TRANSPORT}" = "auto" ]; then
    if [ -n "${payload}" ]; then
      if docker exec "${BACKEND_CONTAINER_NAME}" curl -sS --max-time 20 --include -X "${method}" "${container_url}" -H 'Content-Type: application/json' -d "${payload}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response)"
        return 0
      fi
    else
      if docker exec "${BACKEND_CONTAINER_NAME}" curl -sS --max-time 20 --include -X "${method}" "${container_url}" > "${raw_file}"; then
        REQUEST_STATUS="$(parse_raw_response)"
        return 0
      fi
    fi
  fi

  return 1
}

log "Performance Direction browser round-trip smoke"
log "API_URL=${API_URL}"
log "FRONTEND_URL=${FRONTEND_URL}"
log "BROWSER_FRONTEND_URL=${BROWSER_FRONTEND_URL}"
log ""

log "1. Checking backend and frontend reachability"
request GET "${API_URL}/health" "${TMP_DIR}/backend_health.json"
[ "${REQUEST_STATUS}" = "200" ] || fail "backend health endpoint returned HTTP ${REQUEST_STATUS:-000}"
json_assert "${TMP_DIR}/backend_health.json" "data.get('status') == 'healthy'" "backend health check did not return healthy"
curl -sS --max-time 10 "${FRONTEND_URL}" > "${TMP_DIR}/frontend_index.html"
grep -q 'Mindscape AI - Personal Agent Console' "${TMP_DIR}/frontend_index.html" || fail "frontend did not return the expected HTML shell"
log "   backend and frontend reachable"

log "2. Creating temporary workspace"
request POST "${API_URL}/api/v1/workspaces?owner_user_id=${OWNER_USER_ID}" "${TMP_DIR}/workspace.json" "$(printf '{"title":"%s","description":"Temporary workspace for performance_direction browser round-trip smoke"}' "${WORKSPACE_TITLE}")"
[ "${REQUEST_STATUS}" = "201" ] || fail "workspace create returned HTTP ${REQUEST_STATUS:-000}"
workspace_id="$(json_value "${TMP_DIR}/workspace.json" "data['id']")"
log "   workspace_id=${workspace_id}"

log "3. Creating direction session"
request POST "${API_URL}/api/v1/capabilities/${CAPABILITY_CODE}/sessions" "${TMP_DIR}/session.json" "$(printf '{"workspace_id":"%s","intent":{"goal":"browser roundtrip smoke"},"cast":[],"reference_ids":[]}' "${workspace_id}")"
[ "${REQUEST_STATUS}" = "200" ] || fail "session create returned HTTP ${REQUEST_STATUS:-000}"
session_id="$(json_value "${TMP_DIR}/session.json" "data['session']['session_id']")"
log "   session_id=${session_id}"

log "4. Generating baseline storyboard"
request POST "${API_URL}/api/v1/capabilities/${CAPABILITY_CODE}/sessions/${session_id}/storyboard" "${TMP_DIR}/storyboard.json" "$(printf '{"workspace_id":"%s","source_type":"generative","scene_specs":[{"scene_id":"sc_browser_01","shot_prompt":"single subject browser smoke","framing":"medium","scene_subjects":[{"subject_id":"subj_a","cast_id":"cast_a","role_id":"lead"}],"character_adapter_slots":[{"slot_id":"subj_a_face","slot_role":"identity_face","scope_kind":"subject","subject_id":"subj_a","binding_mode":"reference_only"},{"slot_id":"scene_style","slot_role":"style","scope_kind":"scene","subject_id":"","binding_mode":"adapter_only"}]}]}' "${workspace_id}")"
[ "${REQUEST_STATUS}" = "200" ] || fail "storyboard generation returned HTTP ${REQUEST_STATUS:-000}"
artifact_id="$(json_value "${TMP_DIR}/storyboard.json" "data['artifact']['artifact_id']")"
json_assert "${TMP_DIR}/storyboard.json" "len(data['storyboard']['scenes']) == 1" "storyboard did not contain the expected single scene"
log "   artifact_id=${artifact_id}"

log "5. Verifying installed UI metadata"
request GET "${API_URL}/api/v1/capability-packs/installed-capabilities/${CAPABILITY_CODE}/ui-components" "${TMP_DIR}/ui_components.json"
[ "${REQUEST_STATUS}" = "200" ] || fail "ui-components endpoint returned HTTP ${REQUEST_STATUS:-000}"
json_assert "${TMP_DIR}/ui_components.json" "any(row.get('code') == '${COMPONENT_CODE}' and row.get('import_path') == '@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage' for row in data)" "expected installed UI metadata for PerformanceDirectionStoryboardEditorPage was not present"

browser_runner="${TMP_DIR}/pd_browser_runner.py"
cat > "${browser_runner}" <<'PY'
import json
import os
import sys

from playwright.sync_api import sync_playwright

page_url = os.environ["PAGE_URL"]
updated_cast_id = os.environ["UPDATED_CAST_ID"]
expected_metadata_fragment = os.environ["EXPECTED_METADATA_FRAGMENT"]

metadata_statuses = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path="/usr/bin/chromium",
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1440, "height": 2200})

    def _record_response(response):
        if expected_metadata_fragment in response.url:
            metadata_statuses.append(
                {
                    "url": response.url,
                    "status": response.status,
                }
            )

    page.on("response", _record_response)
    page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
    page.get_by_text("Storyboard Subject + Adapter Slot Editor").wait_for(timeout=30000)
    page.get_by_text("1 loaded").wait_for(timeout=30000)
    page.get_by_text("Face / body / style binding lanes").wait_for(timeout=30000)

    cast_input = page.get_by_label("cast_id").nth(0)
    cast_input.wait_for(timeout=30000)
    initial_cast_id = cast_input.input_value()
    slot_count = page.get_by_label("slot_id").count()

    if slot_count != 2:
        raise SystemExit(f"expected 2 slot_id inputs, got {slot_count}")

    button = page.get_by_role("button", name="Apply patch")
    button.scroll_into_view_if_needed()

    with page.expect_response(
        lambda response: response.request.method == "POST"
        and "/storyboard/scene-patch" in response.url,
        timeout=30000,
    ) as response_info:
        cast_input.fill(updated_cast_id)
        button.click()

    patch_response = response_info.value
    if not patch_response.ok:
        raise SystemExit(f"scene patch request failed with HTTP {patch_response.status}")

    page.reload(wait_until="domcontentloaded", timeout=30000)
    page.get_by_text("Storyboard Subject + Adapter Slot Editor").wait_for(timeout=30000)
    page.get_by_text("1 loaded").wait_for(timeout=30000)
    reloaded_cast_id = page.get_by_label("cast_id").nth(0).input_value()

    browser.close()

result = {
    "initial_cast_id": initial_cast_id,
    "updated_cast_id": updated_cast_id,
    "reloaded_cast_id": reloaded_cast_id,
    "slot_count": slot_count,
    "metadata_statuses": metadata_statuses,
}
print(json.dumps(result))
PY

log "6. Running headless browser round-trip"
docker cp "${browser_runner}" "${BACKEND_CONTAINER_NAME}:/tmp/pd_browser_runner.py" >/dev/null
docker exec \
  -e "PAGE_URL=${BROWSER_FRONTEND_URL}/workspaces/${workspace_id}/capabilities/${CAPABILITY_CODE}?sessionId=${session_id}" \
  -e "UPDATED_CAST_ID=${UPDATED_CAST_ID}" \
  -e "EXPECTED_METADATA_FRAGMENT=/api/v1/capability-packs/installed-capabilities/${CAPABILITY_CODE}/ui-components" \
  "${BACKEND_CONTAINER_NAME}" \
  python3 /tmp/pd_browser_runner.py > "${TMP_DIR}/browser_result.json"

json_assert "${TMP_DIR}/browser_result.json" "data['reloaded_cast_id'] == data['updated_cast_id']" "browser reload did not preserve the updated cast_id"
json_assert "${TMP_DIR}/browser_result.json" "any(row.get('status') == 200 for row in data['metadata_statuses'])" "browser route did not fetch installed capability UI metadata successfully"

log "   initial_cast_id=$(json_value "${TMP_DIR}/browser_result.json" "data['initial_cast_id']")"
log "   updated_cast_id=$(json_value "${TMP_DIR}/browser_result.json" "data['updated_cast_id']")"
log "   reloaded_cast_id=$(json_value "${TMP_DIR}/browser_result.json" "data['reloaded_cast_id']")"
log ""
log "Performance Direction browser round-trip smoke passed"
