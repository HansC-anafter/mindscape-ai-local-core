# AOL 到 MeetingEngine 編排橋接 P0 實作計劃

## 使用者原始指令對齊

本計劃 P0 gate 直接對齊以下使用者原始指令。後續驗收不得只用摘要替代，也不得把 direct object-action、direct playbook dispatch 誤認為已完成 meeting-led orchestration。

1. `我的 meeting session 的最初設計目標是透過 meeting graph node 的模式，一方面實現 ai 輔助引導用戶知道當前應該做什麼，比如在 pd pack 引導用戶如何進行全鏈路的導演思維調動影視工作流進行生成創作、一方面實現 ai 輔助引導的工具可調用工作流`
2. `使用這幾張 ig refs @xxxxx @oooooo 構思一組 90s reels 分鏡並完成分鏡圖製作。`
3. `我又如何在 pd pack 邊使用 aol shell 透過 meeting 討論每一個分鏡的引導創作？？？（這更是這一次設計 pd pack 結合 aol meeting graph shell 的更原始設計意圖！！！）`
4. `我要求的兩條 e2e 走線，和路徑資產入庫、入檔，是否列為計劃最開頭的 checklist true / false  清單？`

## P0 True / False Checklist

| Gate | 計劃列入 | 目前已實作 | 完成驗收證據 |
|---|---:|---:|---|
| 跨 pack object refs → MeetingEngine → downstream dispatch transport：`@owner.kind:{sourceA}`、`@owner.kind:{sourceB}` 進 `route_meeting_orchestration`，由 `MeetingEngine.run()` 產生 TaskIR 與 pack dispatch | true | true | Fresh post-restart E2E `cmd_aol_real_e2e_files_20260504_021_tasklineage` proves selected IG refs enter `route_meeting_orchestration`, MeetingEngine persists request-contract AOL metadata, produces TaskIR `task_f385ff20d3364399`, dispatches `performance_direction/pd_storyboard_gen`, and returns `artifact_landing_status=landed` with three concrete output file paths. Evidence file: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-real-file-e2e-evidence-2026-05-04.md`. |
| 原始指令 #2：用多個 IG refs 構思一組 `90s reels` 分鏡 | true | true | `_021` manifest verifies `scene_count=9`, `total_duration_sec=90`, selected source refs `codex_aol_e2e_ref_a_20260503` / `codex_aol_e2e_ref_b_20260503`, and `render_profile.profile_id=pd_vertical_reels_storyboard`. |
| 原始指令 #2：完成分鏡圖製作，且 storyboard image / frame artifacts 入庫入檔 | true | true | `_021` produced a contact-sheet SVG image artifact plus per-scene `scene_manifest.storyboard_frame` entries. DB/file evidence: image artifact `42e2c149-3c1e-42eb-aa58-d472437a55af`, proposal `18420a74-86c5-4853-923a-1753c8ca8bb9`, manifest `632f963a-a209-4a7e-b478-da165f2da2a2`; `file` identifies the SVG as `SVG Scalable Vector Graphics image`, proposal as UTF-8 text, manifest as JSON data. |
| Pack-owned object discussion → MeetingEngine guidance E2E：`@owner.kind:{object_id}` 進 `route_meeting_orchestration`，由 MeetingEngine 產生 guidance/action/review 節點，並可在 PD pack 內逐分鏡討論 | true | true | `_021` proves pack-owned per-scene review carriers: every scene has `meeting_discussion_prompt`, `decision_items`, `review_candidates`, and `approval_state=needs_review`. This run does not claim a human completed the review decisions; it proves the AOL/Meeting/PD artifact carrier needed for per-scene discussion. |
| 資產入庫：storyboard/proposal/artifact 必須寫入 artifacts DB，而不是只存在 pack response 或前端 fixture | true | true | `_021` execution `7ba39e58-e19f-4113-b8db-5547558e26bd` produced three artifacts table rows. All rows have `thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1`, `task_id=task_f385ff20d3364399`, `metadata.acceptance_evidence`, `metadata.pd_storyboard_evidence`, and `metadata.provenance.eval_summary.passed=true`. |
| 資產入檔：artifact 必須帶可解析 file path，而不是只在 DB metadata 放空殼 | true | true | `_021` command response and DB rows include `metadata.actual_file_path` for contact-sheet SVG, proposal Markdown, and manifest JSON under `/app/data/sandboxes/.../current/artifacts/pd_storyboard_gen/7ba39e58-e19f-4113-b8db-5547558e26bd/`; host `file` and `xxd` checks verify real SVG/Markdown/JSON bytes. |
| UX/UI 編排補全：AOL runtime graph 繼承既有 Workbench 骨架，但必須補出 MeetingEngine 編排狀態，不得只沿用 direct dispatch UI | true | true | Backend API now returns `dispatch_result.meeting_orchestration`; frontend targeted vitest passed: `meetingCommandLedger.spec.ts`, `AOLMeetingBottomShellDispatch.spec.tsx`, `AOLMeetingBottomShellLayout.spec.tsx`, `meetingGraphProjection.spec.ts` = 4 files / 26 tests. Live data lane evidence: `GET /artifacts?thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1&limit=3` returns the `_021` contact-sheet/proposal/manifest artifacts. |
| workspace `codex_cli` host bridge 常駐與自動復活 | true | true | 2026-05-04 runtime audit found LaunchAgent `ai.mindscape.cli-bridge` loaded, then fixed `start_cli_bridge.sh` workspace-removal debounce and bash helper handling. Controlled kill test: PID `18082` was killed; watcher logged `Bridge PID 18082 ... died, will respawn` and started PID `21617`, which connected and registered. Evidence file: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-host-bridge-runtime-evidence-2026-05-04.md`. |
| local-core runtime 不得硬寫 PD/pack-specific storyboard evidence 規則 | true | true | Core runtime search `rg -n "pd_storyboard_evidence|storyboard_preview|selected_scene_package_selector" backend/app/services backend/app/models backend/tests` returned no matches. Pack-specific `pd_storyboard_evidence` and `storyboard_preview` evidence is emitted by `capabilities/performance_direction` and only carried through generic artifact metadata. |

### 0.0.1 本次查驗新增缺口：PD storyboard URL identity

2026-05-04 查驗結論：PD 目前沒有對「各別 storyboard instance」設計唯一 project URL。現況只有 session-scoped workbench route `/workspaces/{workspace_id}/capabilities/performance_direction/sessions/{session_id}`、latest canonical storyboard API `/api/v1/capabilities/performance_direction/sessions/{session_id}/storyboard`、以及 proposal review route。`_021` 落檔 manifest 的 `storyboard_id=sb_a75480dadd93` 沒有 `canonical_storyboard_route`；artifacts DB rows 也沒有可指向該 storyboard instance 的 `navigate_to`。因此不得把「per-storyboard unique project URL」列為已完成能力；後續若要補，應由 PD pack / web-console route 層新增 `storyboard_id` identity route 或 query contract，local-core 只保存 generic artifact/thread/task metadata，不得加入 PD-specific URL 規則。

本文件是 2026-05-03 的 P0 修正計劃。目的不是新增 IG/PD 業務邏輯，而是把 AOL Runtime Shell 的 command、object refs、graph guidance、relations、pack affordances 轉成 MeetingEngine 編排契約，讓 MeetingEngine 成為任務目的理解、跨 pack workflow 組裝、ActionIntent、TaskIR、dispatch、memory、review trace 的中樞。

## 0. 修訂狀態

本版已根據 `aol-to-meeting-engine-orchestration-bridge-verification-report-2026-05-03.md` 修訂。開工條件：先完成本節列出的 P0 級硬性實作 gate。

本次查驗後的狀態：本版將 P0 收斂為單一產品實作路徑，所有 change block 必須對應到唯一檔案、唯一函式/class、唯一資料 carrier、唯一驗收命令。

2026-05-03 補全修訂：本版新增 selected guidance carrier、frontend orchestration response contract、MeetingEngine runner dependency map、session metadata persistence、artifact DB/file landing path、runtime readiness gate、以及外部內容平台/agent orchestration 對齊 gate。若這些 gate 未完成，不得把本計劃標為可開工 P0。

2026-05-03 實作收尾狀態：local-core source path 已落地 `AOLMeetingOrchestrationBridge`、`MeetingEngineRunner`、command ledger `route_meeting_orchestration` routing、`handoff_in.metadata["addressable_object_layer"]` merge、selected guidance metadata carrier、frontend `meeting_orchestration` response handling、TaskIR artifact DB landing、downstream dispatch artifact reconciliation、Ollama health readiness、optional OCR health semantics、bounded MeetingEngine command timeout、cross-worker agent dispatch ACK deadline/fallback、late external-agent result correlation、graph command orchestration metadata projection，以及 explicit direct-route override gate。Verification rerun: `git diff --check` clean；targeted backend pytest suite `34 passed, 163 warnings`；targeted web-console vitest suite `4 passed, 17 tests passed`；post-fix runner/timeout/reconciliation subset `6 passed, 156 warnings`。

Live control/execution backend 已重啟並載入本輪修正：`GET http://localhost:8220/healthz` returns `{"status":"ok","backend_role":"control","reload_enabled":true}`；`GET http://localhost:8200/healthz` returns `{"status":"ok","backend_role":"execution","reload_enabled":false}`；Docker reports `mindscape-ai-local-core-backend` and `mindscape-ai-local-core-backend-control` healthy。`GET http://localhost:8220/health` reports `status=healthy`, `llm_configured=true`, `llm_available=true`, `llm_provider=ollama`, `ocr_service=disabled`, `issues=[]`。`GET http://localhost:8220/api/v1/capability-packs/` proves `ig` and `performance_direction` are installed/enabled and validation succeeded；`GET http://localhost:8200/api/v1/mcp/agent/status` proves target workspace `bac7ce63-e768-454d-96f3-3a00e8e1df69` has authenticated `codex_cli-bac7ce63-e768-454d-96f3-3a00e8e1df69-43b0a0a4a97a`。

Live smoke result is intentionally split: command `cmd_aol_late_reconcile_smoke_20260503` proves MeetingEngine completed with `task_ir_id=task_69b1be657f794276`, `request_contract_aol_metadata_persisted=true`, and downstream dispatch result `{total:5, succeeded:5, failed:0}`. The same historical row also shows top-level `status=failed` because an internal `pd_scene_dispatch_status` task later demoted the parent command after orchestration completed. This demotion is now fixed by rejecting internal phase/playbook task sync when its runtime id does not match the parent MeetingEngine command `accepted_task_id`; regression coverage is in `backend/tests/meeting_command_status_sync_spec.py`。

Post-audit correction for live E2E: command `cmd_aol_fresh_e2e_artifact_reconcile_20260503_2305` returned `status=completed`, `dispatch_status=completed`, `task_ir_id=task_eb9ad4e646e24f47`, `artifact_landing_status=landed`, `artifact_db_ids=["46ec0f7f-acaf-45c8-a4e8-e65fc14bfff0"]`, `artifact_file_paths=["/app/backend/data/workspaces/多平台內容一鍵生成/artifacts/60a3f8af-50d3-4988-9f23-779eb539ab37"]`, `dispatch_total=4`, `dispatch_succeeded=4`, `dispatch_failed=0`, and the request-contract AOL metadata preserves both IG refs plus selected guidance. This is transport/orchestration and task-result-wrapper landing evidence only. The actual intended deliverable did **not** land: `result.json` contains `steps.pd_storyboard_gen.status=error` and `Step generate_storyboard required output 'storyboard' (field='storyboard') not found in tool result`; the directory contains only `result.json` and `summary.md`. At that point final storyboard/proposal E2E remained open; the next 2026-05-04 closure paragraph supersedes this historical failed-deliverable status. Full line-by-line audit record is landed at `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-to-meeting-engine-orchestration-bridge-audit-record-2026-05-04.md`.

