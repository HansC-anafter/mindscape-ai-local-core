# AOL Runtime Workbench 邊界修正報告與待辦

日期：2026-05-03

## 結論

`COMMAND_SUBMIT_IG_REFS_TO_PD_STORYBOARD` 與 `COMMAND_SUBMIT_PD_SCENE_DISCUSSION` 不應成為 local-core canonical action id。這是把 installed-pack 驗收情境提升成 local-core action enum 的文檔層邊界錯誤。已修正為 generic action id：

- `COMMAND_SUBMIT_CROSS_PACK_OBJECT_WORKFLOW`
- `COMMAND_SUBMIT_PACK_OBJECT_GUIDANCE_DISCUSSION`
- `PACK_OBJECT_*`

IG refs 與 PD scene 只能作為 installed-pack 驗收樣本，不是 local-core runtime route、UI enum、action id、contract field 或 hard-coded branch。

## 紅線對照

| 紅線 | 判定 | 證據與處置 |
|---|---:|---|
| 1. 絕不允許繞過 git 直接碰 vm | 未違反 | 本次只修改 git worktree 內文檔；未操作 VM、未改 installed runtime payload。 |
| 2. 實作品質需依計劃做對齊查驗與報告 | 已違反，已補救 | 先前補 action catalog 時未先產出對齊報告；本文件補齊查驗與待辦。 |
| 3. 嚴禁 cloud 實作變更 local-core 架構與邊界規範 | 已違反，文檔層 | 把 IG/PD 情境寫成 canonical action id 會誤導 local-core 實作 hard-code pack branches。已改成 generic action id 與 installed-pack fixture note。 |
| 4. 查驗注釋規則後才能提交 | 未觸發 | 本次未改程式碼註釋，未提交。 |
| 5. 詳讀開發者文檔與註釋規則 | 已違反，流程層 | 最初補 action id 前未先重讀紅線文檔；本次已重讀並依邊界修正。 |
| 6. 內部工作文檔一律繁體中文 | 部分違反 | 既有內部計劃文件本身含英文；本次新增報告與後續 TODO 固定用繁體中文。後續需另列文檔語言清理，不混入 P0 runtime 修補。 |
| 7. UI 正式實作以 i18n 英文為基底，中文為延伸；程式碼禁中文註釋 | 未觸發 | 本次未改 UI code、i18n key、程式碼註釋。 |
| 8. 以當下日期新增任務 todos，包含上下游資料範圍 | 已違反，已補救 | 本文件新增 2026-05-03 TODO，列出本次修正涉及的上下游資料範圍與驗收。 |

## 證據

E1. local-core 不得實作 cloud/platform-specific 業務邏輯。Source: `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md:L11-L28`, `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md:L30-L39`。

E2. local-core 不得直接讀 cloud source，capability source 必須走 package/install 邊界。Source: `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md:L54-L166`。

E3. capability install 邊界要求 local-core runtime 只讀已安裝 pack 與 installer alias，不把 source workspace 當 runtime。Source: `docs-internal/CAPABILITY_INSTALLATION_GUIDE.md:L33-L39`, `docs-internal/CAPABILITY_INSTALLATION_GUIDE.md:L149-L165`。

E4. action catalog 已改成 generic pack object action。Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-ux-action-sequence-catalog-2026-05-02.md:L170-L201`。

E5. P0 checklist 已改成 generic cross-pack object refs 與 pack-owned object discussion，IG/PD 只列為 installed-pack 驗收樣本。Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-to-meeting-engine-orchestration-bridge-implementation-plan-2026-05-03.md:L16-L17`。

E6. 舊 pack-specific action id 已不存在於本次三份計劃文檔。Verification command:

```bash
rg -n "COMMAND_SUBMIT_IG_REFS_TO_PD_STORYBOARD|COMMAND_SUBMIT_PD_SCENE_DISCUSSION|IG_REFERENCE_CARD_SELECT|IG_REFERENCE_OPEN_AOL_ACTIONS|IG_REFERENCE_INSERT_MENTION|IG_REFERENCE_ATTACH_SOURCE" docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-ux-action-sequence-catalog-2026-05-02.md docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-to-meeting-engine-orchestration-bridge-implementation-plan-2026-05-03.md
```

Output: no matches.

## 上下游資料範圍

| 範圍 | 本次允許 | 本次禁止 |
|---|---|---|
| local-core UX action catalog | 定義 generic `PACK_OBJECT_*`、`COMMAND_SUBMIT_*` action id | 定義 `IG_*`、`PD_*` local-core enum |
| local-core P0 bridge | 接受 generic `ObjectRef`、roles、guidance hints、playbook candidates、artifact/proposal ids | hard-code `ig`、`performance_direction`、storyboard scene routing |
| installed pack fixture | 用已安裝 IG/PD pack 驗證 generic route | 讓 fixture 名稱回流成 local-core contract |
| cloud capability source | pack-owned guidance、templates、materializers | 由 local-core 改寫 pack business semantics |
| artifact landing | 用 `artifacts?thread_id={meeting_id}` 驗證 DB/file proof | 用前端 fixture card 假裝 asset landed |

## 任務內 TODO

| TODO | 狀態 | 唯一路徑 | 驗收 |
|---|---:|---|---|
| 移除 pack-specific canonical action id | done | `aol-runtime-workbench-ux-action-sequence-catalog-2026-05-02.md` | `rg` 舊 action id 無結果 |
| 將 cross-pack E2E 改成 generic object workflow gate | done | `aol-to-meeting-engine-orchestration-bridge-implementation-plan-2026-05-03.md` | checklist 使用 `@owner.kind:*`，IG/PD 只作 fixture note |
| 將 layout 驗收改成 generic installed-pack object fixture | done | `aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md` | 驗收文字不要求 IG/PD-specific UI branch |
| P0 實作前檢查 local-core source 無 pack hard-code | pending | `rg -n "performance_direction|capabilities/ig|capabilities/performance_direction|MINDSCAPE_REMOTE_CAPABILITIES_DIR" backend/app/services/object_runtime/aol_meeting_orchestration_bridge.py backend/app/services/meeting_command_dispatch.py backend/app/routes/core/workspace/meeting_commands.py backend/app/services/orchestration/meeting/meeting_engine_runner.py` | 只允許測試 fixture 或明確拒絕邏輯；不允許 product path hard-code |
| 文檔語言清理 | pending | 本目錄內部計劃文件 | 新增或修訂段落使用繁體中文；既有英文大段另開清理，不混入 P0 runtime 修補 |

## 下一步約束

1. local-core canonical action id 只能是 generic AOL / meeting / object / command / runtime / artifact / review 語義。
2. pack-specific IG/PD wording只能出現在驗收 fixture、使用者原始需求引用、evidence citation 或 pack-origin examples，且必須標註不是 local-core contract。
3. P0 runtime code 實作時，任何 `ig`、`performance_direction`、`storyboard` 直接出現在 generic host path 都視為 blocker，除非位於測試 fixture 或負向邊界檢查。
