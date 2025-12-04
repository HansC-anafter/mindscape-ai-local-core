# Playbook Runtime 配置擴展實作任務

**日期**: 2025-12-05  
**任務範圍**: 擴展 Playbook 模型以支援 Cloud Runtime 配置  
**相關評估**: `playbook-design-evaluation-2025-12-05.md`

---

## 任務背景

根據 Playbook 設計原則評估，當前實作缺少完整的 Runtime 配置支援，需要擴展以支援 Cloud 執行場景。

**評估結果**: 當前符合度 80%，缺少 `runtime_tier` 和完整的 `runtime` 配置塊。

---

## 實作任務清單

### 任務 1: 擴展 PlaybookMetadata 模型

**檔案**: `backend/app/models/playbook.py`

**狀態**: ⏳ 待實作

**實作內容**:
- [ ] 添加 `runtime_tier` 欄位（Optional[str]）
  - 值：`local` | `cloud_recommended` | `cloud_only`
  - 預設：`None`
  - 描述：Runtime tier 標示此 playbook 建議的執行環境
  
- [ ] 添加 `runtime` 配置塊（Optional[Dict[str, Any]]）
  - 結構：
    ```python
    {
        "backend": "local_agent" | "remote_crs",
        "requires": ["long_context", "job_queue", "multi_tenant"],
        "supports_schedule": bool,
        "max_expected_duration": "PT30M",  # ISO 8601 duration
        "allowed_tools": ["wordpress.multi_site_stats", ...]
    }
    ```
  - 預設：`None`
  - 描述：Runtime 配置用於 Cloud 執行場景

**程式碼位置**: `backend/app/models/playbook.py:103-224` (PlaybookMetadata 類別)

**驗證方式**:
- [ ] 建立測試 Playbook 包含 `runtime_tier` 和 `runtime` 配置
- [ ] 驗證 PlaybookService 能正確載入這些欄位
- [ ] 驗證資料庫遷移（如需要）

---

### 任務 2: 擴展 PlaybookFileLoader 解析

**檔案**: `backend/app/services/playbook_loaders/file_loader.py`

**狀態**: ⏳ 待實作

**實作內容**:
- [ ] 在 `load_playbook_from_file()` 中解析 `runtime_tier` 欄位
  - 從 YAML frontmatter 讀取 `runtime_tier`
  - 設定到 `PlaybookMetadata.runtime_tier`
  
- [ ] 在 `load_playbook_from_file()` 中解析 `runtime` 配置塊
  - 從 YAML frontmatter 讀取 `runtime` 字典
  - 驗證結構（backend, requires, supports_schedule 等）
  - 設定到 `PlaybookMetadata.runtime`

**程式碼位置**: `backend/app/services/playbook_loaders/file_loader.py:47-117` (load_playbook_from_file 方法)

**驗證方式**:
- [ ] 建立測試 YAML 檔案包含 runtime 配置
- [ ] 驗證解析正確性
- [ ] 驗證向後相容性（沒有 runtime 配置的舊 playbook 仍可正常載入）

---

### 任務 3: 擴展 PlaybookJson 模型（可選）

**檔案**: `backend/app/models/playbook.py`

**狀態**: ⏳ 待實作（低優先級）

**實作內容**:
- [ ] 在 `PlaybookJson` 模型中添加 `runtime_tier` 欄位
- [ ] 在 `PlaybookJson` 模型中添加 `runtime` 配置塊

**說明**: 如果需要在 JSON 定義中也包含 runtime 配置（目前主要從 YAML frontmatter 讀取）

**程式碼位置**: `backend/app/models/playbook.py` (PlaybookJson 類別定義)

**驗證方式**:
- [ ] 建立測試 JSON 檔案包含 runtime 配置
- [ ] 驗證 PlaybookJsonLoader 能正確載入

---

### 任務 4: 更新 Playbook 範例文件

**檔案**: `backend/playbooks/*.yaml` (範例 playbook)

**狀態**: ⏳ 待實作

**實作內容**:
- [ ] 選擇一個 Cloud 進階 playbook 作為範例
- [ ] 在 YAML frontmatter 中添加 `runtime_tier` 和 `runtime` 配置
- [ ] 更新 SOP 內容說明 Cloud 執行相關資訊

