# PD 導演思維決策閉環提交前品質查驗報告

日期：2026-05-04

## 1. 查驗結論

本次可提交範圍分成兩個 repo：

- `mindscape-ai-local-core`：只提交 generic runtime 支援，包含 Artifact API 回傳 `task_id`、Task executor retry/tool-load 行為、AOL explicit playbook request gating、MeetingEngine 將已安裝 explicit request playbook 加入 policy allowlist cache。未在 local-core 加入 PD pack 專屬 artifact acceptance 規則。
- `mindscape-ai-cloud`：提交 pack-owned 實作，包含 PD director guidance 三段 thinking prompts、落庫/落檔 output artifacts、durable storyboard URL / asset index、PD UI asset index 與 director guidance dock、MMS production run refresh/storyboard lookup。

不提交範圍：

- `mindscape-ai-cloud/.tmp/**`：工作產物，未 stage。
- `mindscape-ai-cloud/capabilities/performance_direction/playbooks/specs/pd_storyboard_gen.json`、`schema/__init__.py`、`tools/storyboard_gen.py`、`config/reels_market_fit_policy.json`、`schema/reels_script_market_fit.py`、`services/reels_script_market_fit.py`、`tests/reels_script_market_fit_test.py`：屬於 IG Reels script market fit 另一階段工作，未 stage。
- `mindscape-ai-local-core/web-console/src/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage.test.tsx`：本 repo 測試現況不閉環，未 stage。
- local-core 被 `.gitignore` 擋下的既有 `docs-internal/.../pd-director-guidance-decision-loop-*.md` 不作為 raw pack 強制提交。

## 2. 規範依據

> Evidence: `sed -n '1,180p' .agent/skills/mindscape-dev-guide/SKILL.md`
> ```
> Code / comments / logger messages language: English only
> local-core is a runtime environment only.
> Never commit raw capability source code directly into local-core/backend/app/capabilities/.
> No Chinese in .py / .ts / .tsx / .js files
> No emoji in code comments or logger messages
> ```

> Evidence: `sed -n '1,220p' .agent/skills/evidence-based-reporting/SKILL.md`
> ```
> Every factual claim in a report, plan, or diagnostic document MUST have a corresponding evidence source collected BEFORE the claim is written.
> ```

## 3. 架構邊界查驗

local-core 本次 runtime diff 沒有新增 PD-specific boundary coupling。

> Evidence: `rg -n "backend/app/capabilities|MINDSCAPE_REMOTE_CAPABILITIES_DIR|\\.\\.\\/mindscape-ai-cloud|performance_direction|pd_director|pd_storyboard" backend/app/routes/core/artifacts.py backend/app/runner/task_executor.py backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py backend/app/services/orchestration/meeting/engine.py`
> ```
> <no output>
> ```

MeetingEngine 只把 request contract 內的 explicit playbook requests 與已安裝 playbook spec 做 generic allowlist cache 補齊。

> Evidence: `nl -ba backend/app/services/orchestration/meeting/engine.py | sed -n '442,478p'`
> ```
> 442 def _ensure_requested_playbooks_in_available_cache(self) -> None:
> 443     """Add installed explicit request playbooks to the policy allowlist cache."""
> 444     contract = self._get_request_contract_metadata()
> 445     requests = self._extract_request_contract_playbook_requests(contract)
> 464     for item in requests:
> 465         playbook_code = str(item.get("playbook_code") or "").strip()
> 468         if load_playbook_spec is None or load_playbook_spec(playbook_code) is None:
> 469             continue
> 476     self._available_playbooks_cache = "\n".join(
> ```

AOL bridge 只在 generic metadata/action parameter 明確允許時把 `requested_action` 升級成 hard playbook request；candidate affordance 不會被當成硬 dispatch。

> Evidence: `nl -ba backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py | sed -n '219,264p'`
> ```
> 219 def _allow_requested_action_hard_playbook_request(
> 224     if _truthy_flag(metadata.get("force_playbook_request")):
> 225         return True, "metadata.force_playbook_request"
> 232     return False, "candidate_affordance_only"
> 256 if requested_action and requested_action.playbook_code:
> 258     allowed, reason = _allow_requested_action_hard_playbook_request(
> 262     aol_metadata["hard_playbook_request_allowed"] = allowed
> 264     if allowed and verb in {"execute_playbook", "run_playbook", "invoke_playbook"}:
> ```

## 4. PD pack 實作對齊查驗

PD director guidance 的三段思考引導在 cloud pack 內實作，沒有下沉到 core runtime。

> Evidence: `nl -ba capabilities/performance_direction/services/director_guidance.py | sed -n '338,427p'`
> ```
> 357 title="Director context prompt"
> 383 title="Evidence boundary prompt"
> 410 title="Decision path prompt"
> 421 "accept_proposal",
> 422 "request_revision",
> 423 "reject_or_rerun_with_reason",
> ```

