# IG Runtime 資源、進度與設定頁收尾實作細項

最後更新：2026-05-05

## 目的

本文件記錄本輪工作樹整理、驗證、提交與 deploy-pack 收尾範圍。範圍限定在 IG capability pack 的進度/佇列/參考目錄修復、local-core runner 資源等待語義、local-core settings shell 載入與設定 API 可用性修補，以及提交前註釋/語系/邊界檢查。

## 邊界

- cloud repo 的 IG 實作不得直接修改 local-core 架構、runner lock、capability registry 或已安裝 capability source。
- local-core 只允許處理 runtime primitive、settings shell、runner 資源等待語義與內部證據文檔。
- capability source 的正式啟用必須經由 `.mindpack` 與 install API。
- 本輪不以手動 DB mutation 修正 queue、frontier、progress 或 seed completion。

## 上游資料範圍

| 類別 | 來源 | 本輪用途 |
| --- | --- | --- |
| IG following progress artifact | `artifact_manager.upsert_progress` 寫入的 `progress` payload | 修正 scroll 階段 saved/targets/expected 的顯示資料底線 |
| published seed summary | Sources 列表 seed execution summary | 修正 pending queue compact 與避免 stale seed summary 讓進度倒退 |
| active execution API | `/api/v1/ig/workbench/active-executions` | 查驗 workbench card 是否能穩定載入與呈現進度 |
| reference catalog summary | IG reference facet summary rows | 避免 page load inline rebuild 卡住 backend/control |
| runner subprocess failure context | `task_executor._mark_task_failed` | 區分 browser resource wait 與真正 workflow retry |
| system settings store | `/api/v1/system-settings/*` | 修復 settings page model/profile 設定 API 500 |
| Next.js same-origin proxy | `web-console/next.config.js` rewrite | 修復 browser 端誤打 `backend:8200` 與 `/health` 404 |

## 下游資料範圍

| 類別 | 受影響行為 | 驗證方式 |
| --- | --- | --- |
| Workbench execution card | List Scroll 與 pending queue 顯示不倒退、不跳號 | IG UI hook tests 與 active executions API |
| Sources seed cards | pending queue position 連續壓縮 | `useSeedExecutions.test.ts` |
| Reference catalog page | facet API 不因 legacy summary inline rebuild 阻塞 | `test_reference_catalog_store.py` 與 facets API latency |
| Runner task retry | browser lease wait 不消耗 workflow retry，不觸發 deadletter/on_fail | `runner_resource_pressure_checks.py` |
| Settings page | `/settings` 可載入、icons 顯示、Models and Quota tabs 不溢出 | local `/settings` HTTP 與 targeted UI 檔案檢查 |
| Deploy-pack | IG pack source 以 package/install API 啟用 | `scripts/package_capability.py ig` 與 install API |

## Todos

- [x] 讀取 evidence-based-reporting 與 deploy-pack skill，確認證據與 package/install 流程。
- [x] 讀取 local-core developer guide，確認註釋、語系、邊界與 commit hygiene 規範。
- [x] 盤點 cloud/local-core dirty worktree，分離 source 變更與本機 scratch artifacts。
- [x] 將 cloud `.tmp/`、local-core `_backups/` 與 `web-console/.next.bak-*` 納入 ignore，不提交本機臨時證據或編譯備份。
- [x] 檢查所有目標程式碼新增行沒有中文註釋、emoji、實作步驟註釋或非功能性描述。
- [x] 執行 cloud IG Python/UI targeted tests。
- [x] 執行 local-core runner/settings targeted tests 與 HTTP smoke checks。
- [x] 依目的分批提交 cloud 與 local-core 工作樹。
- [x] 從 clean cloud repo 執行全量 deploy-pack，透過 install API 安裝並查驗 installed runtime source。
- [x] 依 evidence-based-reporting 規則產出本輪品質查驗報告。

## 收尾驗證摘要

- cloud repo 已分批提交：`e7865f9`、`91cc79f`、`948c6a1`。
- local-core repo 已分批提交：`630b9bc9`、`2f278b19`、`ba1acdc0`。
- `git diff --check` 在 cloud 與 local-core 皆通過。
- cloud IG Python targeted tests：`44 passed`。
- cloud IG UI targeted tests：`11 passed`。
- local-core runner targeted tests：`4 passed`。
- local-core settings targeted lint：`No ESLint warnings or errors`。
- local-core repo-wide `type-check` 仍存在既有跨 capability 型別錯誤，未作為本輪 targeted gate。
- deploy-pack 已建立 `ig.mindpack`，install log 顯示 IG capability v1.0.4 安裝完成並寫入 349 個 manifest files。
- post-install health：backend `200`、backend-control `200`、frontend `/health` `200`。
- installed runtime source 已確認含本輪 IG 修補點：reference catalog inline rebuild guard、progress sane merge、pending queue compact。

## 待查驗命令

```bash
git diff --check
rg -n --pcre2 "[\\x{1F300}-\\x{1FAFF}]" <changed-code-files>
rg -n "[一-龥]" <changed-code-files>
python -m pytest capabilities/ig/tests/test_reference_catalog_store.py capabilities/ig/tests/artifact_manager_progress_test.py capabilities/ig/tests/test_vision_schema_salvage_regression.py -q
web-console/node_modules/.bin/vitest run --config vitest.ig-ui.config.cjs capabilities/ig/ui/modules/accounts/hooks/useSeedExecutions.test.ts capabilities/ig/ui/workbench/components/WorkbenchExecutionPanel/hooks/useIGDebug.test.tsx
python -m pytest backend/tests/runner_resource_pressure_checks.py -q
curl -sS -m 20 -o /dev/null -w '%{http_code} %{time_total}\n' http://localhost:8300/settings
python3 scripts/package_capability.py ig
curl -sS -m 300 -X POST http://localhost:8220/api/v1/capability-packs/install-from-file -F file=@ig.mindpack
```