**範例結構**:
```yaml
---
playbook_code: multi_site_daily_seo_health
runtime_tier: cloud_only
runtime:
  backend: remote_crs
  requires:
    - long_context
    - job_queue
    - multi_tenant
  supports_schedule: true
  max_expected_duration: PT30M
  allowed_tools:
    - wordpress.multi_site_stats
    - seo.serp_api
---
```

**驗證方式**:
- [ ] 驗證範例 playbook 能正確載入
- [ ] 驗證 runtime 配置正確解析

---

### 任務 5: 更新 PlaybookService 使用 Runtime 配置

**檔案**: `backend/app/services/playbook_service.py`

**狀態**: ⏳ 待實作

**實作內容**:
- [ ] 在 `get_playbook()` 中檢查 `runtime_tier`
  - 如果 `runtime_tier == "cloud_only"`，在 Local Workspace 中標示為僅 Cloud 可用
  
- [ ] 在 `list_playbooks()` 中支援過濾
  - 支援 `runtime_tier` 參數過濾
  - 支援 `runtime.backend` 參數過濾

**程式碼位置**: `backend/app/services/playbook_service.py:58-83, 85-112`

**驗證方式**:
- [ ] 測試 `get_playbook()` 正確處理 `runtime_tier`
- [ ] 測試 `list_playbooks()` 過濾功能

---

### 任務 6: 更新 API 文件與 Schema

**檔案**: 
- `backend/app/routes/core/playbook.py` (API 端點)
- API 文件（如有）

**狀態**: ⏳ 待實作

**實作內容**:
- [ ] 更新 Playbook 回應 Schema 包含 `runtime_tier` 和 `runtime`
- [ ] 更新 API 文件說明新欄位
- [ ] 更新 OpenAPI/Swagger 定義

**驗證方式**:
- [ ] 驗證 API 回應包含新欄位
- [ ] 驗證 API 文件正確性

---

## 實作優先級

1. **高優先級**:
   - 任務 1: 擴展 PlaybookMetadata 模型
   - 任務 2: 擴展 PlaybookFileLoader 解析

2. **中優先級**:
   - 任務 4: 更新 Playbook 範例文件
   - 任務 5: 更新 PlaybookService 使用 Runtime 配置

3. **低優先級**:
   - 任務 3: 擴展 PlaybookJson 模型（可選）
   - 任務 6: 更新 API 文件與 Schema

---

## 驗證檢查清單

### 功能驗證
- [ ] YAML frontmatter 中的 `runtime_tier` 能正確解析
- [ ] YAML frontmatter 中的 `runtime` 配置塊能正確解析
- [ ] 沒有 runtime 配置的舊 playbook 仍可正常載入（向後相容）
- [ ] PlaybookService 能正確處理 runtime 配置
- [ ] API 回應包含 runtime 相關欄位

### 程式碼品質
- [ ] 程式碼註釋符合規範（英文，無實作步驟）
- [ ] 無 linter 錯誤
- [ ] 型別提示完整
- [ ] 錯誤處理完善

### 文件更新
- [ ] 更新相關 API 文件
- [ ] 更新 Playbook 撰寫指南（如有）
- [ ] 更新評估報告標記為已完成

---

## 相關檔案路徑

### 核心模型
- `backend/app/models/playbook.py:103-224` - PlaybookMetadata 類別
- `backend/app/models/playbook.py` - PlaybookJson 類別（如需要）

### 載入器
- `backend/app/services/playbook_loaders/file_loader.py:47-117` - PlaybookFileLoader
- `backend/app/services/playbook_loaders/json_loader.py` - PlaybookJsonLoader（如需要）

### 服務層
- `backend/app/services/playbook_service.py:58-112` - PlaybookService

### API 層
- `backend/app/routes/core/playbook.py` - Playbook API 端點

### 範例檔案
- `backend/playbooks/*.yaml` - Playbook 範例

---

## 注意事項

1. **向後相容性**: 必須確保沒有 runtime 配置的舊 playbook 仍可正常載入
2. **預設值**: `runtime_tier` 和 `runtime` 應為 Optional，預設 `None`
3. **驗證**: `runtime_tier` 值應驗證為 `local` | `cloud_recommended` | `cloud_only`
4. **文件**: 所有變更必須更新相關文件

---

**建立日期**: 2025-12-05  
**最後更新**: 2025-12-05  
**狀態**: 待實作

