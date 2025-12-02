# 工作區存儲路徑持久化問題分析與修復

**日期**: 2025-12-02
**問題**: 用戶指定工作區存儲路徑後，目錄未在主機上創建或不可見

## 問題描述

用戶在配置工作區存儲路徑時，指定了 `/app/backend/data/workspaces/多平台內容一鍵生成`，但即使保存成功，在主機上也看不到目錄被創建。即使是 Docker 運行，也應該要持久化儲存，否則用戶無法取得檔案。

## 問題分析

### 1. Docker 卷挂載配置

從 `docker-compose.yml` 可以看到 backend 服務的卷挂載配置：

```yaml
volumes:
  - ./backend:/app/backend:rw
  - ./data:/app/data:rw
  - ./logs:/app/logs:rw
```

**關鍵問題**：
- `/app/backend` 被挂載為主機的 `./backend`（項目根目錄下的 backend 文件夾）
- `/app/data` 被挂載為主機的 `./data`（項目根目錄下的 data 文件夾）
- **但 `/app/backend/data` 這個路徑在容器內，並沒有映射到主機**

### 2. 用戶指定的路徑問題

用戶指定的路徑：`/app/backend/data/workspaces/多平台內容一鍵生成`

**問題分析**：
1. 這個路徑在容器內確實可以被創建（因為 `/app/backend` 在容器內存在）
2. 但這個路徑**不在 Docker 卷挂載的範圍內**
3. 即使代碼在容器內成功創建了目錄，用戶在主機上也看不到，因為：
   - `/app/backend` 被挂載為 `./backend`（主機上的項目根目錄下的 backend 文件夾）
   - `/app/backend/data` 在容器內，但主機上的 `./backend/data` 可能不存在或沒有被正確映射

### 3. 正確的存儲路徑

根據 Docker 卷挂載配置，**正確的存儲路徑應該是**：
- `/app/data/workspaces/多平台內容一鍵生成`
- 這個路徑會被映射到主機的 `./data/workspaces/多平台內容一鍵生成`

### 4. 代碼中的默認路徑邏輯

從 `backend/app/routes/core/workspace.py:220` 可以看到默認回退路徑：

```python
# 3. Fallback to project data directory (always available, mounted in docker-compose.yml)
project_data_dir = Path(__file__).parent.parent.parent.parent / "data" / "workspaces"
```

這個路徑會解析為 `/app/data/workspaces`，**這是正確的**，因為它會被映射到主機的 `./data/workspaces`。

## 根本原因

1. **路徑選擇錯誤**：用戶選擇了 `/app/backend/data/...`，但這個路徑不在 Docker 卷挂載範圍內
2. **缺乏路徑驗證**：代碼雖然會創建目錄，但沒有驗證路徑是否在挂載的卷中
3. **文檔說明不足**：沒有明確說明應該使用哪些路徑才能確保持久化

## 解決方案

### 方案 1：修改 Docker 卷挂載配置（推薦）

在 `docker-compose.yml` 中添加對 `/app/backend/data` 的挂載：

```yaml
volumes:
  - ./backend:/app/backend:rw
  - ./data:/app/data:rw
  - ./backend/data:/app/backend/data:rw  # 新增：支持 /app/backend/data 路徑
  - ./logs:/app/logs:rw
```

**優點**：
- 支持用戶指定的路徑
- 保持向後相容

**缺點**：
- 需要確保主機上的 `./backend/data` 目錄存在

### 方案 2：引導用戶使用正確的路徑（當前推薦）

1. **更新前端 UI**：在存儲路徑配置界面中，明確提示應該使用 `/app/data/workspaces/...` 路徑
2. **添加路徑驗證**：在後端驗證路徑是否在挂載的卷中，如果不在，給出明確的錯誤提示
3. **更新文檔**：在開發者文檔中說明正確的存儲路徑配置

### 方案 3：自動路徑轉換

在後端自動將 `/app/backend/data/...` 轉換為 `/app/data/...`：

```python
# 如果路徑是 /app/backend/data/...，自動轉換為 /app/data/...
if storage_path.startswith('/app/backend/data/'):
    storage_path = storage_path.replace('/app/backend/data/', '/app/data/', 1)
```

## 實作計劃

### 階段 1：立即修復（已完成 ✅）

**詳細實作記錄**: 見 `workspace-storage-path-validation-modularization-2025-12-02.md`

1. **添加路徑驗證邏輯** (`backend/app/routes/core/workspace.py:54-120`)
   - ✅ 新增 `_get_docker_mounted_paths()` 函數：獲取 Docker 挂載的卷路徑列表
   - ✅ 新增 `_validate_path_in_mounted_volumes()` 函數：驗證路徑是否在挂載的卷中
   - ✅ 在創建工作區時驗證路徑 (`workspace.py:473-490`)
   - ✅ 在更新工作區存儲路徑時驗證路徑 (`workspace.py:792-798`)
   - ✅ 在更新 playbook 存儲配置時驗證路徑 (`workspace.py:864-870`)
   - ✅ 如果路徑不在挂載的卷中，給出明確的錯誤提示和建議

**實作細節**：
- 函數 `_get_docker_mounted_paths()` 返回 Docker 挂載的卷路徑列表：`/app/data`, `/app/backend`, `/app/logs`
- 函數 `_validate_path_in_mounted_volumes()` 驗證路徑是否在挂載的卷中，並提供建議
- 如果路徑包含 `/app/backend/data`，自動建議使用 `/app/data` 替代
- 錯誤訊息明確說明路徑不會持久化到主機，並提供正確的路徑建議