2026-05-04 final closure: command `cmd_aol_real_e2e_files_20260504_021_tasklineage` supersedes `_014`, `_018`, `_019`, and `_020` as the current acceptance record. It returned `status=completed`, `dispatch_status=completed`, `task_ir_id=task_f385ff20d3364399`, downstream execution id `7ba39e58-e19f-4113-b8db-5547558e26bd`, `artifact_landing_status=landed`, three artifact DB ids, and three concrete file paths: contact-sheet SVG, proposal Markdown, and storyboard manifest JSON. DB rows now carry `thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1` and `task_id=task_f385ff20d3364399`; content verification confirms 9 scenes, 90 seconds total, per-scene frame metadata, per-scene discussion/review carriers, and `render_profile.profile_id=pd_vertical_reels_storyboard`. Evidence is recorded in `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-real-file-e2e-evidence-2026-05-04.md`.

Latest verification after `_021`: local artifact lineage pytest subset `7 passed, 144 warnings`; frontend meeting-workbench vitest subset `4 files / 26 tests passed`; Performance Direction pack tests `187 passed, 49 warnings`; local-core and cloud `git diff --check` clean; modified Python modules `py_compile` clean; control/execution healthz both return `status=ok`.

本次修訂落入以下十一個不可跳過的 gate：

1. **contract carrier gate**：P0 不假設 `RequestContract` 已有 `metadata` 欄位；AOL payload 的 canonical carrier 是 `HandoffIn.context_attachments`，補充 carrier 是 `HandoffIn.metadata["addressable_object_layer"]`，且必須由 MeetingEngine merge 到 `session.metadata["request_contract"]["addressable_object_layer"]`。
2. **TaskIR persistence gate**：不得使用不存在的 `compiled_task_ir_id`；驗收欄位是 `task_ir_id = meeting_result.task_ir.task_id`，並必須復用既有 TaskIR persistence path。
3. **MeetingEngine runner gate**：不得在 command route 直接複製 `MeetingEngine` constructor；必須新增 `backend/app/services/orchestration/meeting/meeting_engine_runner.py`。
4. **PD normalizer exclusion gate**：現有 `HandoffIn` 內的 PD-specific normalizer 是既有相容程式；P0 bridge 不得依賴它作為新主路徑。
5. **single product route gate**：P0 產品 UI 不發 `route_playbook` 與 `route_object_action`。command 具有 `context_objects`、`meeting_mentions`、selected pack tool、graph guidance、任何 canonical AOL ref 其中任一條件時，唯一產品 route 是 `route_meeting_orchestration`。`route_playbook` 與 `route_object_action` 是非產品保留路徑：只允許 backend 測試和外部 API payload 顯式設定 `metadata.dispatch_mode` 且 `metadata.explicit_override = true` 觸發，web-console 不得發出。
6. **runtime evidence gate**：source-code tests 通過不等於 running runtime E2E；宣稱 IG/PD E2E 前必須補 API、DB 或 log evidence。
7. **UX orchestration-state gate**：既有 AOL Runtime Workbench / Meeting Workbench UX 骨架可繼承，但 P0 必須補出 MeetingEngine 編排狀態。Work view 不得只顯示 object graph、local task、direct dispatch result；必須顯示 command 是否進入 `MeetingEngine.run()`、`HandoffIn` / request-contract AOL metadata、`ActionIntent` / `TaskIR`、dispatch result、artifact/proposal 入庫入檔、review/next-state notification。
8. **selected guidance carrier gate**：frontend 必須把 selected graph guidance 的 `guidance_id`、`command_template`、`required_roles`、`target_ref`、`review_routes`、`card.metadata` 全量帶入 command metadata；bridge 只能把 `recommended_pack` / `recommended_playbook` 當 candidate hint。
9. **frontend response gate**：`dispatch_result.meeting_orchestration` 是 P0 成功 response shape；frontend 不得因未收到 route-owned `object_action`、`playbook`、`chat` 而把成功 orchestration 判成錯誤。
10. **artifact landing gate**：`task_ir.artifacts[]` 只是不充分的中間引用；E2E 完成證據必須包含 artifacts DB row 與可解析檔案路徑，或明確的 pending/review state 且不能宣稱入庫入檔完成。
11. **community originality gate**：IG refs -> PD storyboard/reels workflow 必須保留來源 evidence、創作意圖、差異化導演判斷與 human review trace；不得產生可被視為 mass-produced / low-variation template output 的假完成證據。

### 0.1 唯一實作路徑總表

P0 產品路徑固定如下，不允許替代路徑：

```text
web-console/src/components/capabilities/meeting-workbench/meetingCommandSubmit.ts:createMeetingCommandSubmitHandler()
-> web-console/src/components/capabilities/meeting-workbench/meetingCommandLedger.ts:submitMeetingCommandEnvelope()
-> POST /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands
-> backend/app/routes/core/workspace/meeting_commands.py:submit_meeting_command()
-> backend/app/services/meeting_command_parser.py:canonicalize_meeting_command_envelope()
-> backend/app/services/meeting_command_dispatch.py:should_route_meeting_orchestration()
-> backend/app/services/meeting_command_dispatch.py:dispatch_meeting_orchestration_for_command()
-> backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py:AOLMeetingOrchestrationBridge.build_handoff_in()
-> backend/app/services/object_runtime/route_services.py:project_object_graph()
-> backend/app/services/orchestration/meeting/meeting_engine_runner.py:MeetingEngineRunner.run_meeting_orchestration()
-> backend/app/services/orchestration/meeting/engine.py:MeetingEngine.run()
-> backend/app/services/orchestration/meeting/engine.py:_merge_request_contract_metadata()
-> backend/app/services/conversation/pipeline_meeting.py:persist_meeting_task_ir()
-> backend/app/services/stores/meeting_command_store.py:MeetingCommandStore.save()
```

P0 產品路徑禁止：

```text
submitMeetingCommandEnvelope() -> metadata.dispatch_mode = route_playbook
submitMeetingCommandEnvelope() -> metadata.dispatch_mode = route_object_action
submit_meeting_command() -> dispatch_object_action_for_command() for product AOL commands
submit_meeting_command() -> dispatch_playbook_for_command() for product AOL commands
submit_meeting_command() -> dispatch_chat_for_command() for commands with AOL refs or pack guidance
```

### 0.2 UX/UI 繼承與補全邊界

本次不重做整套 AOL runtime graph UI。既有 Workbench 骨架繼承如下：

| 既有骨架 | 繼承狀態 | 保留理由 |
|---|---:|---|
| `MeetingWorkbenchStage` 的 Object Outliner、Semantic Flow Canvas、Inspector、Command Ledger bottom band | true | 已形成四編輯器工作台，不需要回到 raw graph viewer |
| `WORK_GRAPH_LANES` 的 `Focus / Guidance / Command Ledger / Runtime / Outcomes / Assets / Next` | true | 已對齊用戶工作語義，可作為 MeetingEngine 編排狀態投影容器 |
| `useMeetingThreadData` 對 execution graph、meeting events、artifacts 的讀取 | true | 可復用為編排 proof、資產入庫、資產入檔的 UI 資料來源 |

必須補全的 P0 UX/UI 如下：

| 補全項 | 唯一實作路徑 | 驗收 |
|---|---|---|
| Command Dock route 改為 MeetingEngine 編排入口 | `meetingCommandLedger.ts:submitMeetingCommandEnvelope()` 寫入 `metadata.dispatch_mode = "route_meeting_orchestration"`；`meetingCommandSubmit.ts:createMeetingCommandSubmitHandler()` 解析 `dispatch_result.meeting_orchestration` | web-console 測試必須證明 selected pack tool、AOL refs、guidance command 都不再送 `route_playbook` / `route_object_action` |
| Canvas 顯示 MeetingEngine 編排鏈 | `meetingGraphProjection.ts:projectMeetingGraph()` 或其後續 projection module 把 `meeting_orchestration` / execution graph / events 投影成 `Intent -> Context Attachments -> RequestContract -> ActionIntent -> TaskIR -> Dispatch -> Artifact/Proposal -> Review/Next` | Work view 至少能選到 command node 並看到 `task_ir_id` 與 downstream asset/proposal/review 節點 |
| Inspector 顯示 MeetingEngine proof | `PropertiesInspector.tsx` / `MeetingDefaultInspectorContent.tsx` 的 Runtime/Guidance/Review content 讀取 selected node metadata | Inspector 必須顯示 `dispatch_mode`、`task_ir_id`、AOL metadata carrier、candidate playbook hints、dispatch status |
| Assets lane 顯示入庫與入檔 proof | `useMeetingThreadData.ts:fetchMeetingArtifacts()` 讀 `/artifacts?thread_id={meeting_id}`；artifact node output 必須包含 `storage_ref` 與 resolved `file_path` evidence | UI 能從同一 `meeting_id` 查到 artifact row，並顯示 file path/storage ref，不得只顯示 fixture card |
| AOL session notification 顯示 orchestration lifecycle | `meetingCommandSubmit.ts:createMeetingCommandSubmitHandler()` 接收 `dispatch_result.meeting_orchestration` 後發出 accepted/planning/dispatched/asset-landed/review/completed/failed notification | notification payload 必須包含同一 `meeting_id`、`command_id`，有 TaskIR 時包含 `task_ir_id` |

## 1. Problem list

