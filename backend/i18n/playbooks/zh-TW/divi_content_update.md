---
playbook_code: divi_content_update
version: 1.0.0
capability_code: web_generation
name: Divi 內容更新
description: |
  使用 Divi Safeguard 機制安全地更新 WordPress Divi 網站內容。
  包含 7 個執行步驟：Pre-Flight 驗證、健康檢查、映射驗證、Patch Plan 驗證（需 Gate）、
  套用前驗證（需 Gate）、套用 Patch、驗證結果。
  所有步驟都會生成 RunStep，Gate 步驟會生成 GateInfo 供 Thread View 顯示。
tags:
  - web
  - divi
  - wordpress
  - content-update
  - safeguard
  - gated-workflow

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
  - gated
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - web_generation.divi_preflight_validation
  - web_generation.divi_health_check
  - web_generation.divi_mapping_validation
  - web_generation.divi_patch_plan_validation
  - web_generation.divi_apply_gate_validation
  - web_generation.divi_apply_patch
  - web_generation.divi_verify_update

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 🛡️
---

# Divi 內容更新 - SOP

## 目標

使用 Divi Safeguard 機制安全地更新 WordPress Divi 網站內容，確保：

1. **安全驗證**：Pre-Flight 檢查確保環境和配置正確
2. **健康檢查**：驗證 WordPress 站點可訪問性
3. **映射驗證**：確保頁面和模板映射正確
4. **Patch Plan 驗證**：驗證更新計劃符合規格（需 Gate 批准）
5. **套用前驗證**：最終檢查並創建 checkpoint（需 Gate 批准）
6. **安全套用**：執行更新並記錄 revision
7. **結果驗證**：驗證更新是否成功

**核心價值**：
- 多層 Gate 防呆機制，確保更新安全
- 完整的執行鏈追蹤（RunStep）
- Gate 批准流程集成 Thread View
- 自動回滾支持

## 執行步驟

### Phase 0: Pre-Flight 驗證 (Gate 0)

**執行順序**：
1. 步驟 0.0: Pre-Flight 驗證

#### 步驟 0.0: Pre-Flight 驗證

**工具**：`web_generation.divi_preflight_validation`

**輸入**：
- `workspace_id`: 從 context 獲取
- `site_id`: 從 input 獲取
- `page_ids`: 從 input 獲取
- `content_source`: 從 input 獲取（可選）

**驗證項目**：
- site_id 格式和 DB 一致性
- API Key 可用性（優先 DB，環境變數備用）
- 目標頁面在 registry 中
- 頁面有 slot_schema
- API Key 硬編碼檢查（可選）
- post_content 直接修改檢查（可選）
- 幣別符號檢查（可選）

**輸出**：
- `preflight_result`: 驗證結果（包含 passed, checks, blocking_failures）
- `runstep`: Pre-Flight Validation RunStep

**Gate**：無（自動執行）

**失敗處理**：如果 `blocking_failures > 0`，停止執行並返回錯誤

---

### Phase 1: 健康檢查 (Gate 1)

**執行順序**：
2. 步驟 1.0: WordPress 站點健康檢查

#### 步驟 1.0: 健康檢查

**工具**：`web_generation.divi_health_check`

**輸入**：
- `workspace_id`: 從 context 獲取
- `site_id`: 從 input 獲取

**驗證項目**：
- WordPress Plugin API 健康狀態
- 站點可訪問性

**輸出**：
- `health_result`: 健康檢查結果（包含 status, passed）
- `runstep`: Health Check RunStep

**Gate**：無（自動執行）

**失敗處理**：如果 `status != "healthy"`，停止執行並返回錯誤

---

### Phase 2: 映射驗證 (Gate 2)

**執行順序**：
3. 步驟 2.0: 映射驗證

#### 步驟 2.0: 映射驗證

**工具**：`web_generation.divi_mapping_validation`

**輸入**：
- `workspace_id`: 從 context 獲取
- `site_id`: 從 input 獲取
- `page_ids`: 從 input 獲取

**驗證項目**：
- 頁面在 registry 中存在
- 頁面有有效的 template_id
- 頁面有 slot_schema
- 模板在 registry 中存在

**輸出**：
- `mapping_result`: 映射驗證結果（包含 passed, errors, warnings）
- `runstep`: Mapping Validation RunStep

**Gate**：無（自動執行）

