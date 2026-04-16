#!/usr/bin/env bash

set -euo pipefail

ROOT="/Users/shock/Projects_local/workspace/mindscape-ai-local-core"
BASE_URL="${BASE_URL:-http://127.0.0.1:8200}"
CONTAINER_BASE_URL="${CONTAINER_BASE_URL:-http://127.0.0.1:8200}"
HTTP_TRANSPORT="${HTTP_TRANSPORT:-auto}"
HTTP_TRANSPORT_FAILOVER="${HTTP_TRANSPORT_FAILOVER:-1}"
BACKEND_CONTAINER_NAME="${BACKEND_CONTAINER_NAME:-mindscape-ai-local-core-backend}"
BACKEND_READY_ATTEMPTS="${BACKEND_READY_ATTEMPTS:-60}"
BACKEND_READY_DELAY_SECONDS="${BACKEND_READY_DELAY_SECONDS:-2}"
HEALTH_MAX_TIME_SECONDS="${HEALTH_MAX_TIME_SECONDS:-15}"
ACTIVE_WORKSPACE_READY_TIMEOUT_SECONDS="${ACTIVE_WORKSPACE_READY_TIMEOUT_SECONDS:-3}"
JSON_GET_TIMEOUT_SECONDS="${JSON_GET_TIMEOUT_SECONDS:-30}"
COMPILE_JOB_GET_TIMEOUT_SECONDS="${COMPILE_JOB_GET_TIMEOUT_SECONDS:-60}"
COMPILE_JOB_DETAIL_GET_TIMEOUT_SECONDS="${COMPILE_JOB_DETAIL_GET_TIMEOUT_SECONDS:-12}"
SESSION_GET_TIMEOUT_SECONDS="${SESSION_GET_TIMEOUT_SECONDS:-90}"
ARTIFACT_INVENTORY_TIMEOUT_SECONDS="${ARTIFACT_INVENTORY_TIMEOUT_SECONDS:-90}"
MEMORY_DETAIL_TIMEOUT_SECONDS="${MEMORY_DETAIL_TIMEOUT_SECONDS:-45}"
SESSION_EVENTS_LIMIT="${SESSION_EVENTS_LIMIT:-2000}"
SESSION_EVENTS_TIMEOUT_SECONDS="${SESSION_EVENTS_TIMEOUT_SECONDS:-90}"
PROVIDER_STATUS_MAX_ATTEMPTS="${PROVIDER_STATUS_MAX_ATTEMPTS:-120}"
PROVIDER_STATUS_POLL_INTERVAL_SECONDS="${PROVIDER_STATUS_POLL_INTERVAL_SECONDS:-2}"
WORKSPACE_ID="${WORKSPACE_ID:-ws-memory-engine-e2e-codex-054234}"
PROFILE_ID="${PROFILE_ID:-default-user}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)_longtask_codex}"
TRACE_DIR="${ROOT}/data/e2e-traces/${RUN_ID}/longtask"
THEME_SPEC_PATH="${THEME_SPEC_PATH:-${ROOT}/scripts/e2e/specs/codex_cli_longtask_brand_ig_bootstrap.json}"
REVIEW_MODE="${REVIEW_MODE:-human_required}"
COMPILE_TIMEOUT_SECONDS="${COMPILE_TIMEOUT_SECONDS:-240}"
PACKAGE_TIMEOUT_SECONDS="${PACKAGE_TIMEOUT_SECONDS:-120}"
SESSION_POLL_INTERVAL_SECONDS="${SESSION_POLL_INTERVAL_SECONDS:-15}"
SESSION_POLL_MAX_ATTEMPTS="${SESSION_POLL_MAX_ATTEMPTS:-24}"
SESSION_POLL_GRACE_ATTEMPTS="${SESSION_POLL_GRACE_ATTEMPTS:-4}"
SESSION_POLL_EXTENSION_ATTEMPTS="${SESSION_POLL_EXTENSION_ATTEMPTS:-16}"
DISPATCH_POLL_EXTENSION_ATTEMPTS="${DISPATCH_POLL_EXTENSION_ATTEMPTS:-32}"
BRIDGE_ACTIVITY_EXTENSION_ATTEMPTS="${BRIDGE_ACTIVITY_EXTENSION_ATTEMPTS:-32}"
BRIDGE_ACTIVITY_MAX_AGE_SECONDS="${BRIDGE_ACTIVITY_MAX_AGE_SECONDS:-120}"
SESSION_DETAIL_GET_TIMEOUT_SECONDS="${SESSION_DETAIL_GET_TIMEOUT_SECONDS:-12}"
SESSION_LIST_GET_TIMEOUT_SECONDS="${SESSION_LIST_GET_TIMEOUT_SECONDS:-30}"
DELIVERABLE_SETTLE_MAX_ATTEMPTS="${DELIVERABLE_SETTLE_MAX_ATTEMPTS:-12}"
DELIVERABLE_SETTLE_INTERVAL_SECONDS="${DELIVERABLE_SETTLE_INTERVAL_SECONDS:-10}"
POST_FINALIZE_BACKEND_READY_ATTEMPTS="${POST_FINALIZE_BACKEND_READY_ATTEMPTS:-40}"
POST_FINALIZE_BACKEND_READY_DELAY_SECONDS="${POST_FINALIZE_BACKEND_READY_DELAY_SECONDS:-2}"
MINDSCAPE_WS_PONG_TIMEOUT="${MINDSCAPE_WS_PONG_TIMEOUT:-90}"
MINDSCAPE_RESULT_ACK_TIMEOUT="${MINDSCAPE_RESULT_ACK_TIMEOUT:-45}"
MINDSCAPE_WS_OPEN_TIMEOUT="${MINDSCAPE_WS_OPEN_TIMEOUT:-60}"
MINDSCAPE_RESULT_SPOOL_PATH="${MINDSCAPE_RESULT_SPOOL_PATH:-${TRACE_DIR}/00b_bridge_result_spool.json}"
SECRET_KEY="${HANDOFF_BUNDLE_SECRET:-local-e2e-secret-${RUN_ID}}"
MANAGED_BRIDGE_MODE="${MANAGED_BRIDGE_MODE:-1}"
WORKSPACE_CODEX_CLI_REQUIRED="${WORKSPACE_CODEX_CLI_REQUIRED:-1}"
BRIDGE_CLIENT_ID="${BRIDGE_CLIENT_ID:-e2e-codex-${RUN_ID}}"
BRIDGE_PID=""
BRIDGE_LOG="${TRACE_DIR}/00b_bridge_supervisor.log"
ACTIVE_BASE_URL="${BASE_URL}"
HTTP_TRANSPORT_SELECTED=""

PROJECT_ID="proj-e2e-${RUN_ID}"
THREAD_ID="e2e-${RUN_ID}"
HANDOFF_ID="handoff-${RUN_ID}"
SOURCE_DEVICE_ID="e2e-runner-${RUN_ID}"

