#!/usr/bin/env bash

set -euo pipefail

ROOT="/Users/shock/Projects_local/workspace/mindscape-ai-local-core"
BASE_URL="${BASE_URL:-http://localhost:8200}"
WORKSPACE_ID="${WORKSPACE_ID:-ws-memory-engine-e2e-codex-054234}"
PROFILE_ID="${PROFILE_ID:-default-user}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)_closure_codex}"
TRACE_DIR="${ROOT}/data/e2e-traces/${RUN_ID}/closure"
COMPILE_TIMEOUT_SECONDS="${COMPILE_TIMEOUT_SECONDS:-240}"
SESSION_POLL_INTERVAL_SECONDS="${SESSION_POLL_INTERVAL_SECONDS:-15}"
SESSION_POLL_MAX_ATTEMPTS="${SESSION_POLL_MAX_ATTEMPTS:-24}"
SECRET_KEY="${HANDOFF_BUNDLE_SECRET:-local-e2e-secret-${RUN_ID}}"
MANAGED_BRIDGE_MODE="${MANAGED_BRIDGE_MODE:-0}"
BRIDGE_CLIENT_ID="${BRIDGE_CLIENT_ID:-e2e-codex-${RUN_ID}}"
BRIDGE_PID=""
BRIDGE_LOG="${TRACE_DIR}/00b_bridge_supervisor.log"

PROJECT_ID="proj-e2e-${RUN_ID}"
THREAD_ID="e2e-${RUN_ID}"
HANDOFF_ID="handoff-${RUN_ID}"
SOURCE_DEVICE_ID="e2e-runner-${RUN_ID}"
ATTACHMENT_NAME="partner_brief.md"

mkdir -p "${TRACE_DIR}"

require_bin() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_bin curl
require_bin jq

