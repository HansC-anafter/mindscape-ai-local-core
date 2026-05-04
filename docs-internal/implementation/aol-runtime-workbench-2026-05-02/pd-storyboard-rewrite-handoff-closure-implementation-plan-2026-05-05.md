---
title: PD Storyboard Rewrite Handoff 閉環實作計劃
date: 2026-05-05
status: active
owner: local-core / performance_direction
skill_alignment: evidence-based-planning
---

# PD Storyboard Rewrite Handoff 閉環實作計劃

## 問題清單

1. **重寫能力已被規劃但尚未落地**：grounded content-quality 計劃已列出 `storyboard_content_rewrite.py` 與 `pd_storyboard_content_rewrite.json`，但實作前 cloud pack 與 local-core installed pack 都沒有這兩個檔案。Evidence: E1, E2。
2. **內容品質失敗會產生 Meeting handoff，但尚不是可執行 rewrite request**：`MeetingEngineRunner` 會產出 `producer_quality_gate.rewrite_handoff`，但實作前 handoff 只含 producer summaries 與 review instructions，沒有由 producer 提供的 rewrite playbook request。Evidence: E3。
3. **`pd_storyboard_gen` 會評估品質，但尚未關閉可選 rewrite loop**：storyboard generation 已建立 `reference_cue_map`、`content_quality_eval`、`producer_eval_summary`，但實作前會直接保存原始 storyboard payload；當 `rewrite_until_quality_passed` 被要求時沒有 rewritten candidate。Evidence: E4, E5。

優先級：

| Problem | Severity | Detection | Priority |
|---|---:|---:|---:|
| 1 | 5 | 4 | 20 |
| 2 | 4 | 4 | 16 |
| 3 | 5 | 3 | 15 |

## 證據

- E1: 既有計劃在 `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/aol-runtime-workbench-2026-05-02/pd-storyboard-grounded-content-quality-implementation-plan-2026-05-04.md` 的 Change 3 列出 rewrite pass 候選檔案。
- E2: 實作前以 `rg -n "storyboard_content_rewrite|pd_storyboard_content_rewrite"` 搜尋 `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction` 與 `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/capabilities/performance_direction`，沒有找到 rewrite tool/spec 實作檔。
- E3: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/meeting_engine_runner.py` 產生 `producer_quality_gate` 與 `rewrite_handoff`，但實作前沒有泛型 producer-provided `rewrite_dispatch_request`。
- E4: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/tools/storyboard_gen.py` 已在 reels path 建立 `script_market_fit`、`reference_cue_map`、`content_quality_eval` 與 `producer_eval_summary`。
- E5: 同一檔案在保存 storyboard payload 時，實作前未附加 `rewrite_result` 或 `original_storyboard`。
- E6: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/services/storyboard_content_quality.py` 已回傳 generic producer actions，例如 `rewrite_storyboard_script_with_reference_cues`。
- E7: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/playbooks/specs/pd_storyboard_gen.json` 已接受 generic `quality_requirements`，因此 `rewrite_until_quality_passed` 可維持 neutral input，不需在 Meeting 端硬編碼。

## 擬定變更

### Change 1: 新增 pack-owned deterministic rewrite service

解決 Problems 1 與 3。

- 新增 `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/tools/storyboard_content_rewrite.py`。
- 輸入：`storyboard`、`reference_cue_map`、`content_quality_eval`、`quality_requirements`、optional `rewrite_handoff`、optional `review_notes`。
- 若 `reference_cue_map.grounding_status == "needs_reference_analysis"` 或 eval 表示 `needs_reference_analysis`，回傳 `status="needs_reference_analysis"`，不得憑空補 reference details。
- 否則以 reference cues 重寫 blocking vague script fields，並保留 scene count、scene ids、reference ids、source cue ids。
- 對 rewritten candidate 再跑 `build_storyboard_content_quality_eval()`，輸出 `rewritten_storyboard`、`content_quality_eval`、`producer_eval_summary`、`rewrite_report`。

### Change 2: 新增 rewrite playbook spec 與 manifest 宣告

解決 Problem 1。

- 新增 `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/playbooks/specs/pd_storyboard_content_rewrite.json`。
- 更新 `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/manifest.yaml`，讓 tool 與 playbook 可被正式安裝。
- Playbook 需 materialize rewritten storyboard JSON、rewrite report JSON、revised content-quality eval JSON。

