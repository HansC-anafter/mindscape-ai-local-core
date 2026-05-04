---
title: PD Storyboard Rewrite Handoff Todos 與資料範圍
date: 2026-05-05
status: completed
owner: local-core / performance_direction
skill_alignment: evidence-based-planning
---

# PD Storyboard Rewrite Handoff Todos 與資料範圍

最後更新：2026-05-05。

## 目標

把 storyboard content-quality failure 從「只給人看」推進到「producer 可提出 bounded rewrite request，Meeting 可中性判斷，PD pack 可在明確要求下完成一次 rewrite pass」。

## 上游資料範圍

- AOL command metadata：`quality_requirements`、`content_quality_requirements`、`producer_quality_requirements`。
- AOL selected objects：`selected_object_refs`、IG reference refs、card metadata、context attachments。
- PD generation input：`human_instructions`、`addressable_object_layer`、resolved `reference_cue_map`、`quality_requirements.rewrite_until_quality_passed`。
- Producer evaluation：`content_quality_eval`、`producer_eval_summary`、`rewrite_dispatch_request`。

## 本階段處理範圍

- cloud `performance_direction`：
  - `storyboard_content_rewrite.py`
  - `pd_storyboard_content_rewrite.json`
  - `pd_storyboard_content_rewrite.md` English / zh-TW
  - `pd_storyboard_gen` optional rewrite loop
  - `manifest.yaml` playbook/tool registration
- local-core generic host：
  - AOL Meeting bridge quality requirement transport
  - Meeting producer quality gate
  - late result status sync
  - execution graph command metadata projection
  - playbook output artifact fan-out and dynamic artifact typing
  - installed capability metadata endpoint
  - AOL host shell capability metadata lookup and loader metadata priming

## 下游資料範圍

- Stored storyboard artifact payload：
  - `storyboard`
  - `original_storyboard`
  - `content_quality_eval`
  - `producer_eval_summary`
  - `rewrite_result`
- Playbook materialized artifacts：
  - storyboard manifest
  - reference cue map
  - content quality eval JSON
  - content rewrite JSON
- Meeting command metadata：
  - `producer_eval_summaries`
  - `review_state`
  - `review_reason`
  - `recommended_actions`
  - `producer_quality_gate`
  - `producer_quality_gate.rewrite_handoff.dispatch_request`
- UI consumer：
  - installed capability metadata endpoint
  - UI component list endpoint
  - AOL host shell object selection / meeting attach flow

## Todo 狀態

| 項目 | 狀態 | 證據 |
|---|---|---|
| 新增 PD rewrite tool | done | `storyboard_content_rewrite.py:140` |
| 新增 PD rewrite playbook/spec/manifest | done | `manifest.yaml`、`pd_storyboard_content_rewrite.json`、English / zh-TW playbook |
| `pd_storyboard_gen` 接上明確 opt-in rewrite loop | done | `storyboard_gen.py:1001`、`:1085` |
| producer summary 自帶 rewrite request | done | `storyboard_content_quality.py:226` |
| local-core Meeting 保持 generic，不硬編碼 PD rewrite playbook | done | `meeting_engine_runner.py:364` 與 boundary `rg` |
| AOL handoff 攜帶 generic quality requirements | done | `aol_meeting_orchestration_bridge.py:312`、`:549` |
| playbook artifact creator 支援 rewrite artifact materialization | done | `playbook_output_artifact_creator.py:238`、`:437`、`:487` |
| capability metadata endpoint 支援單一 installed capability lookup | done | `capability_packs.py:832` |
| AOL host shell 改用單一 metadata endpoint 並 prime loader metadata | done | `page.tsx:138`、`capability-ui-loader.ts:62` |
| 提交前測試 | done | cloud 8 passed；local-core 28 passed；AOL host vitest 2 passed |
| 正式 commit | done | cloud `7722986`；local-core `5474897a` |
| 提交後 `.mindpack` 正式安裝 | done | install API 回傳 `success=true`、`restart_required=true` |
| 安裝後 registry/API 查驗 | done | health healthy；rewrite playbook/tool endpoint 可查；`pd_storyboard_gen` output 含 `rewrite_result` |

## 不納入本次閉環

- cloud `capabilities/ig/**` 與 `.tmp/**` dirty files。
- local-core settings UI dirty files。
- local-core runner resource pressure dirty files。
- `PerformanceDirectionStoryboardEditorPage.test.tsx` 目前含未閉環大型 editor case；本次不提交此 WIP test file。
