# Execution Governance 實作對齊與查驗報告（2026-03-27）

## Findings
1. **`local-core` 目前仍維持 runtime adapter 邊界，沒有因 control-plane 實作而反向吸收 `site-hub` owner 責任**：`dispatch_remote_execution()` 已收斂成 thin wrapper，真正的本地 shell 建立與 generic dispatch contract 在 `RemoteExecutionLaunchService`，而 `CloudConnector` 只負責傳送 `execution_id / trace_id / job_type / callback_payload / site_key` 這類 control-plane 契約。這批變更沒有把 `site-hub` 的 DB schema、migration、owner-side callback persistence 拉進 `local-core`。 (E1, E2)
2. **`site-hub` 已具備 owner-side execution governance callback 欄位、API 與 rollout 路徑**：`ExecutionControlService` 會建立 `callback_payload`、提供 runtime availability、在 terminal callback 後記錄 `callback_delivered_at / callback_error`；`ExecutionResponse` / `ExecutionResultResponse` 也已把這些欄位序列化出去；ORM 與 migration/runbook 都已補齊。 (E3, E4, E5)
3. **failure-path live smoke 已證明 `local-core -> site-hub -> executor -> callback -> local-core` 閉環成立**：VM 上 `site-hub` 的 execution result 仍能查到 `failed` 狀態與非空的 `callback_delivered_at`；同一筆 execution 在本機 `local-core` task store 也已落成 `failed`，並帶回 `cloud_dispatch_state / capability_code / error`。 (E7, E8)
4. **callback delivery metadata 的 authoritative truth 目前仍主要留在 `site-hub` result API，尚未完整 mirror 進 root execution 的 `local-core` task context**：`site-hub` 在回打 `local-core` 時送出的 `provider_metadata` 目前只有 `site_hub_state / device_id`；另一方面，`local-core` 的 governance/projection 路徑已支援消化 `callback_delivered_at / callback_error`。這代表能力已補在 consumer 端，但 live root-callback path 還沒有把 timestamp 餵回 `local-core` task。 (E2, E3, E7, E8)
5. **本次候選提交檔案已符合語言與註釋規則，且 targeted 驗證已過**：依 `mindscape-dev-guide` / `commit-push` 規範，程式註釋與 docstring 必須英文、`docs-internal/` 必須繁中、`docs/` 必須英文。本輪對候選檔案做了 CJK / emoji / timeline / `TODO|FIXME` 掃描，結果 0 命中；`git diff --check` 與 `py_compile` 也通過；`local-core` targeted pytest 共 `22 passed`，`site-hub` targeted pytest `10 passed`。 (E6, E9, E10, E11, E12, E13, E14)