mkdir -p "${TRACE_DIR}"

require_bin() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_bin curl
require_bin jq
require_bin python3

http_curl() {
  local exit_code=0

  if [[ "${HTTP_TRANSPORT_SELECTED}" == "backend_container" ]]; then
    docker exec "${BACKEND_CONTAINER_NAME}" curl "$@"
    exit_code="$?"
  else
    curl "$@"
    exit_code="$?"
  fi

  if [[ "${exit_code}" -eq 0 ]]; then
    return 0
  fi

  if maybe_failover_transport; then
    if [[ "${HTTP_TRANSPORT_SELECTED}" == "backend_container" ]]; then
      docker exec "${BACKEND_CONTAINER_NAME}" curl "$@"
      return $?
    fi
    curl "$@"
    return $?
  fi

  return "${exit_code}"
}

activate_transport() {
  case "${1}" in
    host)
      HTTP_TRANSPORT_SELECTED="host"
      ACTIVE_BASE_URL="${BASE_URL}"
      ;;
    backend_container)
      HTTP_TRANSPORT_SELECTED="backend_container"
      ACTIVE_BASE_URL="${CONTAINER_BASE_URL}"
      ;;
    *)
      echo "unsupported transport activation: ${1}" >&2
      exit 1
      ;;
  esac
}

probe_transport_health() {
  local transport="$1"

  if [[ "${transport}" == "backend_container" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
      return 1
    fi
    if ! docker inspect "${BACKEND_CONTAINER_NAME}" >/dev/null 2>&1; then
      return 1
    fi
    docker exec "${BACKEND_CONTAINER_NAME}" \
      curl -fsS --max-time "${HEALTH_MAX_TIME_SECONDS}" "${CONTAINER_BASE_URL}/health" \
      >/dev/null 2>&1
    return $?
  fi

  curl -fsS --max-time "${HEALTH_MAX_TIME_SECONDS}" "${BASE_URL}/health" >/dev/null 2>&1
}

probe_transport_ready() {
  local readiness_path="/api/v1/workspaces/active?owner_user_id=${PROFILE_ID}&surface=codex_cli"

  if probe_transport_health "$1"; then
    return 0
  fi

  if [[ "$1" == "backend_container" ]]; then
    docker exec "${BACKEND_CONTAINER_NAME}" \
      curl -fsS --max-time "${ACTIVE_WORKSPACE_READY_TIMEOUT_SECONDS}" "${CONTAINER_BASE_URL}${readiness_path}" \
      >/dev/null 2>&1
    return $?
  fi

  curl -fsS --max-time "${ACTIVE_WORKSPACE_READY_TIMEOUT_SECONDS}" "${BASE_URL}${readiness_path}" >/dev/null 2>&1
}

maybe_failover_transport() {
  local previous_transport="${HTTP_TRANSPORT_SELECTED:-}"
  local target_transport=""

  if [[ "${HTTP_TRANSPORT_FAILOVER}" != "1" ]]; then
    return 1
  fi

  case "${previous_transport}" in
    host)
      if [[ "${HTTP_TRANSPORT}" == "host" ]]; then
        return 1
      fi
      target_transport="backend_container"
      ;;
    backend_container)
      if [[ "${HTTP_TRANSPORT}" == "backend_container" ]]; then
        return 1
      fi
      target_transport="host"
      ;;
    *)
      return 1
      ;;
  esac

  if ! probe_transport_health "${target_transport}"; then
    return 1
  fi

  activate_transport "${target_transport}"
  echo "http transport failover: ${previous_transport} -> ${target_transport}" >&2
  return 0
}

select_http_transport() {
  local attempt

  case "${HTTP_TRANSPORT}" in
    host)
      activate_transport "host"
      ;;
    backend_container)
      activate_transport "backend_container"
      ;;
    auto)
      for attempt in $(seq 1 "${BACKEND_READY_ATTEMPTS}"); do
        if probe_transport_health host; then
          activate_transport "host"
          return 0
        fi
        if probe_transport_health backend_container; then
          activate_transport "backend_container"
          return 0
        fi
        sleep "${BACKEND_READY_DELAY_SECONDS}"
      done
      echo "unable to reach backend via host or backend_container transport after ${BACKEND_READY_ATTEMPTS} attempts" >&2
      exit 1
      ;;
    *)
      echo "unsupported HTTP_TRANSPORT=${HTTP_TRANSPORT}" >&2
      exit 1
      ;;
  esac
}

cleanup() {
  if [[ -n "${BRIDGE_PID}" ]]; then
    kill "${BRIDGE_PID}" 2>/dev/null || true
    wait "${BRIDGE_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

fail_trace() {
  local stage="$1"
  local reason="$2"
  jq -n \
    --arg run_id "${RUN_ID}" \
    --arg stage "${stage}" \
    --arg reason "${reason}" \
    --arg trace_dir "${TRACE_DIR}" \
    '{
      run_id: $run_id,
      stage: $stage,
      reason: $reason,
      trace_dir: $trace_dir
    }' >"${TRACE_DIR}/00_bootstrap_failure.json"
  write_note \
    "${TRACE_DIR}/00_bootstrap_failure.md" \
    "long-task runner 在 bootstrap 階段失敗。" \
    "stage=\`${stage}\`" \
    "reason=\`${reason}\`"
  echo "bootstrap_failure stage=${stage} reason=${reason}" >&2
  exit 1
}

write_note() {
  local path="$1"
  shift
  cat >"${path}" <<EOF
$*
EOF
}

wait_for_backend_ready() {
  local attempts="${1:-20}"
  local delay_seconds="${2:-2}"
  local i
  for i in $(seq 1 "${attempts}"); do
    if probe_transport_ready "${HTTP_TRANSPORT_SELECTED}"; then
      return 0
    fi
    if maybe_failover_transport && probe_transport_ready "${HTTP_TRANSPORT_SELECTED}"; then
      return 0
    fi
    sleep "${delay_seconds}"
  done
  return 1
}

capture_json_get() {
  local url="$1"
  local out_json="$2"
  local attempts="${3:-5}"
  local delay_seconds="${4:-2}"
  local timeout_seconds="${5:-${JSON_GET_TIMEOUT_SECONDS}}"
  local tmp_json
  local tmp_err
  local i

  tmp_json="$(mktemp)"
  tmp_err="$(mktemp)"
  for i in $(seq 1 "${attempts}"); do
    if http_curl -sS --max-time "${timeout_seconds}" "${url}" 2>"${tmp_err}" | jq '.' >"${tmp_json}"; then
      mv "${tmp_json}" "${out_json}"
      rm -f "${tmp_err}"
      return 0
    fi
    sleep "${delay_seconds}"
  done
  rm -f "${tmp_json}"
  rm -f "${tmp_err}"
  return 1
}

