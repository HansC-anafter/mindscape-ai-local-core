#!/usr/bin/env bash

set -euo pipefail

ROOT="/Users/shock/Projects_local/workspace/mindscape-ai-local-core"
BASE_URL="${BASE_URL:-http://localhost:8200}"
CONTAINER_BASE_URL="${CONTAINER_BASE_URL:-http://127.0.0.1:8200}"
HTTP_TRANSPORT="${HTTP_TRANSPORT:-auto}"
BACKEND_CONTAINER_NAME="${BACKEND_CONTAINER_NAME:-mindscape-ai-local-core-backend}"
BACKEND_READY_ATTEMPTS="${BACKEND_READY_ATTEMPTS:-60}"
BACKEND_READY_DELAY_SECONDS="${BACKEND_READY_DELAY_SECONDS:-2}"
HEALTH_MAX_TIME_SECONDS="${HEALTH_MAX_TIME_SECONDS:-5}"
RUN_E2E="${RUN_E2E:-0}"
REQUIRE_CLOSED="${REQUIRE_CLOSED:-1}"
REQUIRE_DYNAMIC_ROUTING="${REQUIRE_DYNAMIC_ROUTING:-0}"
AGENT_STATUS_REQUIRED="${AGENT_STATUS_REQUIRED:-0}"
HTTP_TRANSPORT_SELECTED=""
ACTIVE_BASE_URL="${BASE_URL}"
PYTHON_BIN_RESOLVED=""

PYTEST_TARGETS=(
  "${ROOT}/backend/tests/routes/core/handoff_bundles_api_test.py"
  "${ROOT}/backend/tests/routes/core/meeting_compile_job_projection_api_test.py"
  "${ROOT}/backend/tests/services/compile_job_store_stream_events_test.py"
  "${ROOT}/backend/tests/services/compile_job_reconciler_test.py"
  "${ROOT}/backend/tests/services/orchestration/meeting/test_round_router.py"
  "${ROOT}/backend/tests/services/orchestration/meeting/test_engine_pipeline_diagnostics.py"
  "${ROOT}/backend/tests/services/orchestration/meeting/test_workflow_evidence_prompt_context.py"
  "${ROOT}/backend/tests/services/orchestration/meeting/test_session_memory_linkage.py"
  "${ROOT}/backend/tests/services/orchestration/meeting/test_wave_closure_trace_validator.py"
  "${ROOT}/backend/tests/services/test_handoff_bundle_service.py"
)

select_python_bin() {
  local requested="${PYTHON_BIN:-}"
  local candidates=()

  if [[ -n "${requested}" ]]; then
    candidates+=("${requested}")
  fi

  candidates+=(
    "python3"
    "python"
    "/opt/miniconda3/bin/python3"
    "/opt/miniconda3/bin/python"
  )

  local candidate=""
  for candidate in "${candidates[@]}"; do
    if [[ -z "${candidate}" ]]; then
      continue
    fi
    if ! command -v "${candidate}" >/dev/null 2>&1; then
      continue
    fi
    if "${candidate}" -m pytest --version >/dev/null 2>&1; then
      PYTHON_BIN_RESOLVED="${candidate}"
      return 0
    fi
  done

  echo "[wave-closure] failed to resolve a Python interpreter with pytest available" >&2
  exit 2
}

select_python_bin
echo "[wave-closure] python bin: ${PYTHON_BIN_RESOLVED}"

echo "[wave-closure] running targeted pytest suite"
PYTHONPATH="${ROOT}" "${PYTHON_BIN_RESOLVED}" -m pytest -q "${PYTEST_TARGETS[@]}"

if [[ "${RUN_E2E}" != "1" ]]; then
  echo "[wave-closure] skipping fresh E2E run (set RUN_E2E=1 to enable)"
  exit 0
fi

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
      echo "[wave-closure] unsupported transport activation: ${1}" >&2
      exit 2
      ;;
  esac
}

probe_transport_health() {
  local transport="$1"
  if [[ "${transport}" == "backend_container" ]]; then
    docker exec "${BACKEND_CONTAINER_NAME}" curl -fsS -m "${HEALTH_MAX_TIME_SECONDS}" "${CONTAINER_BASE_URL}/health" >/dev/null 2>&1
    return $?
  fi

  curl -fsS -m "${HEALTH_MAX_TIME_SECONDS}" "${BASE_URL}/health" >/dev/null 2>&1
}

maybe_failover_transport() {
  local previous_transport="${HTTP_TRANSPORT_SELECTED:-}"
  local target_transport=""

  if [[ "${HTTP_TRANSPORT}" != "auto" ]]; then
    return 1
  fi

  case "${previous_transport}" in
    host)
      target_transport="backend_container"
      ;;
    backend_container)
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
  echo "[wave-closure] transport failover: ${previous_transport} -> ${target_transport}" >&2
  return 0
}

is_truthy() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

