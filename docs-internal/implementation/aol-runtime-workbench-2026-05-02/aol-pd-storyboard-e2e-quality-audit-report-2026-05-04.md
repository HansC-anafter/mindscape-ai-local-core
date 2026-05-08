# AOL/PD Storyboard E2E 實作品質查驗報告（2026-05-04）

## 2026-05-05 Ledger Override

本文件受 `pd-storyboard-e2e-preflight-ledger-2026-05-05.md` 約束。本文原本查驗的是 `_021` 的 transport、artifact landing、session-scoped PD URL 缺口與 local-core 邊界；它不再構成 real IG refs 高品質 storyboard 內容驗收。任何新 E2E 必須先通過 `E2E-PD-PREFLIGHT-000`：workspace executor 為 `codex_cli`，selected refs 為 IG catalog real `ref_*`，analysis 為 `COMPLETED / visual_anatomy / 2.1`，`reference_cue_map.cue_count > 0`，90s reels target 為 45 scenes，且逐鏡 LLM judge 與 visual scope gate 都必須按要求通過。

## 結論

本次 P0 AOL → MeetingEngine → PD storyboard artifact landing 主線可以作為 legacy transport 收尾：`_021` 實跑資料證明 command 進入 `route_meeting_orchestration`，產生 TaskIR，dispatch 到 PD pack，並把 manifest、proposal、contact-sheet 三個 artifact 同時入庫與入檔。依 2026-05-05 ledger，此結論不得延伸為 real IG refs 高品質內容通過。

新增查驗問題「PD 是否對各別 storyboard 做唯一 project URL」的答案是：目前沒有。PD 目前提供 session-scoped workbench/API route 與 proposal review route，但沒有以 `storyboard_id` 作為 URL identity 的正式 project URL。此項已補進實作計劃作為未完成能力，不得宣稱已完成。

## 查驗規則來源

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/skills/evidence-based-reporting/SKILL.md | sed -n '8,24p'`
> ```text
> 8  ## Core Rule
> 10 **Every factual claim in a report, plan, or diagnostic document MUST have a corresponding evidence source collected BEFORE the claim is written.**
> 20 Runtime state ... ps aux, docker inspect, env, curl output
> 21 Database content ... psql / API query result
> 23 Code behavior ... Direct code citation with file path and line number
> ```

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-cloud/.agent/skills/mindscape-dev-guide/SKILL.md | sed -n '14,90p'`
> ```text
> 16 local-core is a runtime environment only.
> 20 FORBIDDEN in local-core:
> 29 No Cross-Repo File System Access
> 42 No Raw Capability Source in local-core
> 73 Language Rules (MANDATORY)
> 77 Code comments | English only
> 79 Logger messages | English only, no emoji
> 81 Internal docs (`docs-internal/`) | Traditional Chinese (zh-TW)
> 84 Forbidden in Code Comments
> ```

## PD Storyboard URL Identity

