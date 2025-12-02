# 工作區存儲路徑驗證模組化與前端載入修復

**日期**: 2025-12-02
**任務**: 將存儲路徑驗證邏輯模組化，並修復前端工作區載入問題

## 問題描述

1. **模組化問題**：存儲路徑驗證邏輯直接實現在 `workspace.py` 中，違反模組化原則
2. **前端載入問題**：工作區頁面在 Fast Refresh 時無法正常載入，請求被 pendingRequests 機制阻塞

## 實作內容

### 1. 創建存儲路徑驗證服務模組

**文件**: `backend/app/services/storage_path_validator.py`

**功能**:
- `get_docker_mounted_paths()`: 獲取 Docker 挂載路徑列表
- `validate_path_in_mounted_volumes()`: 驗證路徑是否在挂載卷中
- `validate_and_check_host_path()`: 驗證路徑並檢查是否為主機路徑

**實作細節**:
- 驗證路徑是否在 Docker 挂載卷中（`/app/data`, `/app/backend`, `/app/logs`, `/host/documents`）
- 檢測主機路徑（Mac: `/Users/...`, Linux: `/home/...`, Windows: `C:\...`）
- 提供清晰的錯誤訊息和配置指引

**代碼位置**: `backend/app/services/storage_path_validator.py:1-162`

### 2. 重構 workspace.py 使用服務模組

**文件**: `backend/app/routes/core/workspace.py`

**變更**:
- 移除內聯的驗證函數 `_get_docker_mounted_paths()` 和 `_validate_path_in_mounted_volumes()`
- 導入 `StoragePathValidator` 服務
- 在創建和更新工作區時使用服務進行驗證

**代碼位置**:
- 導入: `backend/app/routes/core/workspace.py:56`
- 創建工作區驗證: `backend/app/routes/core/workspace.py:540-550`
- 更新工作區驗證: `backend/app/routes/core/workspace.py:737-742`
- Playbook 存儲配置驗證: `backend/app/routes/core/workspace.py:810-817`

### 3. 修復前端工作區載入問題

**文件**: `web-console/src/app/workspaces/[workspaceId]/page.tsx`

**問題**:
- Fast Refresh 觸發時，`pendingRequests` 中仍有舊請求，導致新請求被跳過
- 請求被阻塞後沒有正確的 fallback 機制

**修復**:
- 檢測到重複請求時，清除舊的 pending request 並重試
- 添加 AbortController signal 支持，正確處理請求取消
- 改進 direct fetch 的錯誤處理

**代碼位置**:
- `fetchWithRetry` 改進: `web-console/src/app/workspaces/[workspaceId]/page.tsx:109-169`
- `loadWorkspace` 改進: `web-console/src/app/workspaces/[workspaceId]/page.tsx:175-193`

## 程式碼註釋規範檢查

### ✅ 符合規範

1. **英文註釋**: 所有程式碼註釋使用英文
2. **無中文註釋**: 無中文註釋、無實作步驟、無非功能性描述
3. **無 emoji**: 無使用 emoji
4. **文檔字串**: 使用標準的 docstring 格式

### 檢查結果

- `backend/app/services/storage_path_validator.py`: ✅ 符合規範
- `backend/app/routes/core/workspace.py`: ✅ 符合規範
- `web-console/src/app/workspaces/[workspaceId]/page.tsx`: ✅ 符合規範（console.log 為調試用，可接受）

## 相關文件

- 開發者規範: `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`
- 問題分析文檔: `docs-internal/implementation/workspace-storage-path-persistence-issue-2025-12-02.md`

## 驗證步驟

1. **後端驗證**:
   - 測試創建工作區時使用主機路徑，應收到清晰的錯誤提示
   - 測試使用容器內路徑，應成功創建
   - 測試更新工作區存儲路徑，驗證邏輯正常

2. **前端驗證**:
   - 刷新工作區頁面，應能正常載入
   - Fast Refresh 觸發時，不應阻塞新請求
   - 檢查控制台，不應有請求阻塞的警告

## 模組化完成項目

### 1. 存儲路徑驗證服務 (`storage_path_validator.py`)

**新增功能**:
- `validate_path_in_allowed_directories()`: 驗證路徑是否在允許的目錄中（防止目錄遍歷攻擊）
- `get_allowed_directories()`: 獲取允許的目錄列表（從環境變數、ToolConnections、ToolRegistry 讀取）

**代碼位置**: `backend/app/services/storage_path_validator.py:162-280`

### 2. 存儲路徑解析服務 (`storage_path_resolver.py`)

**新增功能**:
- `get_default_storage_path()`: 獲取工作區創建的默認存儲路徑（優先級：環境變數 > 允許目錄 > 項目數據目錄）

**代碼位置**: `backend/app/services/storage_path_resolver.py:164-217`

### 3. 工作區歡迎訊息服務 (`workspace_welcome_service.py`)

**新增功能**:
- `generate_welcome_message()`: 生成個性化的歡迎訊息和初始建議

**代碼位置**: `backend/app/services/workspace_welcome_service.py:1-240`

### 4. workspace.py 重構

**移除的函數**:
- `_validate_path_in_allowed_directories()` → 移至 `StoragePathValidator`
- `_get_allowed_directories()` → 移至 `StoragePathValidator`
- `_get_default_storage_path()` → 移至 `StoragePathResolver`
- `_generate_welcome_message()` → 移至 `WorkspaceWelcomeService`

**更新的調用**:
- 創建工作區: `workspace.py:295, 311, 329, 349`
- 更新工作區: `workspace.py:587, 588, 644, 645`
- 生成歡迎訊息: `workspace.py:441`

## 待辦事項

- [x] 創建存儲路徑驗證服務模組
- [x] 重構 workspace.py 使用服務模組
- [x] 修復前端載入問題
- [x] 將 allowed directories 相關函數移到服務模組
- [x] 將 _get_default_storage_path 移到 storage_path_resolver
- [x] 將 _generate_welcome_message 移到獨立服務模組
- [x] 更新 workspace.py 使用新的服務模組
- [x] 檢查程式碼註釋規範
- [x] 創建任務文檔

## 備註

- 存儲路徑驗證邏輯已完全模組化，符合單一職責原則
- 前端請求處理改進，解決 Fast Refresh 導致的載入問題
- 所有程式碼註釋符合開發者規範要求