**失敗處理**：如果 `passed == false`，停止執行並返回錯誤

---

### Phase 3: Patch Plan 驗證 (Gate 3)

**執行順序**：
4. 步驟 3.0: Patch Plan 驗證

#### 步驟 3.0: Patch Plan 驗證

**工具**：`web_generation.divi_patch_plan_validation`

**輸入**：
- `patch_plan`: 從 input 獲取
- `scope_page_ids`: 從 input 獲取
- `target_slot_ids`: 從 input 獲取（可選）
- `template_schemas`: 從 registry 獲取（可選）
- `run_id`: 從 context 獲取

**驗證項目**：
- patch_plan.operations 非空
- operation.page_id 與 scope.pages 完全一致
- slots 只包含目標 slot_ids（無額外修改）
- SlotSchemaValidator 驗證通過

**輸出**：
- `patch_plan_result`: Patch Plan 驗證結果（包含 passed, errors）
- `runstep`: Patch Plan Validation RunStep（status=WAITING_GATE）
- `gate_info`: GateInfo 對象（如果 passed）

**Gate**：**需要 Gate 批准** 🚧

**Gate 類型**：驗證型（validation）

**失敗處理**：如果 `passed == false`，停止執行並返回錯誤

**Gate 批准後**：繼續執行下一步

---

### Phase 4: 套用前驗證 (Gate 4)

**執行順序**：
5. 步驟 4.0: 套用前驗證

#### 步驟 4.0: 套用前驗證

**工具**：`web_generation.divi_apply_gate_validation`

**輸入**：
- `workspace_id`: 從 context 獲取
- `site_id`: 從 input 獲取
- `page_ids`: 從 input 獲取
- `mode`: 從 input 獲取（"draft" 或 "publish"）
- `diff_reviewed`: 從 input 獲取（可選，預設 false）
- `run_id`: 從 context 獲取
- `checkpoint_id`: 自動生成

**驗證項目**：
- mode 確認（publish 模式需要二次確認）
- Diff 審核確認
- 記錄當前 revision_ids（用於回滾）

**輸出**：
- `apply_gate_result`: 套用前驗證結果（包含 passed, checks, current_revisions）
- `runstep`: Apply Gate RunStep（status=WAITING_GATE）
- `gate_info`: GateInfo 對象
- `checkpoint_id`: Checkpoint ID（用於回滾）

**Gate**：**需要 Gate 批准** 🚧

**Gate 類型**：改動型（modification）

**失敗處理**：如果 `passed == false`，停止執行並返回錯誤

**Gate 批准後**：繼續執行下一步

---

### Phase 5: 套用 Patch

**執行順序**：
6. 步驟 5.0: 套用 Patch

#### 步驟 5.0: 套用 Patch

**工具**：`web_generation.divi_apply_patch`

**輸入**：
- `workspace_id`: 從 context 獲取
- `site_id`: 從 input 獲取
- `patch_plan`: 從 input 獲取
- `mode`: 從 input 獲取（"draft" 或 "publish"）
- `pre_revision_ids`: 從 `apply_gate_result.current_revisions` 獲取
- `checkpoint_id`: 從 `apply_gate_result.checkpoint_id` 獲取

**執行項目**：
- 調用 WordPressPluginClient.apply_patch_plan()
- 記錄 DiviRevision（含必填 id）
- 標記其他 revisions 為非 current

**輸出**：
- `apply_result`: 套用結果（包含 success, revision_ids, revisions）
- `runstep`: Apply Patch RunStep

**Gate**：無（自動執行）

**失敗處理**：
- 如果 `success == false`，調用 RollbackService.automatic_rollback()
- 返回錯誤和回滾狀態

---

### Phase 6: 驗證結果

**執行順序**：
7. 步驟 6.0: 驗證結果

#### 步驟 6.0: 驗證結果

**工具**：`web_generation.divi_verify_update`

**輸入**：
- `workspace_id`: 從 context 獲取
- `site_id`: 從 input 獲取
- `page_ids`: 從 input 獲取

**驗證項目**：
- 使用 get_revision_diff() 驗證每個頁面的更新
- 確認 revision 已正確應用

**輸出**：
- `verify_result`: 驗證結果（包含 success, results）
- `runstep`: Verify Result RunStep

**Gate**：無（自動執行）

**失敗處理**：記錄驗證失敗，但不停止執行（已完成套用）

