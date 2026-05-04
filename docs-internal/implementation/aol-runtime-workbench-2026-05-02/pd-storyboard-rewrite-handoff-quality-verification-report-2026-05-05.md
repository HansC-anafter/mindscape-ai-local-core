---
title: PD Storyboard Rewrite Handoff 品質查驗報告
date: 2026-05-05
status: completed
owner: local-core / performance_direction
skill_alignment: evidence-based-reporting
---

# PD Storyboard Rewrite Handoff 品質查驗報告

最後更新：2026-05-05。

## 結論

本次可閉環提交範圍包含 cloud `performance_direction` pack 的 storyboard content rewrite pass、producer-provided rewrite dispatch request、local-core generic Meeting quality gate/handoff、playbook output artifact materialization、capability metadata endpoint，以及 AOL host shell 的 installed capability lookup。cloud source commit 後已重新打包 `.mindpack`，並透過 local-core install API 正式安裝與重啟 backend。

不納入本次提交範圍的 dirty/WIP 包含 cloud `capabilities/ig/**`、cloud `.tmp/**`、local-core settings UI、runner resource pressure path，以及 `PerformanceDirectionStoryboardEditorPage.test.tsx` 中尚未閉環的大型 storyboard editor case。

> **Evidence**: `git status --short` scoped review, 2026-05-05。
> ```
> cloud dirty includes capabilities/ig/**, .tmp/**, and capabilities/performance_direction/**.
> local-core dirty includes Meeting/AOL/artifact/UI host files plus settings, runner resource, and PerformanceDirectionStoryboardEditorPage.test.tsx.
> ```

## 實作對齊

### Cloud pack source

- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/tools/storyboard_content_rewrite.py:140` 新增 pack-owned rewrite tool；同檔 `:165` 至 `:202` 在 reference analysis 不足時回傳 `needs_reference_analysis`，不憑空生成 rewritten storyboard。
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/services/storyboard_content_quality.py:198` 產生 producer eval summary；同檔 `:226` 至 `:227` 只有在 rewrite recommended 時附帶 producer-provided `rewrite_dispatch_request`。
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/tools/storyboard_gen.py:1001` 至 `:1014` 只在 `rewrite_until_quality_passed` 且 eval 建議 rewrite 時呼叫 pack-owned rewrite function；同檔 `:1085` 至 `:1088` 保存 `rewrite_result` 與 `original_storyboard`。
- `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/manifest.yaml` 宣告 `pd_storyboard_content_rewrite` playbook/tool；spec JSON 由 `jq empty` 驗證。

### local-core host boundary

- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/meeting_engine_runner.py:364` 的 `_producer_rewrite_dispatch_request()` 只讀 producer summary 內的 request，不在 host 端建立 pack-specific playbook code。
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/meeting_engine_runner.py:426` 的 `_producer_quality_gate_fallback()` 只依 generic review state 與 quality requirements 建立 quality gate/handoff。
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py:312` 至 `:358` 收集 generic `quality_requirements`；同檔 `:549` 至 `:582` 將其放入 AOL metadata、governance constraints 與 handoff metadata。
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/routes/core/capability_packs.py:832` 新增單一 installed capability metadata endpoint，避免 web-console 為一個 capability 拉完整清單。
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_output_artifact_creator.py:238` 至 `:245` 支援 `fan_out_source`；同檔 `:437` 至 `:448` 支援 artifact/action type from context；同檔 `:487` 至 `:488` 支援 `storage_ref` metadata。

## 邊界查驗

local-core service/model/route 範圍掃描沒有發現本次 Meeting/AOL host path 硬編碼 `pd_storyboard_content_rewrite`。唯一命中是既有 `core_llm.py` 註釋，與本次變更檔無關。

> **Evidence**:
> ```bash
> rg -n "performance_direction|pd_storyboard_content_rewrite|storyboard_content_rewrite" backend/app/services backend/app/models backend/app/routes -S
> ```
> ```
> backend/app/services/llm/core_llm.py:3:Capability packs such as `performance_direction` still call `core_llm_call()`
> ```

正式安裝紅線維持：cloud source repo 是 source of truth；local-core installed pack 只能由 `.mindpack` 經 install API 落地，不提交 raw installed pack source。

## 註釋與 UI 文案查驗

本次提交範圍的 local-core backend 與 AOL host shell 實作檔未發現中文 UI/emoji/中文註釋命中。AOL host shell error state 已改為英文文案與 `lucide-react` icon。

> **Evidence**:
> ```bash
> rg -n "[一-龥]|<emoji-token-pattern>" backend/app/routes/core/capability_packs.py backend/app/services/meeting_command_status_sync.py backend/app/services/meeting_execution_graph_commands.py backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py backend/app/services/orchestration/meeting/meeting_engine_runner.py backend/app/services/playbook_output_artifact_creator.py 'web-console/src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/page.tsx' web-console/src/lib/capability-ui-loader.ts
> ```
> ```
> <no output>
> ```

cloud `manifest.yaml` 內的 `display_name_zh` / `description_zh` 是正式 zh-TW metadata，不列為違規；英文 playbook file 仍以英文為基底。

## 自動化驗證

### cloud focused pytest