### 階段 2：前端改進（待實作）

1. **更新前端提示** (`web-console/src/app/workspaces/[workspaceId]/page.tsx`)
   - 在存儲路徑配置界面中，明確提示應該使用 `/app/data/workspaces/...` 路徑
   - 添加路徑格式說明和範例
   - 顯示 Docker 卷挂載映射關係

### 階段 3：長期改進（可選）

1. **更新 Docker 卷挂載配置** (`docker-compose.yml`)
   - 考慮添加對 `/app/backend/data` 的挂載支持（如果需要）

2. **更新開發者文檔** (`docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`)
   - 添加工作區存儲路徑配置說明
   - 說明 Docker 卷挂載和持久化存儲的關係

3. **添加路徑自動轉換**（可選）
   - 自動將常見的錯誤路徑轉換為正確的路徑

## 相關代碼位置

- **Docker 配置**: `docker-compose.yml:33-38`
- **Docker 挂載路徑驗證函數**: `backend/app/routes/core/workspace.py:54-120`
  - `_get_docker_mounted_paths()`: 獲取 Docker 挂載的卷路徑列表
  - `_validate_path_in_mounted_volumes()`: 驗證路徑是否在挂載的卷中
- **存儲路徑創建邏輯**: `backend/app/routes/core/workspace.py:473-490` (已添加挂載卷驗證)
- **存儲路徑更新邏輯**: `backend/app/routes/core/workspace.py:792-798` (已添加挂載卷驗證)
- **Playbook 存儲配置更新邏輯**: `backend/app/routes/core/workspace.py:864-870` (已添加挂載卷驗證)
- **默認路徑邏輯**: `backend/app/routes/core/workspace.py:176-230`
- **前端配置界面**: `web-console/src/app/workspaces/[workspaceId]/page.tsx`

## 問題確認與解決

### 實際情況

經過檢查，用戶選擇的路徑 `/app/backend/data/workspaces/多平台內容一鍵生成` **實際上是可以正常工作的**，因為：

1. **Docker 挂載配置**：`./backend:/app/backend:rw` 已經將 `/app/backend` 挂載到主機的 `./backend`
2. **目錄已創建**：主機上的 `backend/data/workspaces/多平台內容一鍵生成/` 目錄已經存在
3. **Artifacts 目錄已創建**：`backend/data/workspaces/多平台內容一鍵生成/artifacts/` 目錄也已存在
4. **路徑有效**：`/app/backend/data` 是 `/app/backend` 的子路徑，因此會被正確挂載並持久化

### 已完成的修復

1. **添加 Docker 挂載卷驗證** (`backend/app/routes/core/workspace.py:54-120`)
   - 新增 `_get_docker_mounted_paths()` 函數，返回 Docker 挂載的卷路徑列表
   - 新增 `_validate_path_in_mounted_volumes()` 函數，驗證路徑是否在挂載的卷中
   - **注意**：`/app/backend` 下的所有路徑（包括 `/app/backend/data`）都被視為有效

2. **在創建工作區時驗證路徑** (`backend/app/routes/core/workspace.py:473-490`)
   - 在用戶指定存儲路徑時，驗證路徑是否在 Docker 挂載的卷中
   - 如果不在，拋出明確的錯誤，說明路徑不會持久化到主機

3. **在更新工作區存儲路徑時驗證路徑** (`backend/app/routes/core/workspace.py:792-798`)
   - 在更新存儲路徑時，驗證新路徑是否在 Docker 挂載的卷中
   - 如果不在，拋出明確的錯誤，說明路徑不會持久化到主機

4. **在更新 Playbook 存儲配置時驗證路徑** (`backend/app/routes/core/workspace.py:864-870`)
   - 在更新 playbook 存儲配置時，驗證路徑是否在 Docker 挂載的卷中
   - 如果不在，拋出明確的錯誤，說明路徑不會持久化到主機

### 修復效果

- ✅ **路徑驗證**：確保用戶選擇的路徑在 Docker 挂載的卷中，可以持久化到主機
- ✅ **支持多種路徑**：支持 `/app/data/...` 和 `/app/backend/data/...` 等路徑
- ✅ **明確的錯誤訊息**：如果路徑不在挂載的卷中，會提供明確的錯誤提示
- ✅ **確保持久化**：只有通過驗證的路徑才會被接受，確保數據可以持久化到主機

## 驗證步驟

1. **測試正確的路徑**：
   - 使用正確的路徑 `/app/data/workspaces/測試工作區` 創建工作區
   - 檢查主機上的 `./data/workspaces/測試工作區` 目錄是否被創建
   - 在容器內創建文件，驗證主機上可以看到

2. **測試錯誤的路徑**：
   - 嘗試使用錯誤路徑 `/app/backend/data/workspaces/測試工作區` 創建工作區
   - 應該收到錯誤提示：`Storage path /app/backend/data/workspaces/測試工作區 is not in a mounted Docker volume and will not persist to host. Suggested path: /app/data/workspaces/測試工作區 (mapped to ./data/workspaces/測試工作區 on host)`

3. **測試更新存儲路徑**：
   - 更新現有工作區的存儲路徑為錯誤路徑
   - 應該收到相同的錯誤提示

4. **測試 Playbook 存儲配置**：
   - 更新 playbook 存儲配置為錯誤路徑
   - 應該收到類似的錯誤提示

## 參考資料

- Docker Compose 卷挂載文檔：https://docs.docker.com/compose/compose-file/compose-file-v3/#volumes
- 項目開發者文檔：`docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`