cleanup() {
  if [[ -n "${BRIDGE_PID}" ]]; then
    kill "${BRIDGE_PID}" 2>/dev/null || true
    wait "${BRIDGE_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

wait_for_backend_ready() {
  local attempts="${1:-20}"
  local delay_seconds="${2:-2}"
  local i
  for i in $(seq 1 "${attempts}"); do
    if curl -fsS --max-time 5 "${BASE_URL}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay_seconds}"
  done
  return 1
}

write_note() {
  local path="$1"
  shift
  cat >"${path}" <<EOF
$*
EOF
}

capture_json_get() {
  local url="$1"
  local out_json="$2"
  curl -sS "${url}" | jq '.' >"${out_json}"
}

echo "run_id=${RUN_ID}"
echo "trace_dir=${TRACE_DIR}"

wait_for_backend_ready 20 2

if [[ "${MANAGED_BRIDGE_MODE}" == "1" ]]; then
  bash "${ROOT}/scripts/start_cli_bridge_supervisor.sh" \
    --surfaces codex_cli \
    --workspace-id "${WORKSPACE_ID}" \
    --host "${BASE_URL#http://}" \
    --client-id "${BRIDGE_CLIENT_ID}" \
    >"${BRIDGE_LOG}" 2>&1 &
  BRIDGE_PID="$!"
  write_note \
    "${TRACE_DIR}/00b_bridge_supervisor.md" \
    "這輪 E2E 由腳本自管一條 supervisor bridge，而不是只依賴 ambient Codex client。" \
    "bridge client_id 固定為 \`${BRIDGE_CLIENT_ID}\`，compile 會顯式把 meeting executor-runtime 綁到這條 bridge。"
fi

capture_json_get \
  "${BASE_URL}/api/v1/mcp/agent/status" \
  "${TRACE_DIR}/00_provider_status.json"

if [[ "${MANAGED_BRIDGE_MODE}" == "1" ]]; then
  for _ in $(seq 1 12); do
    if jq -e --arg ws "${WORKSPACE_ID}" --arg client_id "${BRIDGE_CLIENT_ID}" '
      .workspaces[$ws].clients
      | any(.client_id == $client_id and .surface_type == "codex_cli" and .authenticated == true)
    ' "${TRACE_DIR}/00_provider_status.json" >/dev/null; then
      break
    fi
    sleep 2
    capture_json_get \
      "${BASE_URL}/api/v1/mcp/agent/status" \
      "${TRACE_DIR}/00_provider_status.json"
  done

  write_note \
    "${TRACE_DIR}/00_provider_status.md" \
    "證明這輪 Closure E2E 使用自管 supervisor bridge，而不是只依賴 ambient Codex client。" \
    "這一輪必須在 provider status 中看到 workspace \`${WORKSPACE_ID}\`，且存在 \`client_id=${BRIDGE_CLIENT_ID}\`、\`surface=codex_cli\`、\`authenticated=true\`。"

  jq -e --arg ws "${WORKSPACE_ID}" --arg client_id "${BRIDGE_CLIENT_ID}" '
    .workspaces[$ws].clients
    | any(.client_id == $client_id and .surface_type == "codex_cli" and .authenticated == true)
  ' "${TRACE_DIR}/00_provider_status.json" >/dev/null
else
  write_note \
    "${TRACE_DIR}/00_provider_status.md" \
    "證明這輪 Closure E2E 使用的是既有 workspace，而不是新的隔離 workspace。" \
    "這一輪必須在 provider status 中看到 workspace \`${WORKSPACE_ID}\`，且 client surface 為 \`codex_cli\`、\`authenticated=true\`。"

  jq -e --arg ws "${WORKSPACE_ID}" '
    .workspaces[$ws].clients
    | any(.surface_type == "codex_cli" and .authenticated == true)
  ' "${TRACE_DIR}/00_provider_status.json" >/dev/null
fi

jq -n \
  --arg handoff_id "${HANDOFF_ID}" \
  --arg workspace_id "${WORKSPACE_ID}" \
  --arg source_device_id "${SOURCE_DEVICE_ID}" \
  --arg secret_key "${SECRET_KEY}" \
  --arg run_id "${RUN_ID}" \
  '{
    payload_type: "handoff_in",
    source_device_id: $source_device_id,
    secret_key: $secret_key,
    payload: {
      handoff_id: $handoff_id,
      workspace_id: $workspace_id,
      intent_summary: "請產出 partner_brief.md，摘要合作方向、立即下一步與交付節點，作為 Closure E2E 驗證用小型交付物。",
      goals: [
        "整理合作方向的 3 個關鍵點",
        "列出 2 到 3 個立即下一步",
        "輸出一份可落地保存的 markdown brief"
      ],
      non_goals: [
        "不要展開成大型研究報告",
        "不要產生超出本次 brief 的新專案範圍"
      ],
      deliverables: [
        {
          name: "partner_brief.md",
          mime_type: "text/markdown",
          description: "Closure E2E 驗證用 brief"
        }
      ],
      constraints: {
        action_space: "WRITE_WS",
        max_duration_seconds: 1200
      },
      requested_output_type: "text/markdown",
      human_instructions: "先在 meeting 內完成 deliberation，只有在需要時才外派 execution。最終交付請能落成 artifact 與 memory evidence。",
      metadata: {
        run_id: $run_id,
        e2e_suite: "codex_cli_closure"
      }
    }
  }' >"${TRACE_DIR}/01_package_request.json"

write_note \
  "${TRACE_DIR}/01_package_request.md" \
  "這是 fresh Closure E2E 的 handoff package request。" \
  "它會在 compile 前先產出可驗證簽章的 handoff bundle，並顯式帶同一把 secret，避免 backend 未配置 \`HANDOFF_BUNDLE_SECRET\` 時出現假失敗。"

curl -sS \
  -H 'Content-Type: application/json' \
  --data @"${TRACE_DIR}/01_package_request.json" \
  "${BASE_URL}/api/handoff-bundles/package" \
  | jq '.' >"${TRACE_DIR}/01_package_response.json"

write_note \
  "${TRACE_DIR}/01_package_response.md" \
  "證明 package ingress 可正常產出 signed handoff bundle。" \
  "後續 compile 會直接重用這個 bundle，不再重新建模。"

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
  "這一步走的是正式的 meeting ingress：\`POST /api/handoff-bundles/compile\`。" \
  "project_id 和 thread_id 都是本輪唯一值，避免重用舊 active session 造成判讀污染。"

tmp_body="$(mktemp)"
tmp_headers="$(mktemp)"
set +e
curl -sS \
  -D "${tmp_headers}" \
  -o "${tmp_body}" \
  --max-time "${COMPILE_TIMEOUT_SECONDS}" \
  -H 'Content-Type: application/json' \
  --data @"${TRACE_DIR}/02_compile_request.json" \
  "${BASE_URL}/api/handoff-bundles/compile"
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