PD playbook spec 宣告三個可落檔 output artifacts。

> Evidence: `nl -ba capabilities/performance_direction/playbooks/specs/pd_director_guidance.json | sed -n '121,180p'`
> ```
> 123 "id": "director_guidance_state_file"
> 137 "file_write": {
> 138   "enabled": true
> 144 "id": "director_evidence_dock_state_file"
> 156 "file_write": {
> 157   "enabled": true
> 163 "id": "director_proposal_draft_file"
> 175 "file_write": {
> 176   "enabled": true
> ```

PD durable storyboard URL 由 cloud pack API 提供，不改 local-core route。

> Evidence: `nl -ba capabilities/performance_direction/api/__init__.py | sed -n '944,980p'`
> ```
> 944 @router.get("/sessions/{session_id}/storyboards")
> 957 @router.get("/storyboards/{storyboard_id}")
> 970 @router.get("/storyboards/{storyboard_id}/assets")
> ```

storyboard instance view 回傳 `storyboard_instance_route` 與 asset index。

> Evidence: `nl -ba capabilities/performance_direction/tools/storyboard_patch.py | sed -n '1281,1334p'`
> ```
> 1281 def build_storyboard_instance_view_from_artifacts(
> 1311 assets = _build_storyboard_asset_records(
> 1328 "storyboard_instance_route": (
> 1329     "/api/v1/capabilities/performance_direction/storyboards/"
> 1332 "assets": assets,
> 1333 "asset_count": len(assets),
> ```

MMS production run lookup/refresh 也停留在 cloud pack。

> Evidence: `nl -ba capabilities/multi_media_studio/models/production_run.py | sed -n '171,220p'`
> ```
> 171 def list_runs_for_storyboard(
> 202 projects_root = _storage_base() / tenant_id / "multi_media_studio" / "projects"
> 218 if run_storyboard_id == normalized_storyboard_id:
> 219     matched_runs.append(run)
> ```

## 5. 註釋與語系查驗

selected local-core added lines 沒有新增中文、TODO/FIXME、implementation-step 詞、emoji。

> Evidence: `git diff -U0 -- backend/app/routes/core/artifacts.py backend/app/runner/task_executor.py backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py backend/app/services/orchestration/meeting/engine.py backend/tests/aol_meeting_orchestration_bridge_spec.py backend/tests/artifacts_response_task_id_spec.py | rg -n "^\\+.*([一-龥]|TODO|FIXME|步驟|紀錄|記錄|實作|✅|❌|⚠|🆕|🔴|🟡|🟢)"`
> ```
> <no output>
> ```

selected cloud tracked diff 沒有新增中文、TODO/FIXME、implementation-step 詞、emoji。

> Evidence: `git diff -U0 -- capabilities/performance_direction capabilities/multi_media_studio capabilities/ui/test vitest.cloud-ui.config.cjs | rg -n "^\\+.*([一-龥]|TODO|FIXME|步驟|紀錄|記錄|實作|✅|❌|⚠|🆕|🔴|🟡|🟢)"`
> ```
> <no output>
> ```

selected cloud untracked code/test files 沒有中文、TODO/FIXME、implementation-step 詞、emoji。

> Evidence: `rg -n "[一-龥]|TODO|FIXME|步驟|紀錄|記錄|實作|✅|❌|⚠|🆕|🔴|🟡|🟢" capabilities/performance_direction/ui/components/storyboardEditor/StoryboardAssetIndexPanel.tsx capabilities/multi_media_studio/tests/production_run_model_test.py capabilities/ui/test/dockviewMock.tsx capabilities/ui/test/emptyStyleMock.ts capabilities/ui/test/excalidrawMock.tsx capabilities/ui/test/reactflowMock.tsx`
> ```
> <no output>
> ```

## 6. 測試證據

local-core backend targeted tests 通過。

> Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/aol_meeting_orchestration_bridge_spec.py backend/tests/artifacts_response_task_id_spec.py backend/tests/services/orchestration/meeting/test_dispatch_policy_gate.py -q`
> ```
> 19 passed, 156 warnings in 4.64s
> ```

cloud backend targeted tests 使用相容 Python runtime 通過。

> Evidence: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest capabilities/performance_direction/tests/director_guidance_test.py capabilities/performance_direction/tests/director_guidance_api_test.py capabilities/performance_direction/tests/reference_aware_director_compile_test.py capabilities/performance_direction/tests/reference_aware_director_compile_api_test.py capabilities/performance_direction/tests/storyboard_manifest_contract_test.py capabilities/performance_direction/tests/storyboard_patch_test.py capabilities/multi_media_studio/tests/production_runs_api_test.py capabilities/multi_media_studio/tests/production_run_model_test.py -q`
> ```
> 50 passed, 44 warnings in 3.88s
> ```

cloud UI targeted tests 通過。