1. **AOL command 目前由前端決定 dispatch route，沒有把任務目的交給 MeetingEngine 編排**：`meetingCommandLedger.ts` 依 `selectedPackTool` 與 `objectActionEntries.length` 直接寫入 `route_playbook`、`route_object_action`、`route_chat`，這讓 shell 先決定路徑，而不是讓 MeetingEngine 根據 user intent、object graph 與 pack affordances 組裝 workflow。Evidence: E1。Severity: 5。Detection: 5。Priority: 25。
2. **object action 與 selected playbook 是 AOL 工作流最重要的兩條路徑，但目前都繞過 MeetingEngine.run()**：`route_object_action` 直接呼叫 object runtime plan/invoke，`route_playbook` 直接呼叫 orchestrator 的 `execute_playbook` path，沒有進 MeetingEngine 的 agenda、contract、deliberation、ActionIntent、TaskIR、policy gate、dispatch、finalize 流程。Evidence: E2, E3, E4。Severity: 5。Detection: 5。Priority: 25。
3. **object-meeting-attach 只把 AOL context 寫進 meeting metadata，且有 direct materialize target outcome path，但沒有重新進入 MeetingEngine**：attach service 會解析 ObjectRef、建立/取得 MeetingSession、build handoff、在 target 與 non-target context 同時存在時直接 materialize target outcome，最後寫入 `session.metadata.addressable_object_layer`。這是 context/materializer 機制證明，不是 meeting-led orchestration。Evidence: E5。Severity: 5。Detection: 4。Priority: 20。
4. **MeetingEngine 已有 HandoffIn 與 RequestContract 插槽，但 AOL command ledger 主入口沒有使用，且 AOL metadata carrier 必須補明確 merge path**：`HandoffIn` 與 `RequestContract` 已提供 `playbook_requests`、`playbook_input_defaults`、`context_attachments`，MeetingEngine 會 merge 這些欄位並套用 deterministic playbook requests；但目前未找到 `handoff_in.metadata` 被 merge 的 path，且 `RequestContract` 沒有 `metadata` 欄位。缺口在 AOL command route 沒有建立 `HandoffIn` 並呼叫 `MeetingEngine.run()`，也沒有把 AOL metadata carrier 寫清楚。Evidence: E6, E7, E8, E13, E14。Severity: 5。Detection: 4。Priority: 20。
5. **既有進度文檔把 direct route-owned dispatch 寫成 P0 seed，容易被誤讀為 IG/PD E2E 已完成**：目前文件已承認 route-owned object-action/playbook/chat dispatch，但缺少 P0 修正 gate，導致「shell 能寫 ledger 並直派 pack」被誤當成「meeting 根據任務目的調度 packs」。Evidence: E9, E10。Severity: 5。Detection: 4。Priority: 20。
6. **IG refs 到 PD storyboard 的原始產品目標無法由目前 direct dispatch 正確保證**：原始 UX 目標要求 meeting graph node 同時提供 AI next-step guidance 與 tool-callable workflow spine；command 未進 MeetingEngine 時，`@ig.reference` 與 `@performance_direction.storyboard` 只會成為 direct route payload，而不是 meeting-owned RequestContract、ActionIntent、TaskIR、asset landing 與 review trace。Evidence: E11。Severity: 5。Detection: 5。Priority: 25。

## 2. Evidence

E1. 前端 command ledger 直接決定 dispatch mode：`selectedPackTool ? route_playbook : objectActionEntries.length >= 2 ? route_object_action : route_chat`。Source: `web-console/src/components/capabilities/meeting-workbench/meetingCommandLedger.ts:L84-L91`。

E2. `route_object_action` predicate 只檢查 command metadata，並要求至少兩個 context objects，未檢查 MeetingEngine contract。Source: `backend/app/services/meeting_command_dispatch.py:L38-L43`。

E3. `dispatch_object_action_for_command()` 直接呼叫 `object_runtime.plan_workspace_object_action()` 與 `object_runtime.invoke_workspace_object_action()`。Source: `backend/app/services/meeting_command_dispatch.py:L61-L118`。

E4. `dispatch_playbook_for_command()` 直接組 `action_params` 並呼叫 `orchestrator.handle_suggestion_action(action="execute_playbook")`。Source: `backend/app/services/meeting_command_dispatch.py:L140-L192`。

E5. `attach_objects_to_meeting()` 會建立/取得 MeetingSession、呼叫 `attachment_service.build_handoff()`、在 target 與 non-target context 同時存在時呼叫 `_materialize_target_outcome()`，最後把 attachment metadata 寫入 `session.metadata.addressable_object_layer`。Source: `backend/app/services/object_runtime/meeting_attach_service.py:L127-L260`。

E6. `HandoffIn` 已有 `playbook_requests`、`playbook_input_defaults`、`context_attachments`，並說明這些欄位用來避免在 meeting core 硬編碼 pack rules。Source: `backend/app/models/handoff.py:L263-L313`。

E7. `RequestContract` 已有 `playbook_requests` 與 `playbook_input_defaults`，其說明把 pack/playbook handoff 定義為通用 contract directive，而不是 MeetingEngine 內的 pack-specific routing rules。Source: `backend/app/models/request_contract.py:L49-L84`。

E8. `MeetingEngine.run()` 是七階段 pipeline，且會從 `handoff_in` merge `context_attachments`、`playbook_requests`、`playbook_input_defaults`，再套用 request contract playbook requests。Source: `backend/app/services/orchestration/meeting/engine.py:L298-L330`, `backend/app/services/orchestration/meeting/engine.py:L930-L1012`。

E9. 既有 command envelope 計劃的進度文字寫明目前已實作 route-owned object-action/playbook/chat dispatch。Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L1-L4`。

E10. 既有 milestone 狀態已寫明 direct dispatch 不屬於最終產品主路線，但後續變更仍把 `route_object_action`、`route_playbook`、`route_chat` 作為主路線記錄。Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-milestone-status-2026-05-02.md:L5-L13`, `docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-milestone-status-2026-05-02.md:L196-L219`。

E11. 產品 UX/UI 計劃已定義原始目標：meeting graph nodes 不是 generic graph viewer，而是 AI next-step guidance 與 tool-callable workflow spine；Command Dock 必須把 guidance/user intent 轉成 `MeetingCommandEnvelope`，不得讓 random card buttons 繞過 command ledger。Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L5-L13`, `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L56-L70`。

E12. 既有 conversation pipeline 與 handoff bundle intake 證明 MeetingEngine 已存在 runtime 呼叫路徑，不需要在 pack 中新增 IG/PD 特例。Source: `backend/app/services/conversation/pipeline_core.py:L330-L349`, `backend/app/services/handoff_bundle_service.py:L328-L332`, `backend/app/services/handoff_bundle_service.py:L722-L735`。

E13. `RequestContract` 目前沒有 `metadata` 欄位，因此 P0 計劃不能寫成直接依賴 `RequestContract.metadata.addressable_object_layer`。Source: `backend/app/models/request_contract.py:L49-L90`。

E14. full scope grep 未找到 `handoff_in.metadata` 被 MeetingEngine merge。Command: `rg -n "handoff_in\\.metadata|getattr\\(handoff_in, \\\"metadata\\\"|metadata = getattr\\(handoff_in" backend/app/services backend/app/models`。Output: no matches。

E15. `MeetingResult` 目前欄位是 `task_ir`，現有 persistence path 使用 `meeting_result.task_ir.task_id` 作為 `task_ir_id`。Source: `backend/app/services/orchestration/meeting/engine.py:L81-L92`, `backend/app/services/handoff_bundle_service.py:L772-L790`。

E16. `MeetingEngine` constructor 依賴 session、store、workspace、runtime profile、thread id、execution launcher、model、executor runtime、execution context；command route 目前沒有全部 dependency。Source: `backend/app/services/orchestration/meeting/engine.py:L109-L123`, `backend/app/routes/core/workspace/meeting_commands.py:L104-L115`。

E17. 現有 `HandoffIn` model 內有 PD-specific `pd_storyboard_seed` 與 playbook route 推導，這與 P0 bridge 的 generic host 原則存在衝突風險。Source: `backend/app/models/handoff.py:L35-L79`, `backend/app/models/handoff.py:L106-L240`。

E18. `deploy-pack` 規範要求 capability source of truth 在 cloud repo，經 `.mindpack` 與 local-core control plane install API 安裝；不得直接編輯 local-core 已安裝 pack payload。Source: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/.agent/skills/deploy-pack/SKILL.md:L23-L67`, `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/.agent/skills/deploy-pack/SKILL.md:L111-L118`。

E19. repo 現況尚未實作新主線 component。Command: `rg -n "route_meeting_orchestration|AOLMeetingOrchestrationBridge|aol_meeting_orchestration|dispatch_meeting_orchestration|should_route_meeting_orchestration|MeetingEngineRunner" backend web-console`。Output: no matches。

E20. frontend submit handler 目前只接受 `object_action`、`object_action_plan`、`playbook`、`chat` 四種 route-owned result；沒有處理 `dispatch_result.meeting_orchestration`，最後會丟出 route-owned result error。Source: `web-console/src/components/capabilities/meeting-workbench/meetingCommandSubmit.ts:L157-L297`。

E21. graph guidance node metadata 目前只保留 `guidance_id`、`guidance_intent`、`command_template`、`review_routes`、`target_ref`、`required_roles` 與 projection owner refs，未把 pack-owned guidance `card.metadata` 傳入 command path。Source: `web-console/src/components/capabilities/meeting-workbench/meetingGraphObjectProjection.ts:L115-L128`。

E22. selected guidance draft 目前用 projection `owner_pack` 選 pack tool，而不是用 guidance metadata 的 `recommended_pack` / `recommended_playbook`。Source: `web-console/src/components/capabilities/meeting-workbench/meetingGuidanceCommand.ts:L25-L32`。

E23. IG reference guidance 的 PD 推薦存在 cloud pack guidance metadata 中：`recommended_pack = performance_direction`、`recommended_playbook = pd_director_guidance`。Source: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/services/object_layer/reference_runtime.py:L83-L98`。

E24. PD storyboard/scene/proposal guidance 也使用 generic guidance metadata 推薦 playbook，local-core 不應硬編碼 PD routing。Source: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/services/object_layer/storyboard_runtime.py:L328-L435`。

E25. local-core 已有 generic object-to-meeting attachment builder，會建立 `HandoffIn.context_attachments` 與 `metadata["addressable_object_layer"]`。新 bridge 若另造 attachment shape，會形成平行契約。Source: `backend/app/services/object_meeting_attachment_service.py:L31-L98`。

E26. `MeetingEngine` constructor 依賴 runtime profile、profile id、thread id、project id、execution launcher、model、executor runtime、execution context；command route 目前沒有這些 dependency。Source: `backend/app/services/orchestration/meeting/engine.py:L109-L123`, `backend/app/routes/core/workspace/meeting_commands.py:L108-L115`。

E27. `session_store.update(session)` 是持久化 `MeetingSession.metadata` 的既有路徑；若 runner 只修改 in-memory session，DB/API 驗收可能查不到 `request_contract.addressable_object_layer`。Source: `backend/app/services/stores/meeting_session_store.py:L228-L280`。

E28. meeting artifact emitter 目前主要把 pack producer 結果追加到 `task_ir.artifacts` 與 session metadata；這不等於 artifacts DB row 與可解析 file path。Source: `backend/app/services/orchestration/meeting/capability_artifact_emitter.py:L18-L49`, `backend/app/services/orchestration/meeting/capability_artifact_emitter.py:L185-L233`。

E29. repo 已有 playbook output artifact DB creation path，可作為 P0 artifact landing 對接點之一。Source: `backend/app/services/playbook_output_artifact_creator.py:L147-L168`。

E30. live control/execution readiness 已恢復。Command: `curl -sS -m 8 http://localhost:8220/healthz`; Output: `{"status":"ok","backend_role":"control","reload_enabled":true}`。Command: `curl -sS -m 8 http://localhost:8200/healthz`; Output: `{"status":"ok","backend_role":"execution","reload_enabled":false}`。Command: `docker ps --filter name=mindscape-ai-local-core-backend --format '{{.Names}} {{.Status}}'`; Output includes `mindscape-ai-local-core-backend Up ... (healthy)` and `mindscape-ai-local-core-backend-control Up ... (healthy)`。

E31. live health check currently reports Ollama ready and OCR intentionally disabled, not warning. Command: `curl -sS -m 10 http://localhost:8220/health | jq '{status, llm_configured, llm_available, llm_provider, ocr_service:(.components.ocr_service // .ocr_service), issues}'`。Output: `{"status":"healthy","llm_configured":true,"llm_available":true,"llm_provider":"ollama","ocr_service":"disabled","issues":[]}`。