capture_json_get_with_backend_recovery() {
  local url="$1"
  local out_json="$2"
  local attempts="${3:-5}"
  local delay_seconds="${4:-2}"
  local timeout_seconds="${5:-${JSON_GET_TIMEOUT_SECONDS}}"

  if capture_json_get \
    "${url}" \
    "${out_json}" \
    "${attempts}" \
    "${delay_seconds}" \
    "${timeout_seconds}"; then
    return 0
  fi

  if ! wait_for_backend_ready \
    "${POST_FINALIZE_BACKEND_READY_ATTEMPTS}" \
    "${POST_FINALIZE_BACKEND_READY_DELAY_SECONDS}"; then
    return 1
  fi

  capture_json_get \
    "${url}" \
    "${out_json}" \
    "${attempts}" \
    "${delay_seconds}" \
    "${timeout_seconds}"
}

post_json_file() {
  local input_json="$1"
  local url="$2"
  local out_json="$3"
  local exit_code=0

  if [[ "${HTTP_TRANSPORT_SELECTED}" == "backend_container" ]]; then
    docker exec -i "${BACKEND_CONTAINER_NAME}" \
      curl -sS \
      -H 'Content-Type: application/json' \
      --data-binary @- \
      "${url}" <"${input_json}" | jq '.' >"${out_json}"
    return $?
  fi

  set +e
  curl -sS \
    -H 'Content-Type: application/json' \
    --data @"${input_json}" \
    "${url}" | jq '.' >"${out_json}"
  exit_code="$?"
  set -e

  if [[ "${exit_code}" -eq 0 ]]; then
    return 0
  fi

  if maybe_failover_transport && [[ "${HTTP_TRANSPORT_SELECTED}" == "backend_container" ]]; then
    docker exec -i "${BACKEND_CONTAINER_NAME}" \
      curl -sS \
      -H 'Content-Type: application/json' \
      --data-binary @- \
      "${url}" <"${input_json}" | jq '.' >"${out_json}"
    return $?
  fi

  return "${exit_code}"
}

capture_post_json_response() {
  local input_json="$1"
  local url="$2"
  local headers_out="$3"
  local body_out="$4"
  local timeout_seconds="$5"
  local exit_code=0
  local remote_headers=""
  local remote_body=""

  if [[ "${HTTP_TRANSPORT_SELECTED}" == "backend_container" ]]; then
    remote_headers="/tmp/longtask_headers_$$.$RANDOM.txt"
    remote_body="/tmp/longtask_body_$$.$RANDOM.json"
    set +e
    docker exec -i \
      -e REMOTE_HEADERS="${remote_headers}" \
      -e REMOTE_BODY="${remote_body}" \
      -e REMOTE_TIMEOUT="${timeout_seconds}" \
      -e REMOTE_URL="${url}" \
      "${BACKEND_CONTAINER_NAME}" \
      sh -lc 'curl -sS -D "$REMOTE_HEADERS" -o "$REMOTE_BODY" --max-time "$REMOTE_TIMEOUT" -H "Content-Type: application/json" --data-binary @- "$REMOTE_URL"' \
      <"${input_json}"
    exit_code="$?"
    set -e

    if docker exec "${BACKEND_CONTAINER_NAME}" test -f "${remote_headers}" >/dev/null 2>&1; then
      docker exec "${BACKEND_CONTAINER_NAME}" cat "${remote_headers}" >"${headers_out}"
    else
      : >"${headers_out}"
    fi

    if docker exec "${BACKEND_CONTAINER_NAME}" test -f "${remote_body}" >/dev/null 2>&1; then
      docker exec "${BACKEND_CONTAINER_NAME}" cat "${remote_body}" >"${body_out}"
    else
      : >"${body_out}"
    fi

    docker exec "${BACKEND_CONTAINER_NAME}" rm -f "${remote_headers}" "${remote_body}" >/dev/null 2>&1 || true
    return "${exit_code}"
  fi

  set +e
  curl -sS \
    -D "${headers_out}" \
    -o "${body_out}" \
    --max-time "${timeout_seconds}" \
    -H 'Content-Type: application/json' \
    --data @"${input_json}" \
    "${url}"
  exit_code="$?"
  set -e

  if [[ "${exit_code}" -eq 0 ]]; then
    return 0
  fi

  if maybe_failover_transport && [[ "${HTTP_TRANSPORT_SELECTED}" == "backend_container" ]]; then
    remote_headers="/tmp/longtask_headers_$$.$RANDOM.txt"
    remote_body="/tmp/longtask_body_$$.$RANDOM.json"
    set +e
    docker exec -i \
      -e REMOTE_HEADERS="${remote_headers}" \
      -e REMOTE_BODY="${remote_body}" \
      -e REMOTE_TIMEOUT="${timeout_seconds}" \
      -e REMOTE_URL="${url}" \
      "${BACKEND_CONTAINER_NAME}" \
      sh -lc 'curl -sS -D "$REMOTE_HEADERS" -o "$REMOTE_BODY" --max-time "$REMOTE_TIMEOUT" -H "Content-Type: application/json" --data-binary @- "$REMOTE_URL"' \
      <"${input_json}"
    exit_code="$?"
    set -e

    if docker exec "${BACKEND_CONTAINER_NAME}" test -f "${remote_headers}" >/dev/null 2>&1; then
      docker exec "${BACKEND_CONTAINER_NAME}" cat "${remote_headers}" >"${headers_out}"
    else
      : >"${headers_out}"
    fi

    if docker exec "${BACKEND_CONTAINER_NAME}" test -f "${remote_body}" >/dev/null 2>&1; then
      docker exec "${BACKEND_CONTAINER_NAME}" cat "${remote_body}" >"${body_out}"
    else
      : >"${body_out}"
    fi

    docker exec "${BACKEND_CONTAINER_NAME}" rm -f "${remote_headers}" "${remote_body}" >/dev/null 2>&1 || true
    if [[ "${exit_code}" -eq 0 ]]; then
      return 0
    fi
    if maybe_failover_transport; then
      curl -sS \
        -D "${headers_out}" \
        -o "${body_out}" \
        --max-time "${timeout_seconds}" \
        -H 'Content-Type: application/json' \
        --data @"${input_json}" \
        "${url}"
      return $?
    fi
    return "${exit_code}"
  fi

  if [[ "${exit_code}" -eq 0 ]]; then
    return 0
  fi

  if maybe_failover_transport && [[ "${HTTP_TRANSPORT_SELECTED}" == "backend_container" ]]; then
    remote_headers="/tmp/longtask_headers_$$.$RANDOM.txt"
    remote_body="/tmp/longtask_body_$$.$RANDOM.json"
    set +e
    docker exec -i \
      -e REMOTE_HEADERS="${remote_headers}" \
      -e REMOTE_BODY="${remote_body}" \
      -e REMOTE_TIMEOUT="${timeout_seconds}" \
      -e REMOTE_URL="${url}" \
      "${BACKEND_CONTAINER_NAME}" \
      sh -lc 'curl -sS -D "$REMOTE_HEADERS" -o "$REMOTE_BODY" --max-time "$REMOTE_TIMEOUT" -H "Content-Type: application/json" --data-binary @- "$REMOTE_URL"' \
      <"${input_json}"
    exit_code="$?"
    set -e

    if docker exec "${BACKEND_CONTAINER_NAME}" test -f "${remote_headers}" >/dev/null 2>&1; then
      docker exec "${BACKEND_CONTAINER_NAME}" cat "${remote_headers}" >"${headers_out}"
    else
      : >"${headers_out}"
    fi

    if docker exec "${BACKEND_CONTAINER_NAME}" test -f "${remote_body}" >/dev/null 2>&1; then
      docker exec "${BACKEND_CONTAINER_NAME}" cat "${remote_body}" >"${body_out}"
    else
      : >"${body_out}"
    fi

    docker exec "${BACKEND_CONTAINER_NAME}" rm -f "${remote_headers}" "${remote_body}" >/dev/null 2>&1 || true
  fi

  return "${exit_code}"
}