> **Evidence**:
> ```bash
> /Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest capabilities/performance_direction/tests/storyboard_content_rewrite_test.py capabilities/performance_direction/tests/storyboard_gen_market_fit_test.py capabilities/performance_direction/tests/pd_storyboard_content_rewrite_playbook_spec_test.py capabilities/performance_direction/tests/pd_storyboard_gen_playbook_spec_test.py
> ```
> ```
> 8 passed in 1.10s
> ```

### local-core focused pytest

> **Evidence**:
> ```bash
> ./.venv/bin/python -m pytest backend/tests/meeting_engine_runner_spec.py backend/tests/meeting_execution_graph_commands_spec.py backend/tests/meeting_command_status_sync_spec.py backend/tests/aol_meeting_orchestration_bridge_spec.py backend/tests/capability_packs_cache_spec.py backend/tests/services/test_playbook_output_artifact_creator.py
> ```
> ```
> 28 passed, 156 warnings in 2.42s
> ```

### front-end submitted scope

> **Evidence**:
> ```bash
> ./node_modules/.bin/vitest run 'src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/page.aol-host.spec.tsx' 'src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/page.render-proof.spec.tsx' --reporter=verbose
> ```
> ```
> Test Files  2 passed (2)
> Tests       2 passed (2)
> Duration    4.39s
> ```

### syntax and format checks

> **Evidence**:
> ```bash
> jq empty capabilities/performance_direction/playbooks/specs/pd_storyboard_content_rewrite.json capabilities/performance_direction/playbooks/specs/pd_storyboard_gen.json
> git diff --check
> python -m py_compile <submitted python files>
> ```
> ```
> all commands completed with no output and exit code 0
> ```

## 未納入提交的 WIP 證據

`PerformanceDirectionStoryboardEditorPage.test.tsx` 目前包含尚未閉環的大型 editor case；同跑提交範圍測試時有 29 tests / 10 failed。此檔不作為本次提交證據，也不納入本次 commit pathspec。

> **Evidence**:
> ```bash
> ./node_modules/.bin/vitest run 'src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/page.aol-host.spec.tsx' 'src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/page.render-proof.spec.tsx' 'src/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage.test.tsx'
> ```
> ```
> PerformanceDirectionStoryboardEditorPage.test.tsx (29 tests | 10 failed)
> Test Files  2 failed | 1 passed (3)
> Tests       11 failed | 20 passed (31)
> ```

## 安裝證據

cloud source 已提交為 `7722986`；local-core host/docs 已提交為 `5474897a`。正式 `.mindpack` 從已提交的 cloud `capabilities/performance_direction` scope 打包；打包前 `git status --short -- capabilities/performance_direction` 無輸出。

> **Evidence**:
> ```bash
> python3 scripts/package_capability.py performance_direction
> ```
> ```
> Packaging 216 files from /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction
> Created .mindpack file: /Users/shock/Projects_local/workspace/mindscape-ai-cloud/performance_direction.mindpack
> Package size: 385.19 KB
> Successfully created: /Users/shock/Projects_local/workspace/mindscape-ai-cloud/performance_direction.mindpack
> ```

> **Evidence**:
> ```bash
> tar tzf performance_direction.mindpack
> ```
> ```
> performance_direction/playbooks/specs/pd_storyboard_content_rewrite.json
> performance_direction/playbooks/zh-TW/pd_storyboard_content_rewrite.md
> performance_direction/playbooks/en/pd_storyboard_content_rewrite.md
> performance_direction/tools/storyboard_content_rewrite.py
> performance_direction/tests/storyboard_content_rewrite_test.py
> performance_direction/tests/pd_storyboard_content_rewrite_playbook_spec_test.py
> ```

> **Evidence**:
> ```bash
> curl -sS -X POST http://localhost:8220/api/v1/capability-packs/install-from-file -F file=@/Users/shock/Projects_local/workspace/mindscape-ai-cloud/performance_direction.mindpack
> ```
> ```
> {"success":true,"capability_id":"performance_direction","version":"0.1.0","restart_required":true,"restart_triggered":false}
> ```

Install API 回傳 `restart_required=true`，因此已執行本地 backend restart。

> **Evidence**:
> ```bash
> docker compose restart backend
> docker compose ps backend
> curl -sS -m 20 http://localhost:8220/health
> ```
> ```
> Container mindscape-ai-local-core-backend  Started
> mindscape-ai-local-core-backend   Up 2 minutes (healthy)
> {"status":"healthy","components":{"backend":"healthy","post_ready_playbook_registry":"completed","object_index_sync":"completed"},"issues":[]}
> ```

registry 查驗已確認 rewrite playbook/tool 可用，且 `pd_storyboard_gen` outputs 內含 `rewrite_result`。

> **Evidence**:
> ```bash
> curl -sS -m 20 http://localhost:8220/api/v1/playbooks/pd_storyboard_content_rewrite
> curl -sS -m 20 http://localhost:8220/api/v1/tools/performance_direction.pd_storyboard_content_rewrite
> curl -sS -m 20 http://localhost:8220/api/v1/playbooks/pd_storyboard_gen
> ```
> ```
> "playbook_code":"pd_storyboard_content_rewrite"
> "tool_slot":"performance_direction.pd_storyboard_content_rewrite"
> "tool_id":"performance_direction.pd_storyboard_content_rewrite"
> "rewrite_result":"rewrite_result"
> ```