E32. live capability registry currently has `ig` and `performance_direction` installed/enabled/validated. Command: `curl -sS -m 10 http://localhost:8220/api/v1/capability-packs/ | jq '[.[] | select(.id == "ig" or .id == "performance_direction") | {id, enabled, installed, validation:(.validation.state // .validation.status // null), playbook_count:(.playbooks | length), tool_count:(.tools | length)}]'`。Output: `ig` has `enabled=true`, `installed=true`, `validation=succeeded`, `playbook_count=28`, `tool_count=38`; `performance_direction` has `enabled=true`, `installed=true`, `validation=succeeded`, `playbook_count=15`, `tool_count=26`。

E33. live execution plane currently has an authenticated `codex_cli` client for the test workspace. Command: `curl -sS -m 10 http://localhost:8200/api/v1/mcp/agent/status`。Output includes workspace `bac7ce63-e768-454d-96f3-3a00e8e1df69` with client `codex_cli-bac7ce63-e768-454d-96f3-3a00e8e1df69-43b0a0a4a97a`, `authenticated=true`, `pending_count=0`。

E34. live command `cmd_aol_late_reconcile_smoke_20260503` reached MeetingEngine and downstream PD phases. Command: `curl -sS -m 10 'http://localhost:8220/api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/meetings/0f2463d0-2f22-4016-9b5d-cb3b389eb8d1/commands'`。Output for that command includes `metadata.meeting_orchestration.status="completed"`, `task_ir_id="task_69b1be657f794276"`, `request_contract_aol_metadata_persisted=true`, and `dispatch_result` with `total=5`, `succeeded=5`, `failed=0`。

E35. the same historical live command also proves an already-fixed demotion bug: top-level command `status="failed"` and `metadata.dispatch_status="failed"` came from internal task `runtime_task.pack_id="pd_scene_dispatch_status"` despite `meeting_orchestration.status="completed"`。Fix: `backend/app/services/meeting_command_status_sync.py:L222-L228` rejects internal phase/playbook sync when runtime id does not match `command.accepted_task_id` for MeetingEngine-owned commands. Regression: `backend/tests/meeting_command_status_sync_spec.py:L97-L136`。

E36. live artifact DB/file landing for the IG→PD smoke is still not proven. Command: `curl -sS -m 10 'http://localhost:8220/api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/artifacts?thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1'`。Output: `{"artifacts":[],"total":0,"limit":100,"offset":0}`。

E36a. post-fix live E2E artifact landing is proven at command level and session-thread artifact API level. Command `cmd_aol_fresh_e2e_artifact_reconcile_20260503_2305` returns `status="completed"`, `accepted_task_id="task_eb9ad4e646e24f47"`, `metadata.meeting_orchestration.status="completed"`, `artifact_landing_status="landed"`, `artifact_db_ids=["46ec0f7f-acaf-45c8-a4e8-e65fc14bfff0"]`, `artifact_file_paths=["/app/backend/data/workspaces/多平台內容一鍵生成/artifacts/60a3f8af-50d3-4988-9f23-779eb539ab37"]`, and downstream dispatch result `total=4`, `succeeded=4`, `failed=0`。Artifact API command: `curl -sS -m 10 'http://localhost:8220/api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/artifacts?thread_id=aol-e2e-timeout-20260503'` returns artifact `46ec0f7f-acaf-45c8-a4e8-e65fc14bfff0` with execution id `60a3f8af-50d3-4988-9f23-779eb539ab37` and the same file path. File proof: `docker exec mindscape-ai-local-core-backend-control sh -lc 'test -d "/app/backend/data/workspaces/多平台內容一鍵生成/artifacts/60a3f8af-50d3-4988-9f23-779eb539ab37" && echo exists:60a3f8af'` outputs `exists:60a3f8af`。

E37. command timeout semantics now avoid false artifact failure. Source: `backend/app/services/meeting_command_dispatch.py:L146-L175` returns `artifact_landing_status="pending"`, `late_result_possible=true`, and `error_code="meeting_orchestration_timeout"`；test source: `backend/tests/meeting_command_dispatch_timeout_spec.py:L28-L94`。

E38. cross-worker dispatch no longer treats websocket send as task ACK. Source: `backend/app/routes/agent_dispatch/pubsub_handlers.py:L23-L52` publishes `agent_dispatch_ack_timeout` when no client ACK arrives, and `backend/app/routes/agent_dispatch/pubsub_handlers.py:L139-L148` only schedules the deadline after socket send instead of emitting a false ACK. Source: `backend/app/routes/agent_dispatch/cross_worker.py:L40-L78` converts ACK deadline expiry to bounded retry/timeout results.

E39. late external-agent result correlation now carries command and AOL metadata through transport. Source: `backend/app/services/orchestration/dispatch_orchestrator.py:L968-L1024` extracts/apply meeting command transport context; `backend/app/services/external_agents/core/polling_adapter.py:L47-L134` writes `meeting_command_id` and `addressable_object_layer` into payload context/metadata; `backend/app/routes/agent_dispatch/message_handlers.py:L557-L590` runs best-effort command reconciliation after WS result landing; `backend/app/services/meeting_command_status_sync.py:L268-L386` updates command ledger from late agent results.

E40. 2026-05-03 external web snapshot supports the product direction. OpenAI Agents SDK documents mixed LLM/code orchestration and handoffs; LangGraph documents persistence/durable execution, checkpoints, human-in-the-loop and fault tolerance; MCP architecture documents host/client/server separation with tools/resources; YouTube reused-content policy and April 30, 2026 Instagram aggregator reporting both point toward provenance, meaningful transformation, and avoiding low-effort repost/template output.

## 3. Proposed changes

### Change 1: 鎖定 P0 設計意圖 traceability gate

Resolves Problems 5 and 6.

所有後續 AOL Runtime Shell / Meeting Workbench 計劃與驗收必須逐條填寫：

```text
原始設計意圖
-> 不可變產品原則
-> 架構責任邊界
-> 必須經過的程式路徑
-> 禁止路徑
-> 需要修改的檔案
-> 需要新增/修改的測試
-> 驗收證據
-> 偏離風險
```

本 P0 的不可變產品原則：

- AOL Runtime Shell 不是 direct pack executor。
- AOL Runtime Shell 是 local-core host，負責把 object refs、graph guidance、user intent、pack affordances 轉交 MeetingEngine。
- MeetingEngine 是任務目的理解、跨 pack workflow 組裝、ActionIntent、TaskIR、dispatch、memory、review trace 的中樞。
- `@object` command 是統一意圖入口。
- graph guidance 的 `recommended_playbook` 只能是 candidate/hint；P0 產品 UI 不提供 direct run exact playbook route。
- IG/PD 不得在 local-core 形成 pack-specific hard binding。

### Change 2: 新增 `AOLMeetingOrchestrationBridge`

Resolves Problems 1, 3, and 4.

新增唯一 local-core host service：

```text
backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py
```

責任：

- 接收 `MeetingCommandEnvelope`、workspace id、meeting id、thread id。
- 收集 command `context_objects`、`meeting_mentions`、`requested_action`、`origin_surface`、`write_mode`。
- 收集 frontend 傳入的 selected graph guidance carrier：`metadata.selected_guidance_id`、`metadata.selected_guidance_ids`、`metadata.selected_guidance_metadata`、`metadata.selected_guidance_cards`、`metadata.selected_guidance_object_ref`、`metadata.action_parameters.selected_guidance_*`。
- 讀取當前 `MeetingSession.metadata.addressable_object_layer` 中的 attach metadata，但不得把 attach materialization 當作 workflow 完成。
- 若 canonical object refs 非空，呼叫 `backend.app.services.object_runtime.route_services.project_object_graph(ObjectGraphProjectRequest(...), workspace_id=workspace_id)`；若 object refs 為空，不得用空 `objects=[]` 呼叫 graph projection，改以 selected guidance / pack tool / raw intent 建立 guidance-only handoff。
- 復用或擴充 `ObjectMeetingAttachmentService` 的 generic attachment shape；不得另造與 `object_meeting_attachment_service.py` 平行且不相容的 `context_attachments` schema。
- 將 object refs、roles、bounded projections、graph guidance、relations、review routes、staged refs、selected guidance metadata 轉成 `HandoffIn.context_attachments`。
- 將 selected pack tool、guidance `metadata.recommended_pack`、guidance `metadata.recommended_playbook` 轉成 `candidate_playbooks`，不得轉成 hard `playbook_requests`。
- 將 AOL metadata 放入 `HandoffIn.metadata["addressable_object_layer"]`，並同步保留在 `HandoffIn.context_attachments` 驗收 payload 中。
- P0 不修改 `RequestContract` model。驗收 carrier 固定為 `session.metadata["request_contract"]["addressable_object_layer"]` 與 `HandoffIn.context_attachments`。
- 不 import IG/PD source repository，不直接讀 cloud 檔案，不在 local-core 寫 IG/PD 業務邏輯。

唯一 class / method contract：

```python
class AOLMeetingOrchestrationBridge:
    async def build_handoff_in(
        self,
        *,
        command: MeetingCommandRecord,
        canonical: MeetingCommandEnvelope,
        session: MeetingSession,
        workspace_id: str,
    ) -> HandoffIn: ...
```

Bridge output contract：

```text
HandoffIn.context_attachments[]
  - object_ref
  - object_role
  - owner_pack
  - object_kind
  - projection_summary
  - relations
  - guidance_hints
  - selected_guidance
  - selected_guidance_metadata
  - review_routes
  - staged_refs

HandoffIn.metadata["addressable_object_layer"]
  - command_id
  - origin_surface
  - selected_object_refs
  - selected_guidance_ids
  - selected_guidance_cards
  - selected_guidance_metadata
  - selected_guidance_object_refs
  - candidate_playbooks
  - explicit_override
```

`candidate_playbooks[]` 固定 shape：

```text
- source: "selected_pack_tool" | "graph_guidance" | "command_template"
- pack_code
- playbook_code
- guidance_id
- object_ref
- confidence
- reason
```

禁止輸出：

- `RequestContract.metadata.addressable_object_layer`。
- `HandoffIn.playbook_requests` from P0 bridge output。
- IG/PD 特例欄位作為 bridge 主契約。
- 直接把 pack guidance `recommended_playbook` 轉成 hard `playbook_requests`。
- 在 bridge 內解析或 hard-code `@pack:performance_direction.*`、`@storyboard:*`、`@scene:*` 的 pack-specific route。

### Change 3: 新增 `route_meeting_orchestration`

Resolves Problems 1 and 2.

修改 backend command dispatch contract：

- 新增 predicate `should_route_meeting_orchestration(canonical)`。
- 固定規則：command 有 `context_objects`、`meeting_mentions`、`metadata.selected_guidance_id`、`metadata.selected_guidance_ids`、`metadata.selected_guidance_metadata`、`metadata.selected_pack_tool_id`、`metadata.action_parameters.object_action_entries`、canonical parser 可解析的 AOL object refs 其中任一條件時，走 `route_meeting_orchestration`。
- `route_object_action` 是非產品保留路徑：只允許 backend 測試和外部 API payload 顯式設定 `metadata.dispatch_mode = "route_object_action"` 且 `metadata.explicit_override = true` 觸發，web-console 不得發出。
- `route_playbook` 是非產品保留路徑：只允許 backend 測試和外部 API payload 顯式設定 `metadata.dispatch_mode = "route_playbook"` 且 `metadata.explicit_override = true` 觸發，web-console 不得發出。
- `route_chat` 僅處理無 `context_objects`、無 `meeting_mentions`、無 selected guidance、無 selected pack tool、無 canonical AOL refs 的純文字 command。
- 不得使用 frontend `command.includes('@')` 作為唯一 routing 判斷；email、社群 handle、一般文字中的 `@` 不應被誤判為 AOL orchestration。