read_backend_env_var() {
  local name="$1"
  docker exec "${BACKEND_CONTAINER_NAME}" sh -lc "printf '%s' \"\${${name}:-}\""
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
        if curl -fsS -m "${HEALTH_MAX_TIME_SECONDS}" "${BASE_URL}/health" >/dev/null 2>&1; then
          activate_transport "host"
          return 0
        fi
        if docker exec "${BACKEND_CONTAINER_NAME}" curl -fsS -m "${HEALTH_MAX_TIME_SECONDS}" "${CONTAINER_BASE_URL}/health" >/dev/null 2>&1; then
          activate_transport "backend_container"
          return 0
        fi
        sleep "${BACKEND_READY_DELAY_SECONDS}"
      done
      echo "[wave-closure] backend health preflight failed via host and backend_container transport after ${BACKEND_READY_ATTEMPTS} attempts" >&2
      exit 2
      ;;
    *)
      echo "[wave-closure] unsupported HTTP_TRANSPORT=${HTTP_TRANSPORT}" >&2
      exit 2
      ;;
  esac
}

transport_curl() {
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

wait_for_selected_transport_health() {
  local attempt=""
  for attempt in $(seq 1 "${BACKEND_READY_ATTEMPTS}"); do
    if transport_curl -fsS -m "${HEALTH_MAX_TIME_SECONDS}" "${ACTIVE_BASE_URL}/health" >/dev/null; then
      return 0
    fi
    sleep "${BACKEND_READY_DELAY_SECONDS}"
  done

  echo "[wave-closure] backend health preflight failed via ${HTTP_TRANSPORT_SELECTED} transport after ${BACKEND_READY_ATTEMPTS} attempts" >&2
  exit 2
}

select_http_transport
echo "[wave-closure] http transport: ${HTTP_TRANSPORT_SELECTED}"
echo "[wave-closure] active base url: ${ACTIVE_BASE_URL}"

echo "[wave-closure] preflight backend health"
wait_for_selected_transport_health

echo "[wave-closure] preflight agent status"
if ! transport_curl -fsS -m 5 "${ACTIVE_BASE_URL}/api/v1/mcp/agent/status" >/dev/null; then
  if [[ "${AGENT_STATUS_REQUIRED}" == "1" ]]; then
    echo "[wave-closure] agent status preflight failed and AGENT_STATUS_REQUIRED=1" >&2
    exit 2
  fi
  echo "[wave-closure] agent status preflight failed; continuing in advisory mode" >&2
fi

if [[ "${REQUIRE_DYNAMIC_ROUTING}" == "1" ]]; then
  dynamic_routing_enabled="$(read_backend_env_var "MEETING_DYNAMIC_ROUTING_ENABLED" 2>/dev/null || true)"
  dynamic_routing_trace_enabled="$(read_backend_env_var "MEETING_DYNAMIC_ROUTING_TRACE_ENABLED" 2>/dev/null || true)"
  if ! is_truthy "${dynamic_routing_enabled}" && ! is_truthy "${dynamic_routing_trace_enabled}"; then
    echo "[wave-closure] dynamic routing required, but backend env flags are both disabled or unset" >&2
    echo "[wave-closure] set MEETING_DYNAMIC_ROUTING_ENABLED=true (optionally MEETING_DYNAMIC_ROUTING_TRACE_ENABLED=true) in .env, then restart backend" >&2
    exit 2
  fi
fi

echo "[wave-closure] running fresh closure trace"
run_log="$(mktemp)"
trap 'rm -f "${run_log}"' EXIT
set +e
HTTP_TRANSPORT="${HTTP_TRANSPORT_SELECTED}" \
bash "${ROOT}/scripts/e2e/run_codex_cli_closure_trace.sh" | tee "${run_log}"
trace_exit="${PIPESTATUS[0]}"
set -e

summary_path="$(awk -F= '/^summary=/{print $2}' "${run_log}" | tail -n 1)"
trace_dir_from_log="$(awk -F= '/^trace_dir=/{print $2}' "${run_log}" | tail -n 1)"
if [[ -z "${summary_path}" ]]; then
  echo "[wave-closure] failed to resolve summary.json path from closure trace output" >&2
  exit 1
fi
if [[ -z "${trace_dir_from_log}" && -f "${summary_path}" ]]; then
  trace_dir_from_log="$(cd "$(dirname "${summary_path}")" && pwd)"
fi
if [[ -z "${trace_dir_from_log}" || ! -d "${trace_dir_from_log}" ]]; then
  echo "[wave-closure] failed to resolve trace_dir from closure trace output" >&2
  exit 1
fi

trace_dir="$("${PYTHON_BIN_RESOLVED}" - "${summary_path}" "${trace_dir_from_log}" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
fallback_trace_dir = sys.argv[2]

if summary_path.is_file():
    raw = summary_path.read_text(encoding="utf-8").strip()
    if raw:
        payload = json.loads(raw)
        trace_dir = payload.get("trace_dir")
        if trace_dir:
            print(trace_dir)
            raise SystemExit(0)

print(fallback_trace_dir)
PY
)"

if [[ "${trace_exit}" -ne 0 ]]; then
  echo "[wave-closure] fresh closure trace exited with code ${trace_exit}; continuing to validator using trace_dir=${trace_dir}" >&2
fi

validator_cmd=(
  "${PYTHON_BIN_RESOLVED}"
  "${ROOT}/scripts/e2e/validate_meeting_wave_closure.py"
  --trace-dir "${trace_dir}"
  --write-report "${trace_dir}/closure_validation.json"
)

if [[ "${REQUIRE_CLOSED}" == "1" ]]; then
  validator_cmd+=(--require-closed)
fi

if [[ "${REQUIRE_DYNAMIC_ROUTING}" == "1" ]]; then
  validator_cmd+=(--require-dynamic-routing)
fi

echo "[wave-closure] validating trace artifacts"
"${validator_cmd[@]}"