## Evidence Register
| ID | Type | Source | Finding |
|---|---|---|---|
| E1 | Code | [execution_dispatch.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/execution_dispatch.py#L68), [remote_execution_launch_service.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/remote_execution_launch_service.py#L17) | `local-core` 路由層只做 delegation；本地 shell 建立、ID 正規化、dispatch error handling 都封裝在 `RemoteExecutionLaunchService`。 |
| E2 | Code | [cloud_connector.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/cloud_connector.py#L71), [connector.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/cloud_connector/connector.py#L576), [governance_engine.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py#L331), [task_execution_projection.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/task_execution_projection.py#L18), [remote_route.py](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow/remote_route.py#L306) | `local-core` 只傳 generic control-plane contract，並在 polling / governance / projection seam 支援 callback metadata 消化，不含 owner-side persistence。 |
| E3 | Code | [execution_control_service.py](/Users/shock/Projects_local/workspace/site-hub/site-hub-api/v1/services/execution_control_service.py#L29), [local_core_relay.py](/Users/shock/Projects_local/workspace/site-hub/site-hub-api/v1/local_core_relay.py#L533), [local_core_client.py](/Users/shock/Projects_local/workspace/site-hub/site-hub-api/v1/services/local_core_client.py#L11) | `site-hub` service 端已擁有 runtime availability、callback delivery record、terminal callback 回打 `local-core` 的 owner-side 行為。 |
| E4 | Code | [execution_control.py](/Users/shock/Projects_local/workspace/site-hub/site-hub-api/v1/execution_control.py#L27), [operations.py](/Users/shock/Projects_local/workspace/site-hub/site-hub-common/site_hub_common/database/models/operations.py#L64) | `site-hub` API 與 ORM 已把 `callback_payload / callback_delivered_at / callback_error` 升成正式欄位與 response schema。 |
| E5 | Code/Doc | [20260326_add_execution_callback_fields.py](/Users/shock/Projects_local/workspace/site-hub/site-hub-registry-api/alembic/versions/20260326_add_execution_callback_fields.py#L1), [execution-governance-rollout-2026-03-26.md](/Users/shock/Projects_local/workspace/site-hub/docs/implementation/execution-governance-rollout-2026-03-26.md#L1) | `site-hub` migration 會回填 legacy `_governance.callback_payload`，runbook 也已把 rollout root、success criteria 與 redlines 講清楚。 |
| E6 | Rule | [mindscape-dev-guide/SKILL.md](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/skills/mindscape-dev-guide/SKILL.md#L140), [commit-push/SKILL.md](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/skills/commit-push/SKILL.md#L98) | 開發與提交規範要求：程式註釋/docstring 英文、`docs-internal/` 繁中、`docs/` 英文，禁止中文註釋、emoji、步驟紀錄與非功能性描述。 |
| E7 | Runtime | `ssh bitnami@107.167.189.225 'curl -sS "http://127.0.0.1:8102/api/v1/executions/b4685813-8878-4a5f-8208-e8d870d63e06/result?tenant_id=vm-smoke-tenant"'` | VM `site-hub` 回傳 `state=failed`、`error_message="tool_name is required for tool execution"`、`callback_delivered_at="2026-03-26T12:57:43.784651"`、`callback_error=null`。 |
| E8 | Runtime | `docker exec -i mindscape-ai-local-core-backend python -c "from app.services.stores.tasks_store import TasksStore; task=TasksStore().get_task_by_execution_id('b4685813-8878-4a5f-8208-e8d870d63e06'); print('TASK_STATUS', getattr(task.status, 'value', task.status)); print('TASK_REMOTE', task.execution_context.get('remote_execution', {}))"` | 同一筆 execution 在 `local-core` 已落成 `TASK_STATUS failed`，並記有 `cloud_dispatch_state=failed`、`capability_code=core_llm`、`error="tool_name is required for tool execution"`；但未鏡像 `callback_delivered_at`。 |
| E9 | Test | `pytest -q /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/routes/core/test_remote_execution_launch.py /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/routes/core/test_remote_execution_callbacks.py` | `7 passed`，證明 launch shell 建立與 terminal callback bridge 的 local-core 主要 route regression 通過。 |
| E10 | Test | `pytest -q /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_task_execution_projection.py /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_workflow_orchestrator_remote_tool_routes.py` | `13 passed`，證明 projection 與 workflow remote-route 的 callback metadata / child sync 相關路徑仍通。 |
| E11 | Test | `PYTHONPATH=/Users/shock/Projects_local/workspace/mindscape-ai-local-core:/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend pytest -q /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/test_cloud_connector_terminal_result.py` | `2 passed`，證明 `CloudConnector.wait_for_remote_execution_terminal_result()` 的 callback metadata extraction regression 通過。 |
| E12 | Test | `PYTHONPATH=/Users/shock/Projects_local/workspace/site-hub/site-hub-api:/Users/shock/Projects_local/workspace/site-hub/site-hub-common pytest -q /Users/shock/Projects_local/workspace/site-hub/site-hub-api/tests/test_execution_control.py` | `10 passed`，證明 `site-hub` execution-control、callback persistence、result serialization regression 通過。 |
| E13 | Search | `rg -n "TODO|FIXME|[一-龥]|[😀-🙏]|Step [0-9]|DONE|Phase [0-9]|M[0-9]" <curated candidate files>` returned 0 matches | 候選程式檔目前沒有中文註釋、emoji、timeline 記錄或 `TODO/FIXME` 殘留。 |
| E14 | Diff/Compile | `git -C /Users/shock/Projects_local/workspace/mindscape-ai-local-core diff --check -- <local-core curated files>` and `git -C /Users/shock/Projects_local/workspace/site-hub diff --check -- <site-hub curated files>` returned 0 findings; `python3 -m py_compile <curated python files>` returned 0 errors | 候選提交檔案沒有 whitespace / patch hygiene 問題，且 Python 語法可編譯。 |

## Verification Notes
- 這輪查驗先補讀 [mindscape-dev-guide/SKILL.md](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/skills/mindscape-dev-guide/SKILL.md) 與 [commit-push/SKILL.md](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/skills/commit-push/SKILL.md)，再決定候選 commit 範圍與註釋清理策略，避免先 commit 再回頭返工。
- `site-hub-common/site_hub_common/database/models/operations.py` 與 `site-hub-registry-api/alembic/versions/20241201_144000_add_indexes.py` 原本帶有中文註釋 / docstring；本輪已清為英文功能性描述後再進行合規掃描。
- `test_cloud_connector_terminal_result.py` 第一次執行因 `PYTHONPATH` 未帶入而 collection fail；補上 `PYTHONPATH=/Users/shock/Projects_local/workspace/mindscape-ai-local-core:/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend` 後，`2 passed`。
- live smoke 目前驗到的是 failure-path closure；成功路徑與 GPU VM executor smoke 仍未在本輪重跑。

## Open Questions
- root execution 的 callback delivery timestamp 是否要同步 mirror 到 `local-core` task context？目前 authoritative truth 在 `site-hub` result API，`local-core` task 只反映 execution state / error。
- GPU VM success-path smoke 仍待重跑；目前只有 failure-path live smoke 作為跨 repo 閉環證據。
- `mindscape-ai-cloud` execution bridge 的 decommission 變更是否另開獨立提交，仍需與這次 `local-core + site-hub` owner-path commit 分開處理。

## Next Actions
1. 以顯式檔案清單提交本次 `local-core + site-hub` execution-governance 對齊變更，不混入兩個 repo 內其他 dirty changes。
2. 若要讓 `local-core` UI 直接顯示 root execution 的 callback delivery timestamp，需決定是否在 `site-hub -> local-core` callback payload 另補 mirror 資訊，或改由 local-core 查 owner-side result API。
3. 在 owner-side rollout 穩定後補跑 GPU VM success-path smoke，再決定是否進入 `mindscape-ai-cloud` execution bridge decommission 的正式提交。

## Fix Verification
1. 已完成候選程式檔的 CJK / emoji / timeline / `TODO|FIXME` 掃描，結果 0 命中。 (E13)
2. 已完成候選程式檔的 `git diff --check` 與 `py_compile`，結果 0 finding / 0 error。 (E14)
3. 已完成 `local-core` route-level targeted pytest，結果 `7 passed`。 (E9)
4. 已完成 `local-core` projection / remote-route targeted pytest，結果 `13 passed`。 (E10)
5. 已完成 `local-core` connector terminal-result targeted pytest，結果 `2 passed`。 (E11)
6. 已完成 `site-hub` execution-control targeted pytest，結果 `10 passed`。 (E12)
7. 已重新查驗 VM `site-hub` result endpoint 與本機 `local-core` task store，failure-path live smoke 仍閉環。 (E7, E8)
