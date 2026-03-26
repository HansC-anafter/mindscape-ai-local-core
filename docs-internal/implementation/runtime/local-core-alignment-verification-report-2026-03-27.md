# Local-Core 實作對齊與查驗報告（2026-03-27）

## Findings
1. **`auto-contact-zone rerender` 在 local-core 已達收口條件**：實作計劃已明確記錄主線已通、`manual_required / escalate_local_scene` hard gate 已落地、API smoke 與 opt-in host-runtime smoke 已補齊，下一個推薦切片已轉為 visual acceptance，而不是繼續擴 runtime smoke。 (E1)
2. **`visual-acceptance / artifact-review` 在 local-core 已完成到 generic handoff 邊界**：目前 local-core 端已具備 review bundle、follow-up durability、`rerender / laf_patch / local_scene_review` consumer；`publish_candidate` 只保留 generic `consumer_handoff`，accepted-review evidence 與 promotion rule 已回 pack 擁有。 (E2, E3, E4, E5)
3. **目前程式碼面沒有殘留 pack-owning publish/gate/tool dispatch 實作**：在 `backend/app`、`web-console`、`scripts` 內搜尋 `character_package_publish`、`character_package_promotion_gate`、`review_evidence_resolver`、`character_package_capability_request`、`visual_acceptance_publish_gate`，沒有命中；`publish_candidate` 對應實作僅回傳 `consumer_handoff` dispatch result。 (E5, E6)
4. **本次提交候選檔案已符合語言與註釋規則**：`ArtifactReviewPane`、checklist 文案、測試 fixture 已收回英文基底；針對候選檔案的 CJK / emoji / `zh-TW` 掃描無命中，`git diff --check` 也無 whitespace 或 patch 格式問題。 (E7, E8, E9)
5. **針對 visual-acceptance 主線的後端回歸目前通過**：targeted backend suite `16 passed`；前端型別檢查雖未作為全專案綠燈門檻，但目前過濾 `ExecutionInspector.tsx`、`ArtifactReviewPane.tsx`、`StepDetailPanel.tsx`、`types/execution.ts`、`artifact-review.ts` 未出現命中。 (E10, E11)
6. **目前工作樹仍有大量與本次主題無關的變更，提交必須使用明確檔案清單**：`git status --short` 顯示 repo 尚有多條 governance、settings、memory-impact-graph 等不屬於本次實作的改動；目前 staged 內容也只覆蓋 visual-acceptance 的一部分，因此正式提交前必須用顯式 `git add <files...>` 收斂提交範圍。 (E12, E13, E14)

