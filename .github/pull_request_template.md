# Pull Request

## ⚠️ 架構邊界檢查（必填）

在提交 PR 前，請確認以下項目：

### Cloud/Local-Core 分離檢查
- [ ] ❌ **未在 Local-Core 後端創建能力層 API**（如 `ig_posts.py`）
- [ ] ❌ **未在 Local-Core 前端創建 Cloud 業務 UI 組件**（如 `IG*` 組件）
- [ ] ❌ **未在 Local-Core SDK 中包含 Cloud 業務方法**（如 `listIGPosts`、`scheduleIGPost`）
- [ ] ❌ **未在 Local-Core 的 `OutcomesPanel` 等核心組件中嵌入 Cloud 業務邏輯**
- [ ] ❌ **未在 `backend/playbooks/specs/` 中添加 Cloud 業務 playbook spec**
- [ ] ✅ **所有 Cloud 功能都在 `mindscape-ai-cloud` repo 實現**
- [ ] ✅ **Local-Core 只提供核心 API，不包含業務場景邏輯**

### 敏感路徑檢查（強制審核）
- [ ] 此 PR **未修改** `web-console/src/app/capabilities/**` 路徑
  - ⚠️ 如果修改了，此 PR 需要團隊負責人強制審核
  - ⚠️ 此路徑禁止包含任何 Cloud capability UI 組件
- [ ] 此 PR **未修改** `backend/app/capabilities/*/ui/**` 路徑
  - ⚠️ 如果修改了，此 PR 需要團隊負責人強制審核
  - ⚠️ 此路徑禁止包含任何 Cloud UI 組件
- [ ] 此 PR **未修改** `backend/app/capabilities/*/playbooks/specs/**` 路徑
  - ⚠️ 如果修改了，此 PR 需要團隊負責人強制審核
  - ⚠️ Cloud playbook spec 應通過 CloudExtensionManager 從 cloud 加載

### 修改範圍確認
- [ ] 此 PR 是否修改了 `backend/playbooks/specs/`？
  - 如果是，請說明為什麼需要在 Local-Core 中放置 playbook spec
  - Cloud playbook spec 應通過 CloudExtensionManager 從 cloud 加載
- [ ] 此 PR 是否修改了 `backend/app/routes/core/` 中的路由？
  - 如果是，請確認不是 Cloud 業務 API
- [ ] 此 PR 是否修改了前端組件？
  - 如果是，請確認不是 Cloud 業務 UI 組件

## 變更說明

### 變更類型
- [ ] Bug 修復
- [ ] 新功能
- [ ] 重構
- [ ] 文檔更新
- [ ] 診斷/護欄工具（僅允許此類修改）

### 變更描述
<!-- 請詳細說明此 PR 的目的和變更內容 -->

### 相關 Issue
<!-- 如果有相關 Issue，請在此處引用 -->

## 測試

### 測試方式
<!-- 請說明如何測試此變更 -->

### 測試結果
<!-- 請說明測試結果 -->

## 檢查清單

- [ ] 代碼符合風格規範
- [ ] 已通過基本測試
- [ ] 已更新相關文件
- [ ] 已檢查沒有敏感資訊洩露
- [ ] 確認無 cloud/tenant 相關內容（core routes）
- [ ] 確認符合本地優先原則
- [ ] **已通過 CI 檢查（包括 cloud-function-leakage 和 cloud-component-leakage 檢查）**

## 備註

<!-- 其他需要說明的內容 -->

---

**⚠️ 重要提醒**：
- 如果此 PR 涉及 Cloud 業務功能，請在 `mindscape-ai-cloud` repo 提交
- Local-Core 應保持只讀狀態，僅允許必要的護欄和診斷修改
- 違反架構邊界的 PR 將被拒絕
- **修改敏感路徑（`web-console/src/app/capabilities/**`、`backend/app/capabilities/*/ui/**`）的 PR 需要團隊負責人強制審核**