write_note \
  "${TRACE_DIR}/02_compile_response.md" \
  "這裡記錄 compile client 的原始結果。新契約下，預期應快速返回 \`202 Accepted\`，而不是同步等完整 compile 跑完。" \
  "若 \`curl_exit=28\`，現在比較像 ingress 本身卡住；若拿到 \`202\`，後續就以 compile job / session state 為主。"

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

write_note \
  "${TRACE_DIR}/02a_compile_acceptance.md" \
  "這一步只看 compile ingress 是否快速交出 \`compile_job_id\` 與 \`session_id\`。" \
  "若兩者都存在，代表已切到 async compile contract；後續不再等待同步 compile body。"

if [[ -n "${compile_job_id}" ]]; then
  capture_json_get \
    "${BASE_URL}/api/handoff-bundles/compile-jobs/${compile_job_id}" \
    "${TRACE_DIR}/02c_compile_job.json"

  write_note \
    "${TRACE_DIR}/02c_compile_job.md" \
    "這是 compile job 的第一個快照。正常情況下應先看到 \`accepted\`，之後再轉成 \`running/succeeded/failed\`。" \
    "它用來證明 compile 真相來源已從同步 HTTP body 轉成 first-class job object。"
fi

capture_json_get \
  "${BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions?limit=50" \
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
    "compile response 沒帶 session_id，session list 也找不到對應 project_id 的 session。" \
    "這代表 meeting ingress 尚未完成到 session 建立層，Closure E2E 在 compile ingress 前半段就失敗了。"
  exit 1
fi

write_note \
  "${TRACE_DIR}/02b_session_lookup.md" \
  "新契約下，session_id 應直接由 compile accepted response 帶回；session list fallback 只用於診斷意外情況。" \
  "後續的 Closure E2E 以 session state 與 artifact/memory 證據為主，不再把 compile response body 當主真相來源。"

poll_log="${TRACE_DIR}/03_session_polls.ndjson"
: >"${poll_log}"
terminal_state=""