### Change 3: 在 `pd_storyboard_gen` 關閉明確要求的 auto-rewrite loop

解決 Problem 3。

- 在 first `content_quality_eval` 後，若 `quality_requirements.rewrite_until_quality_passed == true` 且 eval 建議 rewrite，呼叫 pack-owned rewrite function 一次。
- 回傳與保存 payload 需包含 `rewrite_result`。
- 若 rewrite eval passed，stored canonical storyboard 改為 rewritten candidate，並以 `original_storyboard` 保留原候選。
- 若 rewrite 後仍未通過，保留原候選與 rewritten candidate，並維持 final `producer_eval_summary` 狀態。

### Change 4: 讓 Meeting handoff 可執行但保持中性

解決 Problem 2。

- PD producer summary 自帶 `rewrite_dispatch_request`，內容含 pack-owned playbook code 與 required inputs。
- `MeetingEngineRunner` 只讀取 producer-provided request，不在 local-core 硬編碼 `performance_direction` 或 `pd_storyboard_content_rewrite`。
- Meeting 端只依 generic `quality_requirements.rewrite_until_quality_passed` 決定 `dispatch_mode`：
  - true: `auto_launch_allowed`
  - false/missing: `explicit_quality_requirement_required`

## 驗證 SOP

1. Cloud unit tests:

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-cloud
/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest \
  capabilities/performance_direction/tests/storyboard_content_rewrite_test.py \
  capabilities/performance_direction/tests/storyboard_gen_market_fit_test.py \
  capabilities/performance_direction/tests/pd_storyboard_content_rewrite_playbook_spec_test.py \
  capabilities/performance_direction/tests/pd_storyboard_gen_playbook_spec_test.py
```

預期：rewrite 保留 scene count、拒絕缺 reference analysis 時硬寫內容，且 `rewrite_until_quality_passed=true` 時能保存 revised candidate。

2. local-core focused tests:

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core
./.venv/bin/python -m pytest \
  backend/tests/meeting_engine_runner_spec.py \
  backend/tests/meeting_execution_graph_commands_spec.py \
  backend/tests/meeting_command_status_sync_spec.py \
  backend/tests/services/test_playbook_output_artifact_creator.py
```

預期：未明確要求 rewrite 時 producer gate 仍標示 needs-revision；若 producer summary 自帶 rewrite request，handoff 會包含 bounded dispatch request。

3. Release install:

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-cloud
python3 scripts/package_capability.py performance_direction
tar tzf performance_direction.mindpack | head -20
curl -sS -X POST http://localhost:8220/api/v1/capability-packs/install-from-file \
  -F "file=@/Users/shock/Projects_local/workspace/mindscape-ai-cloud/performance_direction.mindpack"
```

預期：install 回傳 success；backend reload 或 restart 後 `/api/v1/playbooks/pd_storyboard_content_rewrite` 與 `/api/v1/tools/performance_direction.pd_storyboard_content_rewrite` 都可查到。

## 自動化測試計劃

- 新增 `capabilities/performance_direction/tests/storyboard_content_rewrite_test.py`：
  - 使用 cue evidence 重寫 vague script fields。
  - 保留 scene count 與 scene ids。
  - cue map 缺 evidence 時回傳 `needs_reference_analysis`，不產生 rewritten storyboard。
- 新增 `capabilities/performance_direction/tests/pd_storyboard_content_rewrite_playbook_spec_test.py`：
  - 檢查 spec 宣告 required inputs、step outputs、materialized artifacts。
- 擴充 `capabilities/performance_direction/tests/storyboard_gen_market_fit_test.py`：
  - `quality_requirements.rewrite_until_quality_passed=true` 時，輸出 `rewrite_result`、final `content_quality_eval.passed=true`，並保留 `original_storyboard`。
- 擴充 `backend/tests/meeting_engine_runner_spec.py`：
  - producer-provided rewrite request 會被 Meeting handoff 搬運。
  - dispatch mode 只由 generic quality requirement 控制。

## 風險與開放問題

- deterministic rewrite 能關閉目前 placeholder / workflow copy failure，但不是完整 creative LLM rewrite。後續可在同一 schema 下替換內部 rewrite provider。
- Meeting 自動 launch 必須維持 opt-in，避免 local-core runtime 變成 pack-specific orchestration。
- 正式安裝必須從 cloud source commit 後打包，並透過 local-core install API 安裝；不得直接修改 installed pack 檔案。