---

## Gate 批准流程

### Gate 3: Patch Plan 驗證

**何時觸發**：Patch Plan 驗證通過後

**Gate 資訊**：
- `operation`: `BATCH_UPDATE`
- `impact_summary`: 影響範圍摘要（頁面數量、slot 數量）
- `affected_resources`: 受影響的頁面列表
- `checkpoint_required`: `false`（驗證型 Gate）

**批准後**：繼續執行 Gate 4

**拒絕後**：停止執行，返回錯誤

### Gate 4: 套用前驗證

**何時觸發**：套用前驗證通過後

**Gate 資訊**：
- `operation`: `PUBLISH`（如果是 publish 模式）
- `impact_summary`: 最終影響範圍摘要
- `affected_resources`: 受影響的頁面列表
- `checkpoint_required`: `true`（改動型 Gate，必須有 checkpoint）
- `checkpoint_id`: Checkpoint ID

**批准後**：繼續執行 Apply Patch

**拒絕後**：停止執行，返回錯誤

---

## RunStep 和 GateInfo 生成

所有步驟都會生成 `RunStep` 對象，包含：

- `index`: 步驟索引（0-6）
- `code`: 步驟代碼（preflight_validation, health_check, mapping_validation, patch_plan_validation, apply_gate, apply_patch, verify_result）
- `status`: 步驟狀態（COMPLETED, FAILED, WAITING_GATE）
- `requires_gate`: 是否需要 Gate（Gate 3 和 Gate 4 為 true）
- `gate_status`: Gate 狀態（pending, approved, rejected）
- `changes`: AffectedResource 列表
- `input_summary`: 輸入摘要
- `output_summary`: 輸出摘要

Gate 3 和 Gate 4 額外生成 `GateInfo` 對象，包含：

- `run_id`: Run ID
- `operation`: GateableOperation
- `impact_summary`: 影響範圍摘要
- `affected_resources`: 受影響的資源列表
- `checkpoint_required`: 是否需要 checkpoint
- `checkpoint_id`: Checkpoint ID（Gate 4）

---

## 輸入參數

```yaml
workspace_id: string          # 必填：Workspace ID（從 context 獲取）
site_id: string              # 必填：Site ID
page_ids: list[int]          # 必填：要更新的頁面 ID 列表
patch_plan: object           # 必填：Patch Plan 對象
mode: string                 # 可選：執行模式（"draft" 或 "publish"），預設 "draft"
content_source: string       # 可選：內容來源路徑（用於 Pre-Flight 掃描）
diff_reviewed: boolean       # 可選：Diff 是否已審核，預設 false
target_slot_ids: list[string] # 可選：目標 slot IDs
```

---

## 輸出結果

```yaml
success: boolean             # 執行是否成功
run_id: string               # Run ID
steps: list[RunStep]         # 所有步驟的 RunStep 列表
gates: list[GateInfo]        # Gate 資訊列表（Gate 3 和 Gate 4）
checkpoint_id: string        # Checkpoint ID（Gate 4 生成）
preflight_result: object     # Pre-Flight 驗證結果
health_result: object        # 健康檢查結果
mapping_result: object       # 映射驗證結果
patch_plan_result: object    # Patch Plan 驗證結果
apply_gate_result: object    # 套用前驗證結果
apply_result: object         # 套用結果
verify_result: object        # 驗證結果
```

---

## 錯誤處理

### 自動回滾

如果 Apply Patch 失敗，會自動調用 `RollbackService.automatic_rollback()`：

- 使用 `pre_revision_ids` 作為回滾目標
- 回滾所有已應用的 revisions
- 記錄回滾原因

### Gate 拒絕

如果 Gate 3 或 Gate 4 被拒絕：

- 停止執行
- 返回拒絕原因
- 不進行任何修改

### 驗證失敗

如果任何驗證步驟失敗：

- 停止執行
- 返回詳細錯誤訊息
- 不進行任何修改

---

## 相關文檔

- [Divi Safeguard Implementation Plan](../../docs/DIVI_SAFEGUARD_IMPLEMENTATION_PLAN.md)
- [Divi Safeguard Integration Guide](../../docs/DIVI_SAFEGUARD_INTEGRATION_GUIDE.md)
- [Thread View Component Specification](../../docs/THREAD_VIEW_COMPONENT_SPECIFICATION.md)