查驗結論：未設計 per-storyboard unique project URL。

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/services/object_layer/storyboard_runtime.py | sed -n '38,49p'`
> ```text
> 38 def _storyboard_route(session_id: str) -> str:
> 40     "/api/v1/capabilities/performance_direction/sessions/"
> 41     f"{session_id}/storyboard"
> 45 def _storyboard_workbench_route(workspace_id: str, session_id: str) -> str:
> 47     f"/workspaces/{workspace_id}/capabilities/"
> 48     f"performance_direction/sessions/{session_id}"
> ```

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/api/__init__.py | sed -n '931,933p'`
> ```text
> 931 @router.get("/sessions/{session_id}/storyboard")
> 932 async def get_storyboard(session_id: str):
> 933     """Get the latest canonical storyboard artifact plus pending proposal summaries."""
> ```

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/capabilities/performance_direction/routePaths.ts | sed -n '1,14p'`
> ```text
> 1  export function buildPerformanceDirectionStartPath(workspaceId: string): string {
> 5  export function buildPerformanceDirectionSessionBasePath(workspaceId: string): string {
> 9  export function buildPerformanceDirectionSessionPath(
> 10   workspaceId: string,
> 11   sessionId: string,
> 13   return `${buildPerformanceDirectionSessionBasePath(workspaceId)}/${encodeURIComponent(sessionId)}`;
> ```

> 證據：`jq '{storyboard_id,status,canonical_storyboard_route:(.canonical_storyboard_route // .global_settings.canonical_storyboard_route // null)}' .../pd_storyboard_manifest_7ba39e58-e19f-4113-b8db-5547558e26bd.json`
> ```json
> {
>   "storyboard_id": "sb_a75480dadd93",
>   "status": "draft",
>   "canonical_storyboard_route": null
> }
> ```

> 證據：`docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select id, artifact_type, metadata::jsonb->>'navigate_to' as navigate_to, metadata::jsonb->'pd_storyboard_evidence'->>'storyboard_id' as storyboard_id from artifacts where execution_id='7ba39e58-e19f-4113-b8db-5547558e26bd' order by created_at;"`
> ```text
> id                                   | artifact_type | navigate_to | storyboard_id
> 632f963a-a209-4a7e-b478-da165f2da2a2 | data          |             | sb_a75480dadd93
> 18420a74-86c5-4853-923a-1753c8ca8bb9 | draft         |             | sb_a75480dadd93
> 42e2c149-3c1e-42eb-aa58-d472437a55af | image         |             | sb_a75480dadd93
> ```

## P0 Gate 對齊

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-to-meeting-engine-orchestration-bridge-implementation-plan-2026-05-03.md | sed -n '12,25p'`
> ```text
> 16 跨 pack object refs ... 目前已實作 true
> 17 原始指令 #2 ... 90s reels 分鏡 ... true
> 18 完成分鏡圖製作 ... true
> 19 Pack-owned object discussion ... true
> 20 資產入庫 ... true
> 21 資產入檔 ... true
> 22 UX/UI 編排補全 ... true
> 23 workspace codex_cli host bridge 常駐與自動復活 ... true
> 24 local-core runtime 不得硬寫 PD/pack-specific storyboard evidence 規則 ... true
> ```

> 證據：`docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select command_id, status, accepted_task_id, metadata::jsonb->>'dispatch_mode' as dispatch_mode, metadata::jsonb->>'dispatch_status' as dispatch_status, metadata::jsonb#>>'{meeting_orchestration,task_ir_id}' as task_ir_id, metadata::jsonb#>>'{meeting_orchestration,artifact_landing_status}' as landing_status, metadata::jsonb#>>'{meeting_orchestration,request_contract_aol_metadata_persisted}' as aol_metadata_persisted, jsonb_array_length(metadata::jsonb#>'{meeting_orchestration,artifact_db_ids}') as artifact_db_count from meeting_commands where command_id='cmd_aol_real_e2e_files_20260504_021_tasklineage';"`
> ```text
> command_id                                      | status    | accepted_task_id      | dispatch_mode               | dispatch_status | task_ir_id            | landing_status | aol_metadata_persisted | artifact_db_count
> cmd_aol_real_e2e_files_20260504_021_tasklineage | completed | task_f385ff20d3364399 | route_meeting_orchestration | completed       | task_f385ff20d3364399 | landed         | true                   | 3
> ```

> 證據：`docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "select id, thread_id, task_id, execution_id, playbook_code, artifact_type, metadata::jsonb->>'actual_file_path' as actual_file_path, metadata::jsonb->'acceptance_evidence'->>'status' as acceptance_status, metadata::jsonb->'pd_storyboard_evidence'->>'storyboard_id' as storyboard_id, metadata::jsonb#>>'{provenance,eval_summary,passed}' as eval_passed from artifacts where execution_id='7ba39e58-e19f-4113-b8db-5547558e26bd' order by created_at;"`
> ```text
> id                                   | thread_id                            | task_id               | execution_id                         | playbook_code     | artifact_type | acceptance_status | storyboard_id    | eval_passed
> 632f963a-a209-4a7e-b478-da165f2da2a2 | 0f2463d0-2f22-4016-9b5d-cb3b389eb8d1 | task_f385ff20d3364399 | 7ba39e58-e19f-4113-b8db-5547558e26bd | pd_storyboard_gen | data          | completed         | sb_a75480dadd93 | true
> 18420a74-86c5-4853-923a-1753c8ca8bb9 | 0f2463d0-2f22-4016-9b5d-cb3b389eb8d1 | task_f385ff20d3364399 | 7ba39e58-e19f-4113-b8db-5547558e26bd | pd_storyboard_gen | draft         | completed         | sb_a75480dadd93 | true
> 42e2c149-3c1e-42eb-aa58-d472437a55af | 0f2463d0-2f22-4016-9b5d-cb3b389eb8d1 | task_f385ff20d3364399 | 7ba39e58-e19f-4113-b8db-5547558e26bd | pd_storyboard_gen | image         | completed         | sb_a75480dadd93 | true
> ```

> 證據：`jq '{storyboard_id,status,scene_count:(.scenes|length),total_duration_sec:([.scenes[].duration_sec]|add),all_frames:all(.scenes[];.scene_manifest.storyboard_frame!=null),all_review_prompts:all(.scenes[];.scene_manifest.meeting_discussion_prompt!=null),all_decision_items:all(.scenes[];(.decision_items|length)>0),all_review_candidates:all(.scenes[];(.review_candidates|length)>0),all_need_review:all(.scenes[];.approval_state=="needs_review"),render_profile:.render_profile.profile_id,source_refs:.global_settings.aol_reference_ids}' .../pd_storyboard_manifest_7ba39e58-e19f-4113-b8db-5547558e26bd.json`
> ```json
> {
>   "storyboard_id": "sb_a75480dadd93",
>   "status": "draft",
>   "scene_count": 9,
>   "total_duration_sec": 90,
>   "all_frames": true,
>   "all_review_prompts": true,
>   "all_decision_items": true,
>   "all_review_candidates": true,
>   "all_need_review": true,
>   "render_profile": "pd_vertical_reels_storyboard",
>   "source_refs": [
>     "codex_aol_e2e_ref_a_20260503",
>     "codex_aol_e2e_ref_b_20260503"
>   ]
> }
> ```

> 證據：`file .../pd_storyboard_contact_sheet_7ba39e58-e19f-4113-b8db-5547558e26bd.svg .../pd_storyboard_proposal_7ba39e58-e19f-4113-b8db-5547558e26bd.md .../pd_storyboard_manifest_7ba39e58-e19f-4113-b8db-5547558e26bd.json`
> ```text
> pd_storyboard_contact_sheet_7ba39e58-e19f-4113-b8db-5547558e26bd.svg: SVG Scalable Vector Graphics image
> pd_storyboard_proposal_7ba39e58-e19f-4113-b8db-5547558e26bd.md: Unicode text, UTF-8 text
> pd_storyboard_manifest_7ba39e58-e19f-4113-b8db-5547558e26bd.json: JSON data
> ```

## Core/Pack 邊界

local-core 只做 generic artifact/task/thread reconciliation；PD-specific evidence 由 PD pack 產生，透過 playbook output metadata generic value carrier 入庫。這符合「cloud/pack 實作不得改 local-core 架構邊界」要求。

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/tools/storyboard_gen.py | sed -n '918,998p'`
> ```text
> 918 acceptance_evidence = {
> 920     "playbook_code": "pd_storyboard_gen",
> 922     "storyboard_id": storyboard_json.get("storyboard_id"),
> 925     "status": "completed",
> 928 pd_storyboard_evidence = {
> 970 eval_summary = {
> 971     "passed": all(eval_checks.values()),
> 995 "acceptance_evidence": acceptance_evidence,
> 996 "pd_storyboard_evidence": pd_storyboard_evidence,
> 997 "eval_summary": eval_summary,
> ```

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/playbooks/specs/pd_storyboard_gen.json | sed -n '238,331p'`
> ```text
> 238 "acceptance_evidence": { "source": "step.generate_storyboard.acceptance_evidence" }
> 243 "pd_storyboard_evidence": { "source": "step.generate_storyboard.pd_storyboard_evidence" }
> 248 "eval_summary": { "source": "step.generate_storyboard.eval_summary" }
> 254 "output_artifacts": [
> 266 "acceptance_evidence": { "value_from": "step.generate_storyboard.acceptance_evidence" }
> 269 "pd_storyboard_evidence": { "value_from": "step.generate_storyboard.pd_storyboard_evidence" }
> 272 "provenance": { "eval_summary": { "value_from": "step.generate_storyboard.eval_summary" } }
> ```

> 證據：`rg -n "pd_storyboard_evidence|storyboard_preview|selected_scene_package_selector|pd_storyboard_gen|performance_direction" <本次 local-core backend app/tests 變更檔案清單>`
> ```text
> no matches
> ```

> 證據：`rg -n "MINDSCAPE_REMOTE_CAPABILITIES_DIR|mindscape-ai-cloud|/Users/shock/Projects_local/workspace/mindscape-ai-cloud|remote_capabilities_dir|remote_capabilities|cloud_path|\\.\\./.*capabilit" <本次 local-core backend app 變更檔案清單>`
> ```text
> no matches
> ```

## 失敗 Artifact 不可算 Landed

此規則已用 generic core 邏輯與 generic 測試覆蓋，沒有寫入 PD-specific runtime gate。

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/meeting_engine_runner.py | sed -n '96,122p'`
> ```text
> 101 status = (_clean_string(content.get("status")) or "").lower()
> 102 if status in {"error", "failed", "failure"}:
> 105 steps = _as_dict(content.get("steps"))
> 109 if step_status in {"error", "failed", "failure"}:
> 111     return f"step_failed:{step_id}:{reason}"
> 113 result = _as_dict(content.get("result"))
> 114 if result.get("success") is False:
> 117 output = _as_dict(content.get("output"))
> 118 if output.get("success") is False:
> ```

> 證據：`nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/meeting_engine_runner_spec.py | sed -n '486,578p'`
> ```text
> 487 async def test_meeting_engine_runner_does_not_land_failed_dispatch_execution_artifacts(monkeypatch):
> 504 "playbook_code": "generic_output_playbook"
> 537 "generate_output": {
> 538     "status": "error",
> 567 assert result["artifact_ids"] == []
> 568 assert result["artifact_db_ids"] == []
> 569 assert result["artifact_file_paths"] == []
> 570 assert result["artifact_landing_status"] == "failed"
> ```

## 註釋與語系規則查驗

> 證據：`rg -n "🔍|⚠|✅|❌|🚀|🆕|🔴|💀|📋|🔥|🐛|✨|Implementation Step|DONE:|Step [0-9]|Phase [0-9]|M[0-9]+ Week|Day [0-9]" <本次 local-core backend app/tests 變更檔案清單>`
> ```text
> no matches
> ```

> 證據：`rg -n "^[[:space:]]*(#|//|/\\*|\\*|\\\"\\\"\\\").*[一-龥]" <本次 local-core backend app/tests 變更檔案清單>`
> ```text
> no matches
> ```

> 證據：`rg -n "🔍|⚠|✅|❌|🚀|🆕|🔴|💀|📋|🔥|🐛|✨|Implementation Step|DONE:|Step [0-9]|Phase [0-9]|M[0-9]+ Week|Day [0-9]" <本次 cloud performance_direction 變更檔案清單>`
> ```text
> no matches
> ```

> 證據：`rg -n "^[[:space:]]*(#|//|/\\*|\\*|\\\"\\\"\\\").*[一-龥]" <本次 cloud performance_direction Python/test 變更檔案清單>`
> ```text
> no matches
> ```

補充：`backend/app/services/orchestration/meeting/engine.py` 仍有既有中文 string literal 用於 deliverable 名稱/token matching，這不是本次 diff 新增，也不是註釋或 logger。未把它列為本次註釋規則違反。

## 測試與 Runtime 證據

通過：

> 證據：`.venv/bin/python -m pytest backend/tests/aol_meeting_orchestration_bridge_spec.py backend/tests/meeting_engine_runner_spec.py backend/tests/routes/test_agent_dispatch_pubsub.py backend/tests/dispatch_orchestrator_idempotency_spec.py backend/tests/handoff_model_contract_spec.py backend/tests/meeting_command_dispatch_timeout_spec.py backend/tests/meeting_command_status_sync_spec.py backend/tests/meeting_engine_request_contract_aol_metadata_spec.py backend/tests/meeting_execution_graph_commands_spec.py backend/tests/playbook_finalization_spec.py backend/tests/system_health_checker_ollama_spec.py backend/tests/services/test_playbook_output_artifact_creator.py backend/tests/services/playbook_run_executor_runtime_workflow_test.py`
> ```text
> 34 passed, 176 warnings in 23.81s
> ```

> 證據：`./node_modules/.bin/vitest run src/components/capabilities/meeting-workbench/meetingCommandLedger.spec.ts src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx src/components/capabilities/meeting-workbench/AOLMeetingBottomShellLayout.spec.tsx src/components/capabilities/meeting-workbench/meetingGraphProjection.spec.ts`
> ```text
> Test Files  4 passed (4)
> Tests       26 passed (26)
> ```

> 證據：`PYTHONPATH=/Users/shock/Projects_local/workspace/mindscape-ai-cloud /Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest capabilities/performance_direction/tests`
> ```text
> 187 passed, 49 warnings in 4.24s
> ```

> 證據：`.venv/bin/python -m py_compile backend/app/services/playbook_output_artifact_creator.py backend/app/services/workflow/playbook_finalization.py backend/app/services/playbook_run_executor_core/runtime_workflow.py backend/app/services/orchestration/meeting/meeting_engine_runner.py`
> ```text
> exit code 0
> ```

> 證據：`git diff --check` in local-core and cloud
> ```text
> exit code 0
> ```

> 證據：`curl -sS http://localhost:8220/healthz`、`curl -sS http://localhost:8200/healthz`
> ```json
> {"status":"ok","backend_role":"control","reload_enabled":true}
> {"status":"ok","backend_role":"execution","reload_enabled":false}
> ```

未通過但不屬於本次 P0 meeting-workbench gate：

> 證據：`./node_modules/.bin/vitest run src/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage.test.tsx`
> ```text
> Test Files  1 failed (1)
> Tests       10 failed | 18 passed (28)
> ```

這個失敗集中在 PD editor 單檔 spec 的 slot/package/production-design 深層互動期望，例如 `character_lora_loader`、`Assign to subj_b_face`、production-design brief label 等元素找不到。該結果不能當成 P0 AOL/MeetingEngine 收尾阻斷證據，但在修復前也不能宣稱 PD editor 全量 regression green。

## 主流網路社區環境對齊

目前設計方向沒有脫節，但外部發布前仍需補平台 disclosure/export mapping。理由如下：

- YouTube Help 對 realistic altered/synthetic content 要求 creator disclose；本實作保留 `acceptance_evidence`、`pd_storyboard_evidence`、`provenance.eval_summary`，符合「可解釋與可揭露」方向，但尚未把 disclosure field 映射到外部發布流程。來源：[YouTube Help: Disclosing use of altered or synthetic content](https://support.google.com/youtube/answer/14328491?hl=en-GB)。
- TikTok Help 說 realistic AIGC 需要 label，且 TikTok 2026 newsroom 提到 AIGC feed control 與更進階 labeling。PD 目前的 source refs、human review、per-scene decision carrier 符合透明與可控趨勢，但若輸出到 TikTok，需要明確 export `ai_generated` / disclosure 狀態。來源：[TikTok Help: AI-generated content](https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content?ref_type=adv)、[TikTok Newsroom 2026-03-10](https://newsroom.tiktok.com/tiktok-ssa-shares-more-ways-to-spot-shape-and-understand-ai-generated-content?lang=en-ZA)。
- Meta 針對 Facebook/Instagram/Threads 的 AI-generated images 採用 industry-standard indicators 與 AI label；本實作的 provenance/evidence 可作為內部來源，但仍需外部 content credentials/disclosure 封裝。來源：[Meta: Labeling AI-Generated Images on Facebook, Instagram and Threads](https://about.fb.com/news/2024/02/labeling-ai-generated-images-on-facebook-instagram-and-threads/?content_id=rafERdgyQvid1hB)。
- Google Search scaled content abuse policy 針對大量低價值、非原創內容，不論是否由 AI 產生。本實作在 `_021` manifest 中保留 source refs、transformation policy、review prompts、decision items，方向上避免 low-variation template output；但若後續批量發布，仍需在 publish layer 加入 uniqueness/value gate。來源：[Google Search spam policies](https://developers.google.com/search/docs/essentials/spam-policies)、[Google guidance on generative AI content](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content)。

## 提交判斷

可提交範圍：

- local-core P0 runtime/orchestration/artifact lineage 修正。
- cloud PD pack 產生 pack-owned storyboard evidence、manifest/proposal/contact-sheet output artifacts。
- 本報告與實作計劃中的 per-storyboard URL gap 記錄。

不得在提交說明中宣稱：

- PD 已有 per-storyboard unique project URL。
- PD editor 單檔 vitest 全量通過。
- local-core 擁有 PD-specific evidence validation gate。