## Evidence Register
| ID | Type | Source | Finding |
|---|---|---|---|
| E1 | Code/Doc | `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/runtime/auto-contact-zone-rerender-v1-implementation-plan-2026-03-26.md:18-40` | `auto-contact-zone` 主線已通，hard gate、API smoke、mixed smoke、opt-in host-runtime smoke 已落地，下一步轉向 visual acceptance。 |
| E2 | Code/Doc | `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/runtime/visual-acceptance-artifact-review-implementation-plan-2026-03-26.md:50-81` | `visual-acceptance` 的 local-core 範圍、boundary correction、已完成切片與剩餘 pack-owned gap。 |
| E3 | Code/Doc | `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/runtime/character-training-pack-implementation-plan-2026-03-26.md:665-761` | `publish_candidate` 在 local-core 只能形成 generic `consumer_handoff`，不得擁有 pack-specific request/gate/publish contract。 |
| E4 | Code | `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/artifact_review_decision.py:25-79` | follow-up action 只保留 `pack_consumer_handoff` lane 與 alias 正規化，未定義 pack tool dispatch。 |
| E5 | Code | `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/visual_acceptance_followup_requests.py:443-460` | `publish_candidate` 對應的 dispatch result 只回傳 `consumer_handoff` metadata。 |
| E6 | Code | `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/visual_acceptance_followup_requests.py:1409-1435` | pack lane dispatch 只建立 `consumer_handoff` artifact 與 execution ref，未直跑 pack consumer。 |
| E7 | Code | `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/execution-inspector/ArtifactReviewPane.tsx:79-141` | review pane 的時間格式、狀態標籤、score label 已改成英文基底。 |
| E8 | Search | searched candidate files for CJK / emoji / `zh-TW`, 0 matches found | 候選提交檔案未殘留中文、emoji、或 `zh-TW` 硬編碼。 |
| E9 | Diff | `git diff --check -- <candidate files>` returned 0 findings | 候選提交檔案沒有 whitespace error 或 patch 格式問題。 |
| E10 | Test | `pytest -q backend/tests/services/test_visual_acceptance_followup_requests.py backend/tests/services/test_visual_acceptance_bundle_service.py backend/tests/routes/core/test_artifact_review_routes.py backend/tests/services/test_workbench_summary_followup_actions.py` | `16 passed, 152 warnings in 2.28s`。 |
| E11 | Type-check | `npm run type-check -- --pretty false 2>&1 | rg "ExecutionInspector\\.tsx|ArtifactReviewPane\\.tsx|StepDetailPanel\\.tsx|types/execution\\.ts|artifact-review\\.ts"` returned no matches | 目前型別錯誤輸出未命中本批前端檔案。 |
| E12 | Git | `git status --short` | 工作樹存在大量與本次主題無關的修改與新增檔案。 |
| E13 | Git | `git diff --cached --name-only -- <candidate files>` | 目前 staged 檔案僅覆蓋 visual-acceptance 子集，還未包含所有本次提交候選檔案。 |
| E14 | Diff | `git diff --stat -- <candidate files>` | 目前候選變更集中在 16 個 tracked files，主體為 visual-acceptance UI/route/service 與 auto-contact-zone runtime seams。 |

## Verification Notes
- 查驗流程先重讀 `evidence-based-reporting` 與 `mindscape-dev-guide` 規範，再回頭掃描候選檔案的中文、emoji、註釋與 locale 使用，避免先寫結論再補證據。
- `ArtifactReviewPane.tsx` 是本輪唯一仍殘留大量中文 UI 字串與 `zh-TW` locale 的檔案；這一輪已改為英文基底，並同步修正 `test_artifact_review_routes.py` 中的 checklist fixture label。
- 對於「沒有殘留 pack-owning 實作」這類否定命題，查驗方式採用限定範圍搜尋：只搜尋 `backend/app`、`web-console`、`scripts`，不把 `docs-internal/` 的設計描述算成程式碼命中。
- 全量前端型別狀態這一輪沒有重建完整基線；目前只確認既有 type-check 錯誤輸出不包含本批前端檔案。

## Open Questions
- 本次本地提交是否要把 `auto-contact-zone` 的未 staged runtime 檔案與 `visual-acceptance` 一併收口進同一個 commit，仍需依最終 curated file list 決定；但無論如何都不應帶入 repo 內其他 memory/governance/settings 改動。
- 若要把 `publish_candidate` 的命名也完全 generic 化，這應視為後續整理工作，而不是這次對齊查驗的阻塞項。

## Next Actions
1. 以顯式檔案清單 staged 本次候選檔案，加上本報告檔案，避免混入 repo 內其他 dirty changes。
2. 重新確認 staged diff 僅包含 `auto-contact-zone` 與 `visual-acceptance` 相關檔案後，建立單一本地 commit。
3. 不推送；後續若要補 `pack` 端 accepted-review evidence resolver、promotion gate、publish smoke，應改在 pack-owning session 進行。

## Fix Verification
1. 已完成候選檔案的 CJK / emoji / `zh-TW` 掃描，結果 0 命中。 (E8)
2. 已完成候選檔案的 `git diff --check`，結果 0 finding。 (E9)
3. 已執行 visual-acceptance 主線的 targeted backend suite，結果 `16 passed`。 (E10)
4. 已檢查目前 type-check 錯誤輸出中不含本批前端檔案名稱。 (E11)