refresh_compile_job_snapshot() {
  if [[ -z "${compile_job_id:-}" ]]; then
    return 1
  fi

  if capture_json_get_with_backend_recovery \
    "${ACTIVE_BASE_URL}/api/handoff-bundles/compile-jobs/${compile_job_id}" \
    "${TRACE_DIR}/02c_compile_job.json" \
    1 \
    1 \
    "${COMPILE_JOB_DETAIL_GET_TIMEOUT_SECONDS}"; then
    return 0
  fi

  local session_list_tmp
  local compile_match_tmp
  session_list_tmp="$(mktemp)"
  compile_match_tmp="$(mktemp)"

  if ! capture_json_get_with_backend_recovery \
    "${ACTIVE_BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions?limit=50" \
    "${session_list_tmp}" \
    2 \
    2 \
    "${SESSION_LIST_GET_TIMEOUT_SECONDS}"; then
    rm -f "${session_list_tmp}" "${compile_match_tmp}"
    return 1
  fi

  if ! jq \
    --arg session_id "${session_id:-}" \
    --arg compile_job_id "${compile_job_id}" \
    --arg project_id "${PROJECT_ID}" \
    --arg thread_id "${THREAD_ID}" \
    '
    first(
      .sessions[]
      | select(
          ((.compile_job.id // "") == $compile_job_id)
          or (.id == $session_id)
          or (
            (.project_id == $project_id)
            and (.thread_id == $thread_id)
          )
        )
      | .compile_job
      | select(. != null)
    )
    | .metadata = ((.metadata // {}) + {snapshot_source: "session_list_fallback"})
    ' "${session_list_tmp}" >"${compile_match_tmp}"; then
    rm -f "${session_list_tmp}" "${compile_match_tmp}"
    return 1
  fi

  if [[ ! -s "${compile_match_tmp}" ]]; then
    rm -f "${session_list_tmp}" "${compile_match_tmp}"
    return 1
  fi

  mv "${compile_match_tmp}" "${TRACE_DIR}/02c_compile_job.json"
  rm -f "${session_list_tmp}"
  return 0
}

refresh_session_snapshot() {
  if [[ -z "${session_id:-}" ]]; then
    return 1
  fi

  if capture_json_get_with_backend_recovery \
    "${ACTIVE_BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions/${session_id}" \
    "${TRACE_DIR}/03_session_after_close.json" \
    1 \
    1 \
    "${SESSION_DETAIL_GET_TIMEOUT_SECONDS}"; then
    return 0
  fi

  local session_list_tmp
  local session_match_tmp
  session_list_tmp="$(mktemp)"
  session_match_tmp="$(mktemp)"

  if ! capture_json_get_with_backend_recovery \
    "${ACTIVE_BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions?limit=50" \
    "${session_list_tmp}" \
    2 \
    2 \
    "${SESSION_LIST_GET_TIMEOUT_SECONDS}"; then
    rm -f "${session_list_tmp}" "${session_match_tmp}"
    return 1
  fi

  if ! jq \
    --arg session_id "${session_id}" \
    --arg project_id "${PROJECT_ID}" \
    --arg thread_id "${THREAD_ID}" \
    '
    first(
      .sessions[]
      | select(
          (.id == $session_id)
          or (
            (.project_id == $project_id)
            and (.thread_id == $thread_id)
          )
        )
    )
    | .metadata = ((.metadata // {}) + {snapshot_source: "session_list_fallback"})
    ' "${session_list_tmp}" >"${session_match_tmp}"; then
    rm -f "${session_list_tmp}" "${session_match_tmp}"
    return 1
  fi

  if [[ ! -s "${session_match_tmp}" ]]; then
    rm -f "${session_list_tmp}" "${session_match_tmp}"
    return 1
  fi

  mv "${session_match_tmp}" "${TRACE_DIR}/03_session_after_close.json"
  rm -f "${session_list_tmp}"
  return 0
}

count_pending_deliverable_action_items() {
  if [[ ! -f "${TRACE_DIR}/03_session_after_close.json" ]]; then
    echo "0"
    return 0
  fi

  jq -r '
    [
      (.action_items // [])[]
      | select(((.input_params.deliverable_path // "") | tostring | length) > 0)
      | ((.task_status // .status // "") | ascii_downcase) as $status
      | select(
          ($status == "")
          or ($status == "pending")
          or ($status == "queued")
          or ($status == "running")
        )
    ]
    | length
  ' "${TRACE_DIR}/03_session_after_close.json"
}

wait_for_deliverable_tasks_to_settle() {
  local attempt pending_count

  if [[ -z "${session_id:-}" ]]; then
    return 0
  fi

  for attempt in $(seq 1 "${DELIVERABLE_SETTLE_MAX_ATTEMPTS}"); do
    refresh_session_snapshot || true
    pending_count="$(count_pending_deliverable_action_items)"
    if [[ "${pending_count}" == "0" ]]; then
      return 0
    fi
    sleep "${DELIVERABLE_SETTLE_INTERVAL_SECONDS}"
  done

  return 0
}

bridge_log_has_recent_activity() {
  local max_age="${1:-${BRIDGE_ACTIVITY_MAX_AGE_SECONDS}}"
  local now_epoch=""
  local mtime_epoch=""
  local age_seconds=0

  if [[ ! -f "${BRIDGE_LOG}" ]]; then
    return 1
  fi

  now_epoch="$(date +%s)"
  mtime_epoch="$(stat -f %m "${BRIDGE_LOG}" 2>/dev/null || true)"
  if [[ -z "${mtime_epoch}" ]]; then
    mtime_epoch="$(stat -c %Y "${BRIDGE_LOG}" 2>/dev/null || true)"
  fi
  if [[ -z "${mtime_epoch}" ]]; then
    return 1
  fi

  age_seconds=$(( now_epoch - mtime_epoch ))
  if (( age_seconds <= max_age )); then
    return 0
  fi
  return 1
}

refresh_session_events_snapshot() {
  if [[ -z "${session_id:-}" ]]; then
    return 1
  fi
  capture_json_get_with_backend_recovery \
    "${ACTIVE_BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions/${session_id}/events?limit=${SESSION_EVENTS_LIMIT}" \
    "${TRACE_DIR}/04_session_events.json" \
    2 \
    2 \
    "${SESSION_EVENTS_TIMEOUT_SECONDS}"
}

provider_status_matches_expectation() {
  local provider_status_path="$1"
  if [[ ! -f "${provider_status_path}" ]]; then
    return 1
  fi

  if [[ "${MANAGED_BRIDGE_MODE}" == "1" ]]; then
    jq -e --arg ws "${WORKSPACE_ID}" --arg client_id "${BRIDGE_CLIENT_ID}" '
      (.workspaces[$ws].clients // [])
      | any(.client_id == $client_id and .surface_type == "codex_cli" and .authenticated == true)
    ' "${provider_status_path}" >/dev/null
    return $?
  fi

  jq -e --arg ws "${WORKSPACE_ID}" '
    (.workspaces[$ws].clients // [])
    | any(.surface_type == "codex_cli" and .authenticated == true)
  ' "${provider_status_path}" >/dev/null
}

bridge_log_matches_expectation() {
  if [[ "${MANAGED_BRIDGE_MODE}" != "1" ]]; then
    return 1
  fi

  if [[ ! -f "${BRIDGE_LOG}" ]]; then
    return 1
  fi

  rg -q "Welcome! client_id=${BRIDGE_CLIENT_ID}" "${BRIDGE_LOG}"
}

write_summary_json() {
  local tmp_summary
  tmp_summary="$(mktemp "${TRACE_DIR}/summary.XXXXXX.json")"

  jq -n \
    --arg run_id "${RUN_ID}" \
    --arg workspace_id "${WORKSPACE_ID}" \
    --arg project_id "${PROJECT_ID}" \
    --arg thread_id "${THREAD_ID}" \
    --arg compile_job_id "${compile_job_id}" \
    --arg compile_job_status "${compile_job_status}" \
    --arg session_id "${session_id}" \
    --arg memory_item_id "${memory_item_id}" \
    --arg terminal_state "${terminal_state}" \
    --arg acceptance_status "${acceptance_status}" \
    --arg trace_dir "${TRACE_DIR}" \
    '{
      run_id: $run_id,
      workspace_id: $workspace_id,
      project_id: $project_id,
      thread_id: $thread_id,
      compile_job_id: $compile_job_id,
      compile_job_status: $compile_job_status,
      session_id: $session_id,
      memory_item_id: $memory_item_id,
      terminal_state: $terminal_state,
      acceptance_status: $acceptance_status,
      trace_dir: $trace_dir
    }' >"${tmp_summary}"

  mv "${tmp_summary}" "${TRACE_DIR}/summary.json"
}

echo "run_id=${RUN_ID}"
echo "trace_dir=${TRACE_DIR}"

select_http_transport
echo "http_transport=${HTTP_TRANSPORT_SELECTED}"
echo "active_base_url=${ACTIVE_BASE_URL}"

wait_for_backend_ready "${BACKEND_READY_ATTEMPTS}" "${BACKEND_READY_DELAY_SECONDS}" || fail_trace "backend_ready" "backend /health unavailable"
cp "${THEME_SPEC_PATH}" "${TRACE_DIR}/00_theme_spec.json" || fail_trace "theme_spec" "failed to copy theme spec"

write_note \
  "${TRACE_DIR}/00_theme_spec.md" \
  "這是 long-task E2E 的固定主題 spec。" \
  "runner 與 validator 都必須以這份 spec 作為同一個驗收契約來源。"

if [[ "${MANAGED_BRIDGE_MODE}" == "1" ]]; then
  MINDSCAPE_WS_PONG_TIMEOUT="${MINDSCAPE_WS_PONG_TIMEOUT}" \
  MINDSCAPE_RESULT_ACK_TIMEOUT="${MINDSCAPE_RESULT_ACK_TIMEOUT}" \
  MINDSCAPE_WS_OPEN_TIMEOUT="${MINDSCAPE_WS_OPEN_TIMEOUT}" \
  MINDSCAPE_RESULT_SPOOL_PATH="${MINDSCAPE_RESULT_SPOOL_PATH}" \
  bash "${ROOT}/scripts/start_cli_bridge_supervisor.sh" \
    --surfaces codex_cli \
    --workspace-id "${WORKSPACE_ID}" \
    --host "${BASE_URL#http://}" \
    --client-id "${BRIDGE_CLIENT_ID}" \
    >"${BRIDGE_LOG}" 2>&1 &
  BRIDGE_PID="$!"
  write_note \
    "${TRACE_DIR}/00b_bridge_supervisor.md" \
    "這輪 long-task E2E 由腳本自管 supervisor bridge。" \
    "compile request 會把 executor-target 指向這條 codex_cli client。"
fi

capture_json_get_with_backend_recovery \
  "${ACTIVE_BASE_URL}/api/v1/mcp/agent/status" \
  "${TRACE_DIR}/00_provider_status.json" || fail_trace "provider_status" "provider status unavailable"

provider_status_matched=0
if [[ "${MANAGED_BRIDGE_MODE}" == "1" ]]; then
  for _ in $(seq 1 "${PROVIDER_STATUS_MAX_ATTEMPTS}"); do
    if provider_status_matches_expectation "${TRACE_DIR}/00_provider_status.json"; then
      provider_status_matched=1
      break
    fi
    sleep "${PROVIDER_STATUS_POLL_INTERVAL_SECONDS}"
    capture_json_get_with_backend_recovery \
      "${ACTIVE_BASE_URL}/api/v1/mcp/agent/status" \
      "${TRACE_DIR}/00_provider_status.json"
  done
elif provider_status_matches_expectation "${TRACE_DIR}/00_provider_status.json"; then
  provider_status_matched=1
fi

if [[ "${provider_status_matched}" != "1" ]] && bridge_log_matches_expectation; then
  provider_status_matched=1
fi

write_note \
  "${TRACE_DIR}/00_provider_status.md" \
  "這份 provider status 用來證明 long-task E2E 走的是 codex_cli explicit runtime。" \
  "若是 managed bridge mode，必須看到指定 client_id。"

jq -n \
  --arg workspace_id "${WORKSPACE_ID}" \
  --arg client_id "${BRIDGE_CLIENT_ID}" \
  --argjson managed_bridge_mode "$( [[ "${MANAGED_BRIDGE_MODE}" == "1" ]] && echo true || echo false )" \
  --argjson matched "$( [[ "${provider_status_matched}" == "1" ]] && echo true || echo false )" \
  '{
    workspace_id: $workspace_id,
    managed_bridge_mode: $managed_bridge_mode,
    expected_client_id: (if $managed_bridge_mode then $client_id else null end),
    matched: $matched
  }' >"${TRACE_DIR}/00_provider_status_check.json"

if [[ "${WORKSPACE_CODEX_CLI_REQUIRED}" == "1" && "${provider_status_matched}" != "1" ]]; then
  fail_trace "workspace_codex_cli" "workspace codex_cli client not connected/authenticated before compile"
fi

capture_json_get_with_backend_recovery \
  "${ACTIVE_BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions?limit=50" \
  "${TRACE_DIR}/00c_workspace_session_preflight.json" || fail_trace "workspace_session_preflight" "workspace session preflight unavailable"

foreign_active_session_count="$(jq -r '
  [
    .sessions[]
    | select(.status == "active")
  ] | length
' "${TRACE_DIR}/00c_workspace_session_preflight.json")"

if [[ "${foreign_active_session_count}" != "0" ]]; then
  jq -c '
    [
      .sessions[]
      | select(.status == "active")
      | {
          id,
          status,
          project_id,
          thread_id,
          stage: (.metadata.pipeline_stage // null)
        }
    ]
  ' "${TRACE_DIR}/00c_workspace_session_preflight.json" \
    >"${TRACE_DIR}/00c_workspace_session_preflight_active.json"
  fail_trace "workspace_session_preflight" "workspace already has active meeting sessions; aborting to avoid stale-run contamination"
fi

jq -n \
  --arg handoff_id "${HANDOFF_ID}" \
  --arg workspace_id "${WORKSPACE_ID}" \
  --arg source_device_id "${SOURCE_DEVICE_ID}" \
  --arg secret_key "${SECRET_KEY}" \
  --arg run_id "${RUN_ID}" \
  --slurpfile spec "${TRACE_DIR}/00_theme_spec.json" \
  '{
    payload_type: "handoff_in",
    source_device_id: $source_device_id,
    secret_key: $secret_key,
    payload: {
      handoff_id: $handoff_id,
      workspace_id: $workspace_id,
      intent_summary: $spec[0].intent_summary,
      goals: ($spec[0].goals // []),
      non_goals: ($spec[0].non_goals // []),
      deliverables: (
        ($spec[0].deliverables // [])
        | map({
            name: .filename,
            mime_type: (.mime_type // "text/markdown"),
            description: (.description // .filename)
          })
      ),
      constraints: {
        action_space: "WRITE_WS",
        max_duration_seconds: 1800
      },
      requested_output_type: "text/markdown",
      human_instructions: ($spec[0].human_instructions // ""),
      metadata: {
        run_id: $run_id,
        e2e_suite: "codex_cli_longtask",
        theme_id: ($spec[0].theme_id // "unknown")
      }
    }
  }' >"${TRACE_DIR}/01_package_request.json"

write_note \
  "${TRACE_DIR}/01_package_request.md" \
  "這是固定主題的 long-task handoff package request。" \
  "它明確要求三份 markdown deliverables，不允許 generic closure brief 取代。"

tmp_package_body="$(mktemp)"
tmp_package_headers="$(mktemp)"
set +e
capture_post_json_response \
  "${TRACE_DIR}/01_package_request.json" \
  "${ACTIVE_BASE_URL}/api/handoff-bundles/package" \
  "${tmp_package_headers}" \
  "${tmp_package_body}" \
  "${PACKAGE_TIMEOUT_SECONDS}"
package_exit="$?"
set -e

package_http_status="$(awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code+0}' "${tmp_package_headers}")"

jq -n \
  --arg body "$(cat "${tmp_package_body}")" \
  --arg headers "$(cat "${tmp_package_headers}")" \
  --argjson http_status "${package_http_status:-0}" \
  --argjson curl_exit "${package_exit}" \
  --argjson timeout_seconds "${PACKAGE_TIMEOUT_SECONDS}" \
  '{
    http_status: $http_status,
    curl_exit: $curl_exit,
    timeout_seconds: $timeout_seconds,
    headers_raw: $headers,
    body_raw: $body
  }' >"${TRACE_DIR}/01a_package_transport.json"

if [[ "${package_exit}" -ne 0 ]]; then
  rm -f "${tmp_package_body}" "${tmp_package_headers}"
  fail_trace "package" "package_request_failed"
fi

if [[ ! -s "${tmp_package_body}" ]]; then
  rm -f "${tmp_package_body}" "${tmp_package_headers}"
  fail_trace "package" "package_response_empty"
fi

if ! jq '.' "${tmp_package_body}" >"${TRACE_DIR}/01_package_response.json"; then
  rm -f "${tmp_package_body}" "${tmp_package_headers}"
  fail_trace "package" "package_response_invalid_json"
fi

rm -f "${tmp_package_body}" "${tmp_package_headers}"

jq -n \
  --arg workspace_id "${WORKSPACE_ID}" \
  --arg project_id "${PROJECT_ID}" \
  --arg profile_id "${PROFILE_ID}" \
  --arg thread_id "${THREAD_ID}" \
  --arg secret_key "${SECRET_KEY}" \
  --arg executor_target_client_id "${BRIDGE_CLIENT_ID}" \
  --argjson managed_bridge_mode "$( [[ "${MANAGED_BRIDGE_MODE}" == "1" ]] && echo true || echo false )" \
  --slurpfile packaged "${TRACE_DIR}/01_package_response.json" \
  '{
    bundle: $packaged[0],
    workspace_id: $workspace_id,
    project_id: $project_id,
    profile_id: $profile_id,
    thread_id: $thread_id,
    secret_key: $secret_key,
    executor_target_client_id: (if $managed_bridge_mode then $executor_target_client_id else null end)
  }' >"${TRACE_DIR}/02_compile_request.json"

write_note \
  "${TRACE_DIR}/02_compile_request.md" \
  "這一步走正式 async compile ingress。" \
  "它只應快速回 accepted，不應同步等待整條 long-task meeting 跑完。"

tmp_body="$(mktemp)"
tmp_headers="$(mktemp)"
set +e
capture_post_json_response \
  "${TRACE_DIR}/02_compile_request.json" \
  "${ACTIVE_BASE_URL}/api/handoff-bundles/compile" \
  "${tmp_headers}" \
  "${tmp_body}" \
  "${COMPILE_TIMEOUT_SECONDS}"
compile_exit="$?"
set -e

http_status="$(awk 'toupper($1) ~ /^HTTP/ {code=$2} END {print code+0}' "${tmp_headers}")"

jq -n \
  --arg body "$(cat "${tmp_body}")" \
  --arg headers "$(cat "${tmp_headers}")" \
  --argjson http_status "${http_status:-0}" \
  --argjson curl_exit "${compile_exit}" \
  --argjson timeout_seconds "${COMPILE_TIMEOUT_SECONDS}" \
  '{
    http_status: $http_status,
    curl_exit: $curl_exit,
    timeout_seconds: $timeout_seconds,
    headers_raw: $headers,
    body_raw: $body
  }' >"${TRACE_DIR}/02_compile_response.json"

rm -f "${tmp_body}" "${tmp_headers}"

compile_job_id="$(jq -r '
  .body_raw
  | fromjson? // {}
  | .compile_job_id // empty
' "${TRACE_DIR}/02_compile_response.json")"

session_id="$(jq -r '
  .body_raw
  | fromjson? // {}
  | .session_id // empty
' "${TRACE_DIR}/02_compile_response.json")"

jq -n \
  --arg compile_job_id "${compile_job_id}" \
  --arg session_id "${session_id}" \
  '{
    compile_job_id: $compile_job_id,
    session_id: $session_id
  }' >"${TRACE_DIR}/02a_compile_acceptance.json"

if [[ -n "${compile_job_id}" ]]; then
  refresh_compile_job_snapshot || true
fi

capture_json_get \
  "${ACTIVE_BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions?limit=50" \
  "${TRACE_DIR}/02b_session_list.json"

if [[ -z "${session_id}" ]]; then
  session_id="$(jq -r --arg project_id "${PROJECT_ID}" '
    .sessions[]
    | select(.project_id == $project_id)
    | .id
  ' "${TRACE_DIR}/02b_session_list.json" | head -n 1)"
fi

jq -n \
  --arg project_id "${PROJECT_ID}" \
  --arg thread_id "${THREAD_ID}" \
  --arg session_id "${session_id}" \
  '{
    project_id: $project_id,
    thread_id: $thread_id,
    session_id: $session_id
  }' >"${TRACE_DIR}/02b_session_lookup.json"

if [[ -z "${session_id}" ]]; then
  write_note \
    "${TRACE_DIR}/02b_session_lookup.md" \
    "compile 沒有交出 session_id，session list 也找不到對應 project。long-task E2E 在 ingress 前半段失敗。"
  exit 1
fi

poll_log="${TRACE_DIR}/03_session_polls.ndjson"
: >"${poll_log}"
terminal_state=""
last_round_count="0"
last_pipeline_stage=""
last_pipeline_stage_status=""
compile_job_status=""

poll_session_snapshot() {
  if ! refresh_session_snapshot; then
    return 1
  fi
  return 0
}

record_poll_row() {
  local grace_flag="${1:-false}"
  local extension_flag="${2:-false}"
  local error="${3:-}"
  if [[ -n "${error}" ]]; then
    jq -nc \
      --arg polled_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg session_id "${session_id}" \
      --arg error "${error}" \
      --arg compile_job_status "${compile_job_status}" \
      --argjson grace_poll "${grace_flag}" \
      --argjson extended_poll "${extension_flag}" '
      {
        polled_at: $polled_at,
        id: $session_id,
        error: $error,
        grace_poll: $grace_poll,
        extended_poll: $extended_poll,
        compile_job_status: ($compile_job_status | select(length > 0))
      }' >>"${poll_log}"
    return
  fi

  jq -c \
    --arg polled_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg compile_job_status "${compile_job_status}" \
    --argjson grace_poll "${grace_flag}" \
    --argjson extended_poll "${extension_flag}" '
    {
      polled_at: $polled_at,
      id,
      status,
      round_count,
      ended_at,
      pipeline_stage: (.metadata.pipeline_stage // null),
      pipeline_stage_status: (.metadata.pipeline_stage_status // null),
      canonical_memory_item_id: (.metadata.canonical_memory_item_id // null),
      compile_job_status: ($compile_job_status | select(length > 0)),
      grace_poll: (if $grace_poll then true else empty end),
      extended_poll: (if $extended_poll then true else empty end)
    }
  ' "${TRACE_DIR}/03_session_after_close.json" >>"${poll_log}"
}

for attempt in $(seq 1 "${SESSION_POLL_MAX_ATTEMPTS}"); do
  refresh_compile_job_snapshot || true
  compile_job_status="$(jq -r '.status // empty' "${TRACE_DIR}/02c_compile_job.json" 2>/dev/null || true)"
  if ! poll_session_snapshot; then
    record_poll_row false false "session poll unavailable"
    wait_for_backend_ready 40 2 || true
    sleep "${SESSION_POLL_INTERVAL_SECONDS}"
    continue
  fi
  record_poll_row
  status="$(jq -r '.status' "${TRACE_DIR}/03_session_after_close.json")"
  last_round_count="$(jq -r '.round_count // 0' "${TRACE_DIR}/03_session_after_close.json")"
  last_pipeline_stage="$(jq -r '.metadata.pipeline_stage // empty' "${TRACE_DIR}/03_session_after_close.json")"
  last_pipeline_stage_status="$(jq -r '.metadata.pipeline_stage_status // empty' "${TRACE_DIR}/03_session_after_close.json")"
  if [[ "${status}" == "closed" || "${status}" == "failed" ]]; then
    terminal_state="${status}"
    break
  fi
  sleep "${SESSION_POLL_INTERVAL_SECONDS}"
done

if [[ -z "${terminal_state}" ]]; then
  for attempt in $(seq 1 "${SESSION_POLL_GRACE_ATTEMPTS}"); do
    refresh_compile_job_snapshot || true
    compile_job_status="$(jq -r '.status // empty' "${TRACE_DIR}/02c_compile_job.json" 2>/dev/null || true)"
    if ! poll_session_snapshot; then
      record_poll_row true false "grace session poll unavailable"
      wait_for_backend_ready 40 2 || true
      sleep "${SESSION_POLL_INTERVAL_SECONDS}"
      continue
    fi
    record_poll_row true false
    status="$(jq -r '.status' "${TRACE_DIR}/03_session_after_close.json")"
    last_round_count="$(jq -r '.round_count // 0' "${TRACE_DIR}/03_session_after_close.json")"
    last_pipeline_stage="$(jq -r '.metadata.pipeline_stage // empty' "${TRACE_DIR}/03_session_after_close.json")"
    last_pipeline_stage_status="$(jq -r '.metadata.pipeline_stage_status // empty' "${TRACE_DIR}/03_session_after_close.json")"
    if [[ "${status}" == "closed" || "${status}" == "failed" ]]; then
      terminal_state="${status}"
      break
    fi
    sleep "${SESSION_POLL_INTERVAL_SECONDS}"
  done
fi

if [[ -z "${terminal_state}" ]]; then
  if [[ "${last_round_count}" -ge 1 ]] || [[ "${compile_job_status}" == "running" ]]; then
    for attempt in $(seq 1 "${SESSION_POLL_EXTENSION_ATTEMPTS}"); do
      refresh_compile_job_snapshot || true
      compile_job_status="$(jq -r '.status // empty' "${TRACE_DIR}/02c_compile_job.json" 2>/dev/null || true)"
      if ! poll_session_snapshot; then
        record_poll_row false true "extended session poll unavailable"
        wait_for_backend_ready 40 2 || true
        sleep "${SESSION_POLL_INTERVAL_SECONDS}"
        continue
      fi
      record_poll_row false true
      status="$(jq -r '.status' "${TRACE_DIR}/03_session_after_close.json")"
      last_round_count="$(jq -r '.round_count // 0' "${TRACE_DIR}/03_session_after_close.json")"
      last_pipeline_stage="$(jq -r '.metadata.pipeline_stage // empty' "${TRACE_DIR}/03_session_after_close.json")"
      last_pipeline_stage_status="$(jq -r '.metadata.pipeline_stage_status // empty' "${TRACE_DIR}/03_session_after_close.json")"
      if [[ "${status}" == "closed" || "${status}" == "failed" ]]; then
        terminal_state="${status}"
        break
      fi
      sleep "${SESSION_POLL_INTERVAL_SECONDS}"
    done
  fi
fi

if [[ -z "${terminal_state}" ]]; then
  if [[ "${last_pipeline_stage}" == "extract_actions" || "${last_pipeline_stage}" == "dispatch" ]]; then
    for attempt in $(seq 1 "${DISPATCH_POLL_EXTENSION_ATTEMPTS}"); do
      refresh_compile_job_snapshot || true
      compile_job_status="$(jq -r '.status // empty' "${TRACE_DIR}/02c_compile_job.json" 2>/dev/null || true)"
      if ! poll_session_snapshot; then
        record_poll_row false true "dispatch extension session poll unavailable"
        wait_for_backend_ready 40 2 || true
        sleep "${SESSION_POLL_INTERVAL_SECONDS}"
        continue
      fi
      record_poll_row false true
      status="$(jq -r '.status' "${TRACE_DIR}/03_session_after_close.json")"
      last_round_count="$(jq -r '.round_count // 0' "${TRACE_DIR}/03_session_after_close.json")"
      last_pipeline_stage="$(jq -r '.metadata.pipeline_stage // empty' "${TRACE_DIR}/03_session_after_close.json")"
      last_pipeline_stage_status="$(jq -r '.metadata.pipeline_stage_status // empty' "${TRACE_DIR}/03_session_after_close.json")"
      if [[ "${status}" == "closed" || "${status}" == "failed" ]]; then
        terminal_state="${status}"
        break
      fi
      if [[ "${last_pipeline_stage}" != "extract_actions" && "${last_pipeline_stage}" != "dispatch" ]]; then
        break
      fi
      sleep "${SESSION_POLL_INTERVAL_SECONDS}"
    done
  fi
fi

if [[ -z "${terminal_state}" ]]; then
  if [[ "${compile_job_status}" == "running" ]] && bridge_log_has_recent_activity; then
    for attempt in $(seq 1 "${BRIDGE_ACTIVITY_EXTENSION_ATTEMPTS}"); do
      refresh_compile_job_snapshot || true
      compile_job_status="$(jq -r '.status // empty' "${TRACE_DIR}/02c_compile_job.json" 2>/dev/null || true)"
      if ! poll_session_snapshot; then
        record_poll_row false true "bridge activity extension session poll unavailable"
        wait_for_backend_ready 40 2 || true
        sleep "${SESSION_POLL_INTERVAL_SECONDS}"
        continue
      fi
      record_poll_row false true
      status="$(jq -r '.status' "${TRACE_DIR}/03_session_after_close.json")"
      last_round_count="$(jq -r '.round_count // 0' "${TRACE_DIR}/03_session_after_close.json")"
      last_pipeline_stage="$(jq -r '.metadata.pipeline_stage // empty' "${TRACE_DIR}/03_session_after_close.json")"
      last_pipeline_stage_status="$(jq -r '.metadata.pipeline_stage_status // empty' "${TRACE_DIR}/03_session_after_close.json")"
      if [[ "${status}" == "closed" || "${status}" == "failed" ]]; then
        terminal_state="${status}"
        break
      fi
      if [[ "${compile_job_status}" != "running" ]]; then
        break
      fi
      if ! bridge_log_has_recent_activity; then
        break
      fi
      sleep "${SESSION_POLL_INTERVAL_SECONDS}"
    done
  fi
fi

terminal_state="${terminal_state:-active_or_timeout}"
memory_item_id="$(jq -r '.metadata.canonical_memory_item_id // empty' "${TRACE_DIR}/03_session_after_close.json" 2>/dev/null || true)"

set +e
refresh_session_events_snapshot
events_exit="$?"
set -e
if [[ "${events_exit}" -ne 0 ]]; then
  jq -n \
    --arg session_id "${session_id}" \
    --argjson curl_exit "${events_exit}" \
    '{session_id: $session_id, curl_exit: $curl_exit, error: "session events endpoint unavailable"}' \
    >"${TRACE_DIR}/04_session_events.json"
fi

if [[ "${terminal_state}" == "closed" ]]; then
  wait_for_deliverable_tasks_to_settle || true
fi

if ! capture_json_get_with_backend_recovery \
  "${ACTIVE_BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/artifacts?limit=200&include_content=true&include_preview=true" \
  "${TRACE_DIR}/10_artifact_inventory.json" \
  2 \
  2 \
  "${ARTIFACT_INVENTORY_TIMEOUT_SECONDS}"; then
  jq -n \
    --arg workspace_id "${WORKSPACE_ID}" \
    '{workspace_id: $workspace_id, error: "artifact inventory unavailable", artifacts: []}' \
    >"${TRACE_DIR}/10_artifact_inventory.json"
fi

if [[ -n "${memory_item_id}" ]]; then
  capture_json_get_with_backend_recovery \
    "${ACTIVE_BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/governance/memory/${memory_item_id}" \
    "${TRACE_DIR}/15_governance_memory_detail.json" \
    2 \
    2 \
    "${MEMORY_DETAIL_TIMEOUT_SECONDS}" || \
    jq -n --arg memory_item_id "${memory_item_id}" '{memory_item_id: $memory_item_id, error: "memory detail unavailable"}' \
      >"${TRACE_DIR}/15_governance_memory_detail.json"
fi

if [[ "${terminal_state}" == "closed" ]]; then
  refresh_session_snapshot || true
  refresh_session_events_snapshot || true
fi

refresh_compile_job_snapshot || true
compile_job_status="$(jq -r '.status // empty' "${TRACE_DIR}/02c_compile_job.json" 2>/dev/null || true)"

python3 "${ROOT}/scripts/e2e/validate_longtask_trace_assets.py" \
  --trace-dir "${TRACE_DIR}" \
  --spec "${TRACE_DIR}/00_theme_spec.json" \
  --review-mode "${REVIEW_MODE}"

acceptance_status="$(jq -r '.status // empty' "${TRACE_DIR}/16_acceptance_verdict.json" 2>/dev/null || true)"

write_summary_json

echo "session_id=${session_id}"
echo "memory_item_id=${memory_item_id}"
echo "terminal_state=${terminal_state}"
echo "acceptance_status=${acceptance_status}"
echo "summary=${TRACE_DIR}/summary.json"