for attempt in $(seq 1 "${SESSION_POLL_MAX_ATTEMPTS}"); do
  capture_json_get \
    "${BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions/${session_id}" \
    "${TRACE_DIR}/03_session_after_close.json"

  jq -c --arg polled_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
    {
      polled_at: $polled_at,
      id,
      status,
      round_count,
      ended_at,
      pipeline_stage: (.metadata.pipeline_stage // null),
      pipeline_stage_status: (.metadata.pipeline_stage_status // null),
      canonical_memory_item_id: (.metadata.canonical_memory_item_id // null)
    }
  ' "${TRACE_DIR}/03_session_after_close.json" >>"${poll_log}"

  status="$(jq -r '.status' "${TRACE_DIR}/03_session_after_close.json")"
  if [[ "${status}" == "closed" || "${status}" == "failed" ]]; then
    terminal_state="${status}"
    break
  fi
  sleep "${SESSION_POLL_INTERVAL_SECONDS}"
done

write_note \
  "${TRACE_DIR}/03_session_after_close.md" \
  "這是 compile 後真正的 backend session 快照。" \
  "判讀重點是 session 是否 closed、action_items 是否帶 execution_id，以及 metadata 是否已出現 canonical memory 與 impact trace。"

set +e
curl -sS \
  --max-time 30 \
  "${BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/meeting-sessions/${session_id}/events" \
  | jq '.' >"${TRACE_DIR}/04_session_events.json"
events_exit="$?"
set -e

if [[ "${events_exit}" -eq 0 ]]; then
  write_note \
    "${TRACE_DIR}/04_session_events.md" \
    "這份 event stream 用來查驗 deliberation、dispatch、finalize、writeback 的可觀測痕跡。" \
    "若 session 未閉環，這裡也應保留最後一段已發生的 event，不可以只看最終狀態。"
else
  jq -n \
    --arg session_id "${session_id}" \
    --argjson curl_exit "${events_exit}" \
    '{session_id: $session_id, curl_exit: $curl_exit, error: "session events endpoint unavailable"}' \
    >"${TRACE_DIR}/04_session_events.json"
  write_note \
    "${TRACE_DIR}/04_session_events.md" \
    "session events endpoint 這輪沒有成功返回，所以這裡記錄的是未抵達狀態。" \
    "這種情況不能拿空白當作沒有事件，而要保留 endpoint 失敗本身的證據。"
fi

execution_id="$(jq -r '
  (.action_items[0].execution_id // .metadata.execution_ids[0] // empty)
' "${TRACE_DIR}/03_session_after_close.json")"
memory_item_id="$(jq -r '.metadata.canonical_memory_item_id // empty' "${TRACE_DIR}/03_session_after_close.json")"

if [[ "${terminal_state}" == "closed" && -n "${execution_id}" ]]; then
  jq -n \
    --arg execution_id "${execution_id}" \
    --arg output "# Partner Brief\n\n## 合作方向\n- 以受治理記憶與 deliberation 可觀測性作為 partner demo 主軸。\n- 第一階段先證明 meeting -> execution -> artifact -> memory 的閉環。\n- 對外敘事只保留已驗證能力與下一步路線。\n\n## 立即下一步\n1. 釘住 closure e2e 的正式報告。\n2. 補 readback e2e 驗證上一輪記憶回送。\n3. 清理 compile ingress 的同步長請求風險。\n" \
    --arg attachment_name "${ATTACHMENT_NAME}" \
    '{
      execution_id: $execution_id,
      result_data: {
        status: "completed",
        output: $output,
        result_json: {
          progress: {
            percent: 100,
            label: "closure e2e synthetic completion"
          },
          metadata: {
            source: "run_codex_cli_closure_trace.sh",
            e2e: true
          }
        },
        attachments: [
          {
            filename: $attachment_name,
            content: $output,
            mime_type: "text/markdown"
          }
        ]
      }
    }' >"${TRACE_DIR}/05_completion_request.json"

  write_note \
    "${TRACE_DIR}/05_completion_request.md" \
    "這是 synthetic completion payload，用來驗證 execution result landing 與 artifact 生成。" \
    "它故意帶 progress 與 markdown attachment，讓 progress snapshot 和 landed artifact 都有可觀測內容。"

  curl -sS \
    -H 'Content-Type: application/json' \
    --data @"${TRACE_DIR}/05_completion_request.json" \
    "${BASE_URL}/api/v1/mcp/agent/result" \
    | jq '.' >"${TRACE_DIR}/05_completion_response.json"

  capture_json_get \
    "${BASE_URL}/api/v1/mcp/agent/result/${execution_id}" \
    "${TRACE_DIR}/06_landed_result.json"

  write_note \
    "${TRACE_DIR}/06_landed_result.md" \
    "這一步證明 execution result 已經 landed 成 storage/artifact 可讀結果。" \
    "若 attachment index 裡有 partner_brief.md，表示執行輸出確實已落成資產，而不是只停留在 task.result。"

  capture_json_get \
    "${BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/executions/${execution_id}/progress-snapshot" \
    "${TRACE_DIR}/07_progress_snapshot.json"

  write_note \
    "${TRACE_DIR}/07_progress_snapshot.md" \
    "progress snapshot 反證 landed artifact 內容可以被下游 UI/debug 讀回。" \
    "這一步不是重看 task 狀態，而是檢查 artifact content 的 progress 是否真的可回讀。"

  capture_json_get \
    "${BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/governance/memory" \
    "${TRACE_DIR}/08_memory_list.json"

  if [[ -n "${memory_item_id}" ]]; then
    capture_json_get \
      "${BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/governance/memory/${memory_item_id}" \
      "${TRACE_DIR}/09_memory_detail.json"

    capture_json_get \
      "${BASE_URL}/api/v1/workspaces/${WORKSPACE_ID}/governance/memory-impact-graph?session_id=${session_id}" \
      "${TRACE_DIR}/10_memory_impact_graph.json"
  fi
fi

jq -n \
  --arg run_id "${RUN_ID}" \
  --arg workspace_id "${WORKSPACE_ID}" \
  --arg project_id "${PROJECT_ID}" \
  --arg thread_id "${THREAD_ID}" \
  --arg session_id "${session_id}" \
  --arg execution_id "${execution_id}" \
  --arg memory_item_id "${memory_item_id}" \
  --arg terminal_state "${terminal_state}" \
  --arg trace_dir "${TRACE_DIR}" \
  '{
    run_id: $run_id,
    workspace_id: $workspace_id,
    project_id: $project_id,
    thread_id: $thread_id,
    session_id: $session_id,
    execution_id: $execution_id,
    memory_item_id: $memory_item_id,
    terminal_state: $terminal_state,
    trace_dir: $trace_dir
  }' >"${TRACE_DIR}/summary.json"

echo "session_id=${session_id}"
echo "execution_id=${execution_id}"
echo "memory_item_id=${memory_item_id}"
echo "terminal_state=${terminal_state:-active_or_timeout}"
echo "summary=${TRACE_DIR}/summary.json"
