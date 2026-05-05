# IG Runtime 資源、進度與設定頁工作樹品質查驗報告

最後更新：2026-05-05

## 結論

本輪工作樹已依 repo 邊界分批提交，cloud repo 保持 IG capability source 修復，local-core repo 僅處理 runtime primitive、settings shell、proxy 與內部文件。全量 `deploy-pack` 已從 clean cloud repo 建包並經 install API 安裝；install log 顯示 IG capability v1.0.4 完成安裝，post-install backend、backend-control、frontend health 皆為 200。

目前仍需記錄的殘留風險是 local-core repo-wide `type-check` 有既有跨 capability 型別錯誤；本輪 targeted lint/tests 通過，未把該既有全域型別債務擴入本輪修復。

## 邊界查驗

| 項目 | 結果 | 證據 |
| --- | --- | --- |
| cloud 實作未改 local-core 架構 | 通過 | cloud commits 只在 `capabilities/ig` 與 cloud `.gitignore`；local-core commits 不包含 installed IG source |
| installed capability source 不直接提交到 local-core | 通過 | local-core commit `630b9bc9` 將 tracked installed capability test 從 index 移除，保留 hard barrier |
| 不以 DB mutation 修正狀態 | 通過 | 本輪提交無 SQL/manual DB correction |
| 內部文件使用繁體中文 | 通過 | 本文件與 todos 文檔位於 `docs-internal/implementation/runtime/` |
| 程式碼註釋語系與 emoji 規則 | 通過 | 新增行 CJK/emoji scan 通過；cloud `formatters.ts` 已移除 emoji heading |

## 已提交變更

### cloud repo

| Commit | 範圍 | 說明 |
| --- | --- | --- |
| `e7865f9` | repo hygiene | ignore `.tmp/` local scratch artifacts |
| `91cc79f` | IG vision/reference salvage | 統一 schema 2.1 fallback、修正 prose salvage 與 material confidence preserving |
| `948c6a1` | IG following progress/queue/catalog | 穩定 List Scroll、pending queue compact、reference catalog 缺 summary 時跳過 inline rebuild |

### local-core repo

| Commit | 範圍 | 說明 |
| --- | --- | --- |
| `630b9bc9` | repo hygiene/boundary | ignore generated artifacts，移除 tracked installed capability source |
| `2f278b19` | runner runtime primitive | browser resource lease wait 改為 requeue，不消耗 workflow retry、不 deadletter |
| `ba1acdc0` | settings shell/proxy | 修正 settings store 500、same-origin proxy、settings shell lazy loading 與 icon/tab UI |

## 測試與查驗證據

| 類別 | 命令 | 結果 |
| --- | --- | --- |
| diff hygiene | `git diff --check` | cloud/local-core 皆通過 |
| 註釋與字元規則 | added-line CJK/emoji scan | 目標程式碼新增行通過 |
| cloud Python targeted tests | `python -m pytest capabilities/ig/tests/test_reference_catalog_store.py capabilities/ig/tests/artifact_manager_progress_test.py capabilities/ig/tests/test_vision_schema_salvage_regression.py -q` | `44 passed` |
| cloud IG UI tests | `vitest run ...useSeedExecutions.test.ts ...useIGDebug.test.tsx` | `11 passed`，僅 React act warning |
| local runner tests | `python -m pytest backend/tests/runner_resource_pressure_checks.py -q` | `4 passed` |
| local settings lint | `npm --prefix web-console run lint -- --file ...` | `No ESLint warnings or errors` |
| local type-check | `npm --prefix web-console run type-check` | 失敗，範圍為既有跨 capability 型別錯誤 |
| backend health | `curl http://localhost:8200/health` | `200` |
| backend-control health | `curl http://localhost:8220/health` | `200` |
| frontend health | `curl http://localhost:8300/health` | `200` |
| settings route | `curl http://localhost:8300/settings` | `200`，本機 dev server 仍可能因 cold compile 有 10 秒以上延遲 |
| capability packs list | `curl http://localhost:8220/api/v1/capability-packs/` | `200` |

## Deploy-Pack 查驗

建包命令：

```bash
python3 scripts/package_capability.py ig
```

結果摘要：

- `Packaging 615 files`
- `Created .mindpack file: /Users/shock/Projects_local/workspace/mindscape-ai-cloud/ig.mindpack`
- `Package size: 1151.25 KB`

安裝命令：

```bash
curl -sS -m 300 -X POST http://localhost:8220/api/v1/capability-packs/install-from-file -F file=@ig.mindpack
```

curl 端在 300 秒 timeout，但 backend-control log 顯示 install 已完成並回 200：

- `Extracted capability: ig`
- `Registered 19 capability migration files for ig`
- `Saved install manifest for v1.0.4 (349 files)`
- `POST /api/v1/capability-packs/install-from-file HTTP/1.1" 200 OK`

post-install runtime source 查驗：

| 修補點 | 容器內查驗 |
| --- | --- |
| reference catalog 避免缺 summary 時 inline rebuild | `/app/backend/app/capabilities/ig/services/reference_catalog_write.py` 含 `skipping inline rebuild` |
| progress sane merge | frontend installed `useIGDebug.ts` 含 `maxNumberOrNull` 與 published summary merge |
| pending queue compact | frontend installed `useSeedExecutions.ts` 含 `queuePosition: projectedStatus === 'paused' ? undefined : ...` |

## 實作目標對齊

| 目標 | 查驗結果 |
| --- | --- |
| List Scroll 不因 stale summary 倒退或跳動 | 以 progress artifact/current payload/published summary 做 sane merge，不降低 saved/visited；UI hook tests 覆蓋 |
| pending queued 排序連續 | pending projection 不再被提前 `continue` 跳過；UI hook tests 覆蓋 |
| reference catalog page 不因 legacy summary 重建拖垮 API | 缺 baseline count summary 時跳過 inline rebuild；Python tests 覆蓋 |
| browser resource pressure 不打死任務鏈 | lease wait 使用 resource wait requeue，不走 workflow retry/deadletter/on_fail；runner tests 覆蓋 |
| settings page console 404/500 類問題 | `/health` same-origin rewrite、browser backend URL normalization、settings store staticmethod 修復；health/API smoke 通過 |
| UI 調整不破壞 i18n 基底 | UI 正式文字仍走既有 locale/messages；程式碼新增行未引入中文註釋 |

## 殘留風險與後續觀測

- local-core repo-wide `type-check` 仍有既有跨 capability 型別錯誤，需另立全域型別債務處理，不建議混入本輪 IG runtime 收尾。
- `/settings` 在本機 Next dev server cold compile 期間仍可能出現十秒級延遲；hot health 與 API smokes 已恢復正常。
- `runner-browser` 在有 IG 任務執行時仍可達 4 GiB 以上記憶體；本輪修復的是 resource lease wait 不錯誤消耗 task retry，是否進一步降低單任務瀏覽器記憶體需另開 browser lifecycle/profile cache 專案。