> Evidence: `web-console/node_modules/.bin/vitest run --config vitest.cloud-ui.config.cjs capabilities/performance_direction/ui/components/PerformanceDirectionStoryboardEditorPage.test.tsx capabilities/performance_direction/ui/components/storyboardEditor/DirectorGuidanceDock.test.tsx`
> ```
> Test Files  2 passed (2)
> Tests  30 passed (30)
> Duration  71.13s
> ```

local-core web-console 同名測試未納入提交，因為在 local-core repo 現況下未閉環。

> Evidence: `node_modules/.bin/vitest run --config vitest.config.ts src/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage.test.tsx`
> ```
> Test Files  1 failed (1)
> Tests  14 failed | 15 passed (29)
> ```

## 7. Runtime E2E 證據

control/execution backend health 皆正常。

> Evidence: `curl -sS -m 8 http://localhost:8220/healthz`
> ```
> {"status":"ok","backend_role":"control","reload_enabled":true}
> ```

> Evidence: `curl -sS -m 8 http://localhost:8200/healthz`
> ```
> {"status":"ok","backend_role":"execution","reload_enabled":false}
> ```

director guidance E2E command 已 completed，dispatch ok，artifact landing landed，artifact DB rows 6 筆。

> Evidence: `curl -sS -m 20 'http://localhost:8220/api/v1/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/meetings/0f2463d0-2f22-4016-9b5d-cb3b389eb8d1/commands' | jq '.commands[] | select(.command_id == "cmd_aol_pd_director_guidance_20260504_006_prompt_gate_closed_loop") | {status, accepted_task_id, task_ir_id: .metadata.meeting_orchestration.task_ir_id, artifact_landing_status: .metadata.meeting_orchestration.artifact_landing_status, dispatch_status: .metadata.meeting_orchestration.dispatch_result.status, succeeded: .metadata.meeting_orchestration.dispatch_result.succeeded, failed: .metadata.meeting_orchestration.dispatch_result.failed, artifact_db_ids: .metadata.meeting_orchestration.artifact_db_ids}'`
> ```
> {
>   "status": "completed",
>   "accepted_task_id": "task_2937844224cf4f02",
>   "task_ir_id": "task_2937844224cf4f02",
>   "artifact_landing_status": "landed",
>   "dispatch_status": "ok",
>   "succeeded": 2,
>   "failed": 0,
>   "artifact_db_ids": [
>     "0b45ad00-abe2-4af2-b78f-a415a30a72cb",
>     "7aa47e5a-8b09-4d47-94bd-750015da6022",
>     "729083e0-b046-4657-a5f8-38288f7ceae6",
>     "424b9b79-ed81-48c9-951c-a475ce206d5c",
>     "9fe39bca-fb8f-4060-b668-52cb718811f3",
>     "f9a35f30-ab2d-4fe1-80cf-7f56f0bcf764"
>   ]
> }
> ```

落檔 guidance state 證明三段 prompt、guidance cards、evidence dock、proposal draft、PD patch origin。

> Evidence: `jq '{kind, scene_id, prompts: (.thinking_prompts | length), prompt_axes: [.thinking_prompts[].metadata.decision_axis], prompt_titles: [.thinking_prompts[].title], cards: (.guidance_cards | length), evidence_attachments: (.evidence_dock_state.attachments | length), missing_projection_fields: (.evidence_dock_state.missing_projection_fields | length), proposal_tool: .proposal_draft.materialization_tool, patch_origin_hint: .proposal_draft.review_route.storyboard_patch_proposal_origin}' '/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/sandboxes/bac7ce63-e768-454d-96f3-3a00e8e1df69/project_repo/af1c83dc-ffea-4052-b0b4-bbf48d3fdba7/current/artifacts/pd_director_guidance/ec0a8fb9-114b-47d1-82d9-d052a2c16394/pd_director_guidance_state_ec0a8fb9-114b-47d1-82d9-d052a2c16394.json'`
> ```
> {
>   "kind": "director_guidance_state",
>   "scene_id": "sc01",
>   "prompts": 3,
>   "prompt_axes": ["context", "evidence", "next_state"],
>   "prompt_titles": [
>     "Director context prompt",
>     "Evidence boundary prompt",
>     "Decision path prompt"
>   ],
>   "cards": 3,
>   "evidence_attachments": 1,
>   "missing_projection_fields": 3,
>   "proposal_tool": "pd_reference_aware_director_compile",
>   "patch_origin_hint": "pd"
> }
> ```

## 8. 提交策略

應提交：

- local-core selected runtime/tests/docs/report：generic Meeting/AOL/artifact support 與本報告。
- cloud selected PD/MMS/runtime UI/tests：pack-owned director guidance、storyboard URL/asset index、MMS production run support。

不得提交：

- local-core raw capability pack source。
- cloud `.tmp/**`。
- Reels script market-fit tracked/untracked files。
- local-core web-console failing test file。