插入點：

- `backend/app/services/meeting_command_dispatch.py`：新增 orchestration predicate 與 dispatch function。
- `backend/app/routes/core/workspace/meeting_commands.py`：把 orchestration route 放在 object/playbook/chat 前面。
- `web-console/src/components/capabilities/meeting-workbench/meetingCommandLedger.ts`：修改 default dispatch mode selection。
- `backend/tests/test_meeting_command_envelope.py`：保留 direct route explicit override 測試，並新增 web-console metadata 不可觸發 direct routes 的回歸測試。

### Change 4: 新增 MeetingEngine runner

Resolves Problems 2 and 4.

新增唯一 local-core meeting orchestration runner：

```text
backend/app/services/orchestration/meeting/meeting_engine_runner.py
```

責任：

- 集中建立 `MeetingEngine`，復用 `PipelineCore` / `handoff_bundle_service` 已驗證的 constructor dependency 組裝方式。
- 提供唯一 public method：`MeetingEngineRunner.run_meeting_orchestration(...)`。
- 回傳標準化 result：`meeting_result`、`task_ir_id`、`event_ids`、`minutes_md`、`completion_status`、`dispatch_result`。
- 在 runner 內處理 TaskIR persistence，使用 `meeting_result.task_ir.task_id`，不得製造不存在的 `compiled_task_ir_id`。
- 在 runner 內持久化 `MeetingSession.metadata`；`MeetingEngine.run()` 後若 session metadata 包含 request-contract AOL carrier，必須呼叫 `session_store.update(session)`。

Runner dependency map 必須逐欄寫在 implementation PR 內，不得用隱式 default：

```text
profile_id: workspace.owner_user_id
project_id: session.project_id or workspace.primary_project_id
thread_id: session.thread_id or command.thread_id or session.id
runtime_profile: WorkspaceRuntimeProfileStore / chat_session_setup 等既有 profile loading path
execution_launcher: pipeline_meeting.build_execution_launcher(store)
model_name: runtime_profile / session metadata / existing workspace default resolution
executor_runtime: runtime_profile / workspace execution mode resolution
execution_context: existing MeetingExecutionContext construction path, not a new ad hoc dict
uploaded_files: [] unless command metadata carries explicit uploaded file refs
```

若任一 dependency 無法從既有 path 解析，runner 必須回傳 `status = "failed"` 與可診斷 `missing_dependency` metadata；不得用空物件讓 MeetingEngine 半初始化後才失敗。

唯一 class / method contract：

```python
class MeetingEngineRunner:
    def __init__(self, *, store: MindscapeStore, session_store: MeetingSessionStore) -> None: ...

    async def run_meeting_orchestration(
        self,
        *,
        session: MeetingSession,
        workspace: Workspace,
        message: str,
        handoff_in: HandoffIn,
        command: MeetingCommandRecord,
    ) -> dict: ...
```

`run_meeting_orchestration()` 回傳 dict 固定 shape：

```python
{
    "status": "completed" | "failed",
    "session_id": str,
    "task_ir_id": str | None,
    "event_ids": list[str],
    "minutes_md": str,
    "completion_status": str,
    "dispatch_result": dict | None,
    "task_ir_artifacts": list[dict],
    "artifact_ids": list[str],
    "artifact_file_paths": list[str],
    "artifact_landing_status": "landed" | "pending" | "not_landed" | "not_requested" | "failed",
    "artifact_db_ids": [...],
    "artifact_db_errors": [...],
    "request_contract_aol_metadata": dict,
    "request_contract_aol_metadata_persisted": bool,
}
```

禁止做法：

- 在 `meeting_commands.py` route handler 內直接 new `MeetingEngine`。
- 在 `meeting_command_dispatch.py` 複製一套與 `PipelineCore` 分叉的 constructor defaults。
- 為 IG/PD 建立 pack-specific runner。

### Change 5: `route_meeting_orchestration` 必須呼叫 `MeetingEngine.run()`

Resolves Problems 2 and 4.

`dispatch_meeting_orchestration_for_command()` 必須：

- 接收 `submit_meeting_command()` 已驗證的 `MeetingSession`。
- 呼叫 `AOLMeetingOrchestrationBridge.build_handoff_in(...)`。
- 呼叫 `MeetingEngineRunner.run_meeting_orchestration(...)`。
- 由 runner 呼叫 `MeetingEngine.run(command.intent_text, handoff_in=handoff_in)`。
- 將 `MeetingResult` 的 `task_ir_id = meeting_result.task_ir.task_id`、`event_ids`、`minutes_md`、`completion_status`、dispatch result 寫回 command row metadata。
- command lifecycle 必須從 accepted/running/completed/failed 與 meeting runtime result 對齊，不得只用 direct pack task status 判斷。
- `HandoffIn.metadata["addressable_object_layer"]` 必須由 MeetingEngine metadata merge path 寫入 `session.metadata["request_contract"]["addressable_object_layer"]`；驗收來源固定為 API、DB、log evidence。
- runner 必須在 `MeetingEngine.run()` 後呼叫 `persist_meeting_task_ir(meeting_result.task_ir)`，再呼叫 `session_store.update(session)` 持久化 request-contract AOL metadata 與 capability artifact producer session updates。
- runner 必須回傳 artifact landing summary：`task_ir_artifacts`、`artifact_ids`、`artifact_file_paths`、`artifact_db_ids`、`artifact_db_errors`、`artifact_landing_status`。沒有 DB row 或 file path 時只能是 `pending` / `not_landed`，不得標 `completed`。

`dispatch_meeting_orchestration_for_command()` 回傳固定 shape：

```python
command.metadata["dispatch_mode"] = "route_meeting_orchestration"
command.metadata["dispatch_status"] = runner_result["status"]
command.metadata["meeting_orchestration"] = runner_result
command.accepted_task_id = runner_result["task_ir_id"]
dispatch_result = {"meeting_orchestration": runner_result}
```

`runner_result["status"] == "completed"` 時，`command.status = MeetingCommandStatus.COMPLETED`。`runner_result["status"] == "failed"` 時，`command.status = MeetingCommandStatus.FAILED`。

必要插入點：

- `backend/app/services/meeting_command_dispatch.py`：新增 `dispatch_meeting_orchestration_for_command(..., session: MeetingSession, store: MindscapeStore, session_store: MeetingSessionStore)`，但只負責 command-to-bridge-to-runner orchestration，不直接組 `MeetingEngine`。
- `backend/app/routes/core/workspace/meeting_commands.py`：把 `route_meeting_orchestration` branch 排在 `route_object_action`、`route_playbook`、`route_chat` 前。
- `backend/app/routes/core/workspace/meeting_commands.py`：`submit_meeting_command()` signature 新增 `store: MindscapeStore = Depends(get_store)`，並把 `store` 傳入 `dispatch_meeting_orchestration_for_command(...)`。
- `backend/app/services/orchestration/meeting/engine.py:_merge_request_contract_metadata(...)`：在既有 `context_attachments` merge 後，讀取 `handoff_in.metadata["addressable_object_layer"]`，寫入回傳 metadata 的 `addressable_object_layer`；不得要求 `RequestContract` model 先新增 `metadata` 欄位。
- `backend/app/services/conversation/pipeline_meeting.py:persist_meeting_task_ir(...)`：runner 只能復用此 path 或抽出共用 helper，不得新增第二套 TaskIR store 寫入語義。
- `backend/app/services/stores/meeting_session_store.py:update(...)`：runner 必須使用此 path 持久化 session metadata。

### Change 6: 分離 attach context 與 materialization completion

Resolves Problem 3.

`object-meeting-attach` 目前存在 direct materialize target outcome path。P0 bridge 落地後必須把語義切清：

- `attach` 是 context preparation。
- `materialize` 是由 MeetingEngine orchestration 選出的 downstream action。
- 現有 direct materialization 只屬於非產品保留路徑；P0 產品驗收不得使用 direct materialization 作為完成證據。
- bridge 只讀 `MeetingSession.metadata["addressable_object_layer"]`、`canonical.context_objects`、`canonical.meeting_mentions` 與 `project_object_graph()` 結果。

### Change 7: 修正 frontend default dispatch 與測試期待

Resolves Problems 1, 2, and 6.

Frontend rule：

- `submitMeetingCommandEnvelope()` 內 `metadata.dispatch_mode` 固定計算：
  - `route_meeting_orchestration`：`objectActionEntries.length > 0 || mentionRefs.length > 0 || selectedPackTool !== null || selectedGuidance !== null || selectedGuidanceMetadata !== null`
  - `route_chat`：上述條件全為 false
- P0 產品 UI 不發 `route_playbook`。
- P0 產品 UI 不發 `route_object_action`。
- `selectedPackTool` 保留在 `requested_action` 與 `metadata.selected_pack_tool_id`，只作為 MeetingEngine 候選 affordance，不是 direct dispatch mode。
- `command.includes('@')` 不得作為 route 判斷條件；只有 `extractMentionReferences()` 或 backend canonical parser 識別的 AOL refs 才能觸發 orchestration。
- `buildObjectGraphNodes()` 建立 guidance node 時必須把 `card.metadata` 保留到 `node.metadata.guidance_metadata` 或等價欄位，不得丟失 `recommended_pack` / `recommended_playbook`。
- `applyGuidanceCommandDraft()` 不得用 projection `owner_pack` 當 selected pack tool。若 guidance metadata 提供 `recommended_pack` / `recommended_playbook`，可以填入 command metadata 的 selected guidance carrier 或 candidate affordance；不能因此發 `route_playbook`。
- `meetingCommandSubmit.ts` 必須處理 `dispatch_result.meeting_orchestration`：更新 local task 狀態、通知、`task_ir_id`、artifact landing summary、request-contract AOL metadata evidence；不得丟出 `Meeting command route did not return a route-owned dispatch result.`。

唯一前端修改檔：

- `web-console/src/components/capabilities/meeting-workbench/meetingCommandLedger.ts`
- `web-console/src/components/capabilities/meeting-workbench/meetingCommandSubmit.ts`
- `web-console/src/components/capabilities/meeting-workbench/meetingGraphObjectProjection.ts`
- `web-console/src/components/capabilities/meeting-workbench/meetingGuidanceCommand.ts`
- `web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchTypes.ts`

要更新的測試：

- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx`
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellMentions.spec.tsx`
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellPackFixtures.spec.tsx`
- `web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchTestHarness.ts`

### Change 8: 界定既有 PD normalizer 與 cloud/local-core 邊界

Resolves Problems 4 and 6.

現有 `HandoffIn` 內的 PD-specific `pd_storyboard_seed` normalizer 是既有相容程式，不屬於本 P0 路徑。P0 bridge 的輸入與輸出必須是 generic object refs、roles、relations、guidance hints、review routes、candidate playbooks。

實作紅線：

- local-core host 只處理 generic `ObjectRef`、`GraphProjection`、`GraphGuidance`、`HandoffIn`、`RequestContract`、TaskIR。
- local-core host 不得 hard-code `performance_direction` 的 storyboard seed 推導，也不得 hard-code IG 到 PD 的 playbook routing。
- IG/PD guidance schema、command templates、playbook metadata、materializer 的所有調整，固定修改 `mindscape-ai-cloud/capabilities/{pack}` source，打 `.mindpack` 並經 local-core control plane install API；不得直接修改 `local-core/backend/app/capabilities/{pack}` 已安裝 payload。
- 任何為了本機 smoke 的 dirty pack install 必須標明是 working-tree smoke，不得當成 release install。

### Change 9: 重新定義 IG/PD E2E 驗收

Resolves Problem 6.

IG refs 到 PD storyboard 的 E2E 必須用以下路徑驗收：

```text
user intent: "使用這幾張 ig refs @ig.reference:refA @ig.reference:refB 構思一組 90s reels 分鏡並完成分鏡圖製作"
-> MeetingCommandEnvelope
-> route_meeting_orchestration
-> AOLMeetingOrchestrationBridge
-> HandoffIn.context_attachments + session.metadata["request_contract"]["addressable_object_layer"]
-> MeetingEngine.run()
-> ActionIntent / TaskIR
-> pack dispatch selected by meeting orchestration
-> storyboard/proposal/artifacts landed
-> graph + Command Ledger + AOL session notification updated
```

此 E2E 不要求預先提供 PD storyboard target。MeetingEngine 決策缺少 target 時，唯一合法結果是 meeting response / Command Ledger 記錄缺口並要求補上下文；不得由 frontend direct playbook route 補成假 E2E。

不得用以下證據宣稱完成：

- only object graph projection works
- only attach response returns staged refs
- only direct `route_playbook` starts a task
- only direct `route_object_action` materializes target output
- only frontend fixture proves no direct `/chat`

### Change 10: 補 artifact landing 與入檔責任

Resolves Problems 6 and P0 checklist artifact gates.

P0 的「完成分鏡圖製作」不得只停在 TaskIR 或 pack response。落地責任必須拆清：

- `MeetingEngine` 產生 `TaskIR` 與 action/dispatch intent。
- downstream pack execution 或 capability artifact producer 產生 artifact reference。
- local-core artifact landing path 必須把可交付結果寫入 artifacts DB row。
- artifact metadata 必須包含可解析檔案路徑：`file_path`、`actual_file_path`、`storage_ref` 或等價 storage descriptor。
- 若 pack 只回傳 proposal/staged result，Command Ledger 必須顯示 `artifact_landing_status = pending`，不得標示「入庫入檔完成」。

必要插入點：

- `backend/app/services/orchestration/meeting/meeting_engine_runner.py`：整理 `meeting_result.task_ir.artifacts`、透過 `MindscapeStore.artifacts.create_artifact()` 落 DB、保留 file path/storage ref、更新 session metadata，輸出 `artifact_db_ids` / `artifact_db_errors` / `artifact_landing_status`。
- `backend/app/services/playbook_output_artifact_creator.py` 或既有 task-result landing path：若 dispatch result 包含 output artifacts，必須建立 artifacts DB row。
- `backend/app/routes/core/artifacts.py` 或 artifact list API：Verification SOP 必須查同一 `meeting_id` / `thread_id` 下可見 artifact。

禁止做法：

- 只把 artifact reference append 到 `task_ir.artifacts` 就宣稱 artifacts DB 入庫。
- 只把 file path 放在 metadata 但檔案不存在就宣稱入檔。
- 在 local-core hard-code IG/PD artifact schema；pack-specific output mapping 必須留在 cloud capability source 或 installed pack contract。

### Change 11: 補外部社區與 agent orchestration 對齊 gate

Resolves Problem 6 and community originality gate.

P0 不需要追逐單一平台 API，但必須避免產品方向與 2025-2026 主流 agent/tool workflow 與內容平台規範脫節：

- Agent/tool orchestration 主流做法是「host 保持 generic orchestration，tools/packs 提供 affordances，runtime 保留 trace/persistence/human review」。本計劃的 MeetingEngine 中樞、candidate playbooks、TaskIR、review trace 與該方向一致。
- 內容社區方向正在降低 mass-produced、reused、low-variation content 的分發與商業化價值。IG refs -> PD storyboard/reels E2E 必須把 refs 當 visual evidence 與創作素材，不得把 pack guidance 寫成模板化批量生成。
- Verification 必須檢查 output metadata 是否保留 source refs、director rationale、human review route、proposal/revision state。缺少這些欄位時，只能標 `requires_review` 或 `pending_context`。

2026-05-03 補查結論：本計劃沒有與主流網路社區環境脫節，但必須把「trace/persistence/review/provenance」當作產品完成條件，而不是報告附註。OpenAI Agents SDK 的 orchestration/handoff、LangGraph 的 durable execution/checkpoint、人機審核、MCP 的 host/tools/resources 分層，都支持 local-core 作為 generic host、pack 作為 affordance provider、MeetingEngine 作為可追溯 workflow spine。內容平台側，YouTube reused content policy 與 2026-04-30 Instagram 對 aggregator/reposted photo/carousel reach 的收緊，要求 IG refs -> PD storyboard/reels 不能只是搬運素材或低差異模板；必須輸出 source refs、創作判斷、material transformation、human review route。

外部參考快照：

- OpenAI Agents SDK multi-agent orchestration: `https://openai.github.io/openai-agents-js/guides/multi-agent/`
- OpenAI Agents SDK Python agent orchestration: `https://openai.github.io/openai-agents-python/multi_agent/`
- LangGraph persistence / durable workflow: `https://docs.langchain.com/oss/javascript/langgraph/persistence`
- LangGraph durable execution: `https://docs.langchain.com/oss/python/langgraph/durable-execution`
- Model Context Protocol host/tools/resources architecture: `https://modelcontextprotocol.io/docs/learn/architecture`
- Model Context Protocol specification architecture: `https://modelcontextprotocol.io/specification/2025-06-18/architecture`
- YouTube reused / repetitive content monetization policy: `https://support.google.com/youtube/answer/1311392`
- Instagram 2026 original-content / aggregator reach reporting: `https://techcrunch.com/2026/04/30/instagram-restricts-reach-of-content-aggregators-in-new-crackdown/`

## 4. Verification SOP

0. **Runtime evidence prerequisite**
   - Command/data setup:
     ```bash
     curl -sS -m 5 "$CORE_API/health" | jq '{status, llm_configured, llm_available, backend:(.components.backend // .services.backend.status)}'
     curl -sS -m 10 "$CORE_API/api/v1/capability-packs/" \
       | jq '.[] | select((.id // .code) == "ig" or (.id // .code) == "performance_direction") | {id:(.id // .code), enabled, installed, validation:(.validation.status // .validation_state)}'
     curl -sS -X POST "$CORE_API/api/v1/workspaces/$WORKSPACE_ID/object-graph/project" \
       -H 'Content-Type: application/json' \
       -d '{"objects":[{"uri":"mindscape://ig/reference/'"$IG_REF_A"'","owner_pack":"ig","object_kind":"reference","object_id":"'"$IG_REF_A"'"},{"uri":"mindscape://ig/reference/'"$IG_REF_B"'","owner_pack":"ig","object_kind":"reference","object_id":"'"$IG_REF_B"'"}],"include_relations":true,"include_summaries":true}' \
       | jq '{projection_count:(.projections | length), errors}'
     ```
   - Expected: control API responds before timeout; IG/PD packs are installed/enabled; fixture data is documented before E2E execution。
   - Fail: health or capability pack endpoint timeout, E2E 只引用 source-code fixture 與前端 mock，沒有 running runtime 驗證資料。
   - Proves: runtime evidence gate。

1. **Default AOL command routes to MeetingEngine orchestration**
   - Command:
     ```bash
     curl -sS -X POST "$CORE_API/api/v1/workspaces/$WORKSPACE_ID/meetings/$MEETING_ID/commands" \
       -H 'Content-Type: application/json' \
       -d '{"workspace_id":"'"$WORKSPACE_ID"'","meeting_id":"'"$MEETING_ID"'","origin_surface":"meeting_workbench","actor":"user","intent_text":"Use @ig.reference:'"$IG_REF_A"' and @ig.reference:'"$IG_REF_B"' to plan a 90s reels storyboard.","context_objects":[{"role":"source","ref":{"uri":"mindscape://ig/reference/'"$IG_REF_A"'","owner_pack":"ig","object_kind":"reference","object_id":"'"$IG_REF_A"'"}},{"role":"source","ref":{"uri":"mindscape://ig/reference/'"$IG_REF_B"'","owner_pack":"ig","object_kind":"reference","object_id":"'"$IG_REF_B"'"}}],"write_mode":"recommendation_only","thread_id":"'"$MEETING_ID"'","meeting_mentions":[],"metadata":{"dispatch_mode":"route_meeting_orchestration","selected_guidance_id":"ig-reference-director-guidance","selected_guidance_metadata":{"recommended_pack":"performance_direction","recommended_playbook":"pd_director_guidance"}}}' \
       | jq '{dispatch_mode:.command.metadata.dispatch_mode, task_ir_id:.dispatch_result.meeting_orchestration.task_ir_id, artifact_landing_status:.dispatch_result.meeting_orchestration.artifact_landing_status, metadata_persisted:.dispatch_result.meeting_orchestration.request_contract_aol_metadata_persisted, status:.command.status}'
     ```
   - Expected: command metadata has `dispatch_mode = route_meeting_orchestration`; `dispatch_result.meeting_orchestration.task_ir_id` is non-empty; selected guidance metadata appears under request-contract AOL metadata; artifact landing status is truthful。
   - Fail: response shows `route_object_action`, `route_playbook`, or direct task id without MeetingEngine evidence。
   - Proves: Problems 1 and 2.

2. **Bridge builds HandoffIn from AOL context**
   - Command:
     ```bash
     /Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/aol_meeting_orchestration_bridge_spec.py
     ```
   - Expected: `HandoffIn.context_attachments` contains role-bearing object refs, projections, selected guidance metadata, guidance hints, relation proof, and review routes; `HandoffIn.metadata["addressable_object_layer"]` contains command/session carrier fields; `candidate_playbooks` contains recommended playbook hints; `HandoffIn.playbook_requests` is `None`。
   - Fail: object refs are lost, `card.metadata` is dropped, guidance becomes hard route without explicit override, or IG/PD-specific logic appears in local-core。
   - Proves: Problems 3, 4, and 6.

3. **MeetingEngine runner persists TaskIR and request metadata**
   - Command:
     ```bash
     /Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/meeting_engine_runner_spec.py
     ```
   - Expected: `MeetingEngine.run()` is called once; `task_ir_id == meeting_result.task_ir.task_id`; `persist_meeting_task_ir()` is called; `session_store.update(session)` persists `session.metadata["request_contract"]["addressable_object_layer"]`; runner returns artifact landing summary。
   - Fail: runner returns `compiled_task_ir_id`, does not persist TaskIR, drops AOL metadata carrier, or marks artifact landing complete without DB/file evidence。
   - Proves: Problems 2 and 4.

4. **MeetingEngine.run() is invoked for AOL orchestration**
   - Command:
     ```bash
     /Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/test_meeting_command_envelope.py -k meeting_orchestration
     ```
   - Expected: `MeetingEngine.run()` receives user intent and `handoff_in`。
   - Fail: object runtime plan/invoke or `handle_suggestion_action` is called before MeetingEngine for default AOL commands。
   - Proves: Problems 2 and 4.

5. **Cross-pack object workflow fixture uses meeting-owned TaskIR**
   - Command:
     ```bash
     curl -sS -X POST "$CORE_API/api/v1/workspaces/$WORKSPACE_ID/meetings/$MEETING_ID/commands" \
       -H 'Content-Type: application/json' \
      -d '{"workspace_id":"'"$WORKSPACE_ID"'","meeting_id":"'"$MEETING_ID"'","origin_surface":"meeting_workbench","actor":"user","intent_text":"Use @'"$SOURCE_REF_A_TOKEN"' and @'"$SOURCE_REF_B_TOKEN"' to create a downstream artifact or proposal with meeting guidance.","context_objects":[{"role":"source","ref":{"uri":"'"$SOURCE_REF_A_URI"'","owner_pack":"'"$SOURCE_REF_A_OWNER"'","object_kind":"'"$SOURCE_REF_A_KIND"'","object_id":"'"$SOURCE_REF_A_ID"'"}}],"write_mode":"recommendation_only","thread_id":"'"$MEETING_ID"'","meeting_mentions":[],"metadata":{"dispatch_mode":"route_meeting_orchestration"}}' \
      | jq '{dispatch_mode:.command.metadata.dispatch_mode, task_ir_id:.dispatch_result.meeting_orchestration.task_ir_id, status:.command.status, command_id:.command_id}'
     ```
   - Expected: command row, HandoffIn context attachments, `session.metadata["request_contract"]["addressable_object_layer"]`, MeetingEngine events, ActionIntent or TaskIR, pack dispatch, artifact/proposal landing, graph/ledger notification all exist under the same meeting id。
   - Fail: result is produced only by direct playbook or object materializer without MeetingEngine evidence。
   - Fixture note: IG refs to downstream storyboard can populate the generic `SOURCE_*` variables as an installed-pack validation fixture, but this is not a local-core enum, route, or hard-coded contract。
   - Proves: Problem 6.

6. **Pack object guidance discussion fixture stays meeting-guided**
   - Command:
     ```bash
     curl -sS -X POST "$CORE_API/api/v1/workspaces/$WORKSPACE_ID/meetings/$MEETING_ID/commands" \
       -H 'Content-Type: application/json' \
      -d '{"workspace_id":"'"$WORKSPACE_ID"'","meeting_id":"'"$MEETING_ID"'","origin_surface":"'"$PACK_OBJECT_ORIGIN_SURFACE"'","actor":"user","intent_text":"Discuss guidance for @'"$TARGET_OBJECT_TOKEN"' through the meeting graph.","context_objects":[{"role":"target","ref":{"uri":"'"$TARGET_OBJECT_URI"'","owner_pack":"'"$TARGET_OBJECT_OWNER"'","object_kind":"'"$TARGET_OBJECT_KIND"'","object_id":"'"$TARGET_OBJECT_ID"'"}}],"write_mode":"recommendation_only","thread_id":"'"$MEETING_ID"'","meeting_mentions":[],"metadata":{"dispatch_mode":"route_meeting_orchestration"}}' \
      | jq '{dispatch_mode:.command.metadata.dispatch_mode, task_ir_id:.dispatch_result.meeting_orchestration.task_ir_id, status:.command.status, command_id:.command_id}'
     ```
   - Expected: target ObjectRef enters meeting context, MeetingEngine receives the object context, guidance/action/review nodes are created, and owner-pack execution happens after meeting orchestration。
   - Fail: pack UI calls direct pack API or direct playbook without MeetingEngine。
   - Fixture note: PD scene discussion can populate the generic `TARGET_OBJECT_*` variables as an installed-pack validation fixture, but this is not a local-core enum, route, or hard-coded contract。
   - Proves: Problems 1, 2, and 6.

7. **Artifact DB/file landing is truthful**
   - Command:
     ```bash
     curl -sS "$CORE_API/api/v1/workspaces/$WORKSPACE_ID/artifacts?thread_id=$MEETING_ID" \
       | jq '[.artifacts[]? | {id, title, artifact_type, file_path:(.file_path // .metadata.actual_file_path // .metadata.file_path // .storage_ref), metadata}]'
     ARTIFACT_FILE_PATH="$(curl -sS "$CORE_API/api/v1/workspaces/$WORKSPACE_ID/artifacts?thread_id=$MEETING_ID" | jq -r '.artifacts[0] | (.file_path // .metadata.actual_file_path // .metadata.file_path // .storage_ref // "")')"
     test -n "$ARTIFACT_FILE_PATH" && test -f "$ARTIFACT_FILE_PATH"
     ```
   - Expected: completed E2E has at least one artifact DB row for the meeting/thread and a file path/storage ref that resolves in the runtime environment。
   - Fail: only `task_ir.artifacts[]` exists, artifact DB list is empty, or file path is missing/unresolvable while status claims completed。
   - Proves: artifact landing gate.

8. **Community originality / review evidence is present**
   - Command:
     ```bash
     curl -sS "$CORE_API/api/v1/workspaces/$WORKSPACE_ID/meetings/$MEETING_ID/commands" \
       | jq --arg command_id "$COMMAND_ID" '.commands[] | select(.command_id == $command_id) | {source_refs:.metadata.meeting_orchestration.task_ir_artifacts, aol:.metadata.meeting_orchestration.request_contract_aol_metadata, artifact_landing_status:.metadata.meeting_orchestration.artifact_landing_status}'
     ```
   - Expected: output trace preserves source refs, selected guidance, director rationale or review route, and proposal/revision state when final artifact is not yet approved。
   - Fail: output is a generic generated result with no source refs, no rationale, no review state, or no provenance。
   - Proves: community originality gate.

9. **Cloud/local-core boundary remains clean**
   - Command:
     ```bash
     rg -n "mindscape-ai-cloud|capabilities/performance_direction|capabilities/ig|MINDSCAPE_REMOTE_CAPABILITIES_DIR" backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py backend/app/services/meeting_command_dispatch.py backend/app/routes/core/workspace/meeting_commands.py backend/app/services/orchestration/meeting/meeting_engine_runner.py
     ```
   - Expected: no new local-core runtime import/path dependency on cloud source repository; installed pack/runtime contract refs only。
   - Fail: bridge imports cloud source path or hard-codes IG/PD business API。
   - Proves: boundary compliance.

## 5. Automated test plan

1. **Backend command envelope orchestration tests**
   - Target: `backend/tests/test_meeting_command_envelope.py`。
   - Scenario: command with source and target refs, selected guidance metadata, and no explicit direct override。
   - Assertions: command dispatches as `route_meeting_orchestration`; direct `route_object_action` and `route_playbook` are not called; `MeetingEngine.run()` is called with `handoff_in`; explicit direct routes require `metadata.explicit_override = true`。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/test_meeting_command_envelope.py -k meeting_orchestration`。
   - Prevents regressions for Problems 1, 2, and 4.

2. **Bridge unit tests**
   - Target: `backend/tests/aol_meeting_orchestration_bridge_spec.py`。
   - Scenario: source refs, target refs, attach metadata, selected guidance metadata, graph guidance recommended playbook, required roles, review routes, and guidance-only command with no object refs。
   - Assertions: `HandoffIn.context_attachments` preserves roles/projections/guidance/review routes and selected `card.metadata`; recommended playbook appears only under `HandoffIn.metadata["addressable_object_layer"]["candidate_playbooks"]`; `HandoffIn.playbook_requests` is empty or `None`; empty object refs do not call `project_object_graph(objects=[])`。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/aol_meeting_orchestration_bridge_spec.py`。
   - Prevents regressions for Problems 3, 4, and 6.

3. **RequestContract merge tests**
   - Target: `backend/tests/meeting_engine_request_contract_aol_metadata_spec.py`。
   - Scenario: bridge-generated `HandoffIn` enters MeetingEngine。
   - Assertions: `metadata.context_attachments` and `session.metadata["request_contract"]["addressable_object_layer"]` appear in meeting request-contract metadata; selected guidance metadata is preserved; `metadata.playbook_requests` remains empty for guidance-only AOL bridge handoff; no pack-specific hardcoding is required。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/meeting_engine_request_contract_aol_metadata_spec.py`。
   - Prevents regressions for Problem 4.

4. **MeetingEngine runner tests**
   - Target: `backend/tests/meeting_engine_runner_spec.py`。
   - Scenario: runner receives a test meeting session, message, and bridge-generated `HandoffIn`。
   - Assertions: calls `MeetingEngine.run()` with `handoff_in`; persists `task_ir_id = meeting_result.task_ir.task_id`; calls `session_store.update(session)`; returns normalized orchestration evidence, artifact landing summary, and dependency failure metadata when runtime profile/execution launcher cannot be resolved。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/meeting_engine_runner_spec.py`。
   - Prevents regressions for Problems 2 and 4.

5. **Frontend dispatch tests**
   - Target: `web-console/src/components/capabilities/meeting-workbench/meetingCommandLedger.spec.ts`、`web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx`、`web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellMentions.spec.tsx`、`web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellPackFixtures.spec.tsx`。
   - Scenario: object refs, selected guidance, IG guidance command, ordinary pure chat。
   - Assertions: AOL/object/guidance/selected pack tool commands post `route_meeting_orchestration`; pure chat posts `route_chat`; no P0 frontend test expects `route_playbook` or `route_object_action`; `card.metadata.recommended_pack/recommended_playbook` is preserved; `meeting_orchestration` response updates task and notification; plain text containing email/social `@` remains chat unless parser extracted AOL refs。
   - Command:
     ```bash
     cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
     ./node_modules/.bin/vitest run src/components/capabilities/meeting-workbench/meetingCommandLedger.spec.ts src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx src/components/capabilities/meeting-workbench/AOLMeetingBottomShellMentions.spec.tsx src/components/capabilities/meeting-workbench/AOLMeetingBottomShellPackFixtures.spec.tsx --config vitest.config.ts
     ```
   - Prevents regressions for Problems 1, 2, and 6.

6. **IG/PD product fixture gate**
   - Target: manual live smoke SOP in this document plus future automation. There is currently no `backend/tests/test_ig_pd_meeting_orchestration_e2e.py` file in repo; do not cite that missing file as runnable evidence.
   - Scenario: IG reference guidance inserts command with source refs; PD scene discussion inserts scene ref。
   - Assertions: no frontend direct `/chat`, no direct `/object-actions/invoke` for default path, command row contains orchestration route, backend evidence shows MeetingEngine run, selected guidance metadata survives into request contract, artifact status is truthful, and originality/review metadata is present。
   - Command: use Verification SOP steps 0, 1, 5, 7, and 8 against a fresh post-restart command id. Expected current result is allowed to be `artifact_landing_status=pending` only if artifact DB/file output is absent; it is not allowed to claim final storyboard/proposal completion without artifact rows.
   - Prevents regressions for Problem 6.

7. **Boundary tests**
   - Target: repo-level grep check。
   - Scenario: bridge implementation in local-core。
   - Assertions: no cloud source path imports, no IG/PD-specific API calls in local-core host, no pack source direct filesystem access。
   - Command: `rg -n "mindscape-ai-cloud|capabilities/performance_direction|capabilities/ig|MINDSCAPE_REMOTE_CAPABILITIES_DIR" backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py backend/app/services/meeting_command_dispatch.py backend/app/routes/core/workspace/meeting_commands.py backend/app/services/orchestration/meeting/meeting_engine_runner.py`。
   - Prevents boundary regressions.

8. **Artifact landing tests**
   - Target: `backend/tests/meeting_engine_runner_spec.py` and the artifact landing service tests chosen during implementation。
   - Scenario: MeetingEngine returns TaskIR artifacts and pack dispatch result with output artifacts。
   - Assertions: runner reports `artifact_landing_status` truthfully; DB artifact row is created when output artifact payload is sufficient; missing artifact store or missing file path produces `pending` / `not_landed` instead of `completed`。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/meeting_engine_runner_spec.py -k artifact`。
   - Prevents false asset 入庫/入檔 claims.

9. **External agent transport ACK tests**
   - Target: `backend/tests/routes/test_agent_dispatch_pubsub.py`。
   - Scenario: cross-worker WS dispatch writes to the socket but the host client never sends the real task ACK。
   - Assertions: pub/sub dispatch does not treat socket write as task ACK; missing client ACK triggers bounded `agent_dispatch_ack_timeout` fallback instead of waiting for the whole MeetingEngine command timeout。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/routes/test_agent_dispatch_pubsub.py backend/tests/routes/agent_dispatch/test_db_fallback.py backend/tests/services/external_agents/test_host_bridge_runtime_adapter.py`。
   - Prevents false runtime availability and hidden external-agent hangs.

10. **Command timeout and late-result reconciliation tests**
   - Target: `backend/tests/meeting_command_dispatch_timeout_spec.py` and `backend/tests/meeting_command_status_sync_spec.py`。
   - Scenario: MeetingEngine command exceeds bounded command timeout; later WS/governance result lands with `meeting_command_id`; internal phase task carries the same command id after parent orchestration completed。
   - Assertions: timeout returns `meeting_orchestration_timeout`, `artifact_landing_status=pending`, `late_result_possible=true`; late result can recover a timed-out command and attach artifact ids/paths; internal phase tasks cannot demote the parent MeetingEngine command unless their runtime id matches `command.accepted_task_id`。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/meeting_command_dispatch_timeout_spec.py backend/tests/meeting_command_status_sync_spec.py`。
   - Prevents hidden hangs, false artifact failure, and parent-command demotion regressions.

11. **Graph command orchestration projection tests**
   - Target: `backend/tests/meeting_execution_graph_commands_spec.py`。
   - Scenario: command ledger rows contain MeetingEngine orchestration metadata, AOL request-contract metadata, timeout status, and artifact landing status。
   - Assertions: graph command nodes preserve `dispatch_mode`, `dispatch_status`, `meeting_orchestration_error_code`, `artifact_landing_status`, and request-contract AOL metadata for inspector/runtime proof。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/meeting_execution_graph_commands_spec.py`。
   - Prevents UI/runtime graph proof regressions.

12. **System health readiness tests**
   - Target: `backend/tests/system_health_checker_ollama_spec.py`。
   - Scenario: Ollama reports model tags; OCR service URL is unset and not required。
   - Assertions: Ollama health uses `/api/tags`, recognizes `ollama/qwen2.5:7b`, and optional OCR reports disabled without making the system unhealthy。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/system_health_checker_ollama_spec.py`。
   - Prevents runtime readiness false negatives.

13. **External dispatch payload correlation tests**
   - Target: `backend/tests/services/external_agents/test_dispatch_payload_auth_scope.py`。
   - Scenario: MeetingEngine downstream external-agent dispatch carries meeting command and AOL metadata through runtime payload context/metadata。
   - Assertions: payload includes `meeting_command_id`, `command_id`, `addressable_object_layer`, auth/source workspace scope, deliverable path/name/targets, and thread/session context。
   - Command: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/services/external_agents/test_dispatch_payload_auth_scope.py`。
   - Prevents late-result reconciliation from losing command correlation.

## 6. Live E2E evidence update - 2026-05-04

The latest verified transport and real-file landing evidence is recorded in:

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-real-file-e2e-evidence-2026-05-04.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-host-bridge-runtime-evidence-2026-05-04.md`

Current verified status:

- Command-ledger E2E `cmd_aol_real_e2e_files_20260504_021_tasklineage` completed through `route_meeting_orchestration`, MeetingEngine, downstream `performance_direction/pd_storyboard_gen` dispatch, artifact reconciliation, and command response.
- The command response returned `artifact_landing_status=landed`, TaskIR id `task_f385ff20d3364399`, downstream execution id `7ba39e58-e19f-4113-b8db-5547558e26bd`, and artifact DB ids:
  - `42e2c149-3c1e-42eb-aa58-d472437a55af` for contact-sheet SVG
  - `18420a74-86c5-4853-923a-1753c8ca8bb9` for proposal Markdown
  - `632f963a-a209-4a7e-b478-da165f2da2a2` for storyboard manifest JSON
- The files exist on the host runtime data volume under `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/sandboxes/.../current/artifacts/pd_storyboard_gen/7ba39e58-e19f-4113-b8db-5547558e26bd/`.
- The `artifacts` DB table contains all three rows with `thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1`, `task_id=task_f385ff20d3364399`, `metadata.actual_file_path`, `metadata.acceptance_evidence`, `metadata.pd_storyboard_evidence`, and `metadata.provenance.eval_summary.passed=true`.
- Content verification confirms storyboard id `sb_a75480dadd93`, direction session `ds_f4ae71893782`, command id `cmd_aol_real_e2e_files_20260504_021_tasklineage`, and selected AOL source refs `codex_aol_e2e_ref_a_20260503` / `codex_aol_e2e_ref_b_20260503`.
- Product content gate now passes for this fixture: `scene_count=9`, `total_duration_sec=90`, `all_have_frames=true`, `all_need_review=true`, `all_have_discussion_prompt=true`, `all_have_decision_items=true`, `all_have_review_candidates=true`, and `render_profile=pd_vertical_reels_storyboard`.
- Meeting asset lane data path is live: `GET /api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/artifacts?thread_id=0f2463d0-2f22-4016-9b5d-cb3b389eb8d1&limit=3` returned the `_021` contact-sheet/proposal/manifest set. Response `total=9` includes older `_019` and `_020` rows sharing the same meeting thread.
- Core runtime pack-rule exclusion is verified: `rg -n "pd_storyboard_evidence|storyboard_preview|selected_scene_package_selector" backend/app/services backend/app/models backend/tests` returned no matches. PD-specific evidence is pack-owned and carried through generic artifact metadata only.
- Targeted frontend verification passed: `./node_modules/.bin/vitest run src/components/capabilities/meeting-workbench/meetingCommandLedger.spec.ts src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx src/components/capabilities/meeting-workbench/AOLMeetingBottomShellLayout.spec.tsx src/components/capabilities/meeting-workbench/meetingGraphProjection.spec.ts` returned 4 files / 26 tests passed.
- Host bridge persistence evidence confirms LaunchAgent `ai.mindscape.cli-bridge` is loaded and target `codex_cli` bridge is under the launchd supervisor. After controlled kill of target PID `18082`, watcher logged `died, will respawn` and started PID `21617`, which connected and registered.

Current remaining scope:

- Closed for the tested IG refs -> MeetingEngine -> downstream PD storyboard fixture: transport, 90 秒 reels storyboard proposal, SVG storyboard image/contact sheet, proposal/manifest/contact-sheet DB rows, concrete files, TaskIR/thread lineage, and per-scene review carriers.
- Not claimed by this run: final rendered video or raster production frames beyond the SVG contact sheet, live human decision resolution for each scene, or exhaustive coverage for every future pack/object fixture.

## 7. Risks / open questions

1. **MeetingEngine construction duplication risk**：`MeetingEngineRunner` is the only place allowed to construct `MeetingEngine` for command-ledger orchestration. Code review must reject `MeetingEngine(` added to `meeting_commands.py` or `meeting_command_dispatch.py`。
2. **Guidance hint vs hard route semantics**：P0 bridge stores selected pack tool and `recommended_playbook` under `candidate_playbooks` only. Code review must reject bridge output that writes these hints into `HandoffIn.playbook_requests`。
3. **Attach materialization compatibility**：backend direct materialization remains outside P0 product route. E2E acceptance must reject outputs produced only by `dispatch_object_action_for_command()`。
4. **Runtime evidence scope risk**：current closure evidence is command `cmd_aol_real_e2e_files_20260504_021_tasklineage`. API/DB/filesystem checks prove the running instance uses `route_meeting_orchestration`, MeetingEngine AOL metadata persists, downstream dispatch completes, and command-level artifact ids/file paths resolve to contact-sheet/proposal/manifest DB rows plus real files. This does not prove final video/raster production frames, live human decision resolution, or every future pack fixture; those still need separate fresh runtime evidence.
5. **Memory/writeback scope**：P0 acceptance requires command-to-engine-to-task dispatch evidence. This P0 does not modify MeetingEngine finalize code。
6. **RequestContract model churn risk**：P0 must not add `RequestContract.metadata`。AOL metadata storage path is fixed at `session.metadata["request_contract"]["addressable_object_layer"]`。
7. **Pack install boundary risk**：IG/PD source changes must happen in cloud source and be installed through `.mindpack`; editing installed local-core payload invalidates verification。
8. **Selected guidance carrier loss risk**：如果 frontend 仍只送 `owner_pack` 或 `command_template`，bridge 會看不到 `recommended_pack` / `recommended_playbook`，MeetingEngine 只能做弱推斷。Code review must reject graph guidance metadata being dropped in `meetingGraphObjectProjection.ts`。
9. **Frontend false failure risk**：backend 成功回 `dispatch_result.meeting_orchestration` 但 frontend 未更新 handler 時，產品會顯示 dispatch error。Frontend tests must include this response shape。
10. **Runner dependency drift risk**：runtime profile、execution launcher、execution context 若用臨時 default 組出來，E2E 會在 live runtime 中不穩定。Implementation PR must include explicit dependency map and missing-dependency failure tests。
11. **Session metadata persistence risk**：只改 in-memory `session.metadata` 會讓 API/DB evidence 查不到 request-contract AOL carrier。Runner tests must spy/assert `session_store.update(session)`。
12. **Artifact false completion risk**：TaskIR artifact reference、pack response、proposal metadata 都不能單獨證明入庫入檔。E2E status must distinguish `landed`、`pending`、`not_landed`、`not_requested`。
13. **Community originality risk**：IG refs -> reels/storyboard output 若沒有 source evidence、director rationale、review/proposal state，容易變成低差異模板化生成。Completion criteria must require provenance and review trace。
14. **Historical failed row interpretation risk**：`cmd_aol_late_reconcile_smoke_20260503` is a useful evidence row for MeetingEngine completion and for the now-fixed internal-task demotion bug, but its top-level failed status was produced before the demotion fix was loaded. Do not use that historical parent status as the current acceptance result; rerun a fresh command after restart for release evidence.
