# 雲端發佈功能設計方案

## 一、概述

雲端發佈功能允許用戶將本地開發的 Playbook 和 Capability 發佈到雲端服務。

**⚠️ 重要架構決策**：
- **local-core** 提供發佈 UI 和**中性發佈服務接口**
- **發佈服務**（可配置，如 mindscape-ai-cloud）負責實際的發佈邏輯
- **site-hub** 提供 Publisher API 作為最終的發佈目標

**設計原則**：
- **解耦**：local-core 不硬編碼依賴任何特定服務
- **配置化**：用戶可配置發佈服務的 API 端點和認證
- **可擴展**：未來可支持不同的發佈服務提供商

**發佈流程**：
```
local-core (UI + 中性接口)
    ↓ 調用配置的發佈服務 API
發佈服務（如 mindscape-ai-cloud）
    ↓ 處理打包、上傳、註冊
site-hub (Publisher API)
    ↓ 最終存儲
Storage (GCS/S3/R2)
```

## 二、核心概念

### 2.1 Adapter 機制

Adapter 是一個抽象層，負責：
- **封裝發佈邏輯**：每個 Adapter 處理特定平台的發佈流程
- **統一介面**：所有 Adapter 實現相同的介面，便於擴展
- **配置管理**：每個 Adapter 有獨立的配置

### 2.2 發佈流程

```
local-core (用戶操作)
    ↓
選擇要發佈的 Playbook/Capability
    ↓
調用 mindscape-ai-cloud 發佈 API
    ↓
mindscape-ai-cloud 處理：
  - 驗證內容（manifest、schema）
  - 打包（.mindpack 格式）
  - 上傳到 Storage (GCS/S3/R2)
  - 調用 site-hub Publisher API 註冊
    ↓
發佈完成
```

## 三、架構設計

### 3.1 前端組件結構

```
CloudPublishPanel/
├── AdapterList/          # 適配器列表
├── ContentSelector/       # 內容選擇器（Playbook/Capability）
├── PublishWizard/        # 發佈精靈
└── PublishHistory/       # 發佈歷史
```

### 3.2 後端 API 設計

#### 3.2.1 Publish Service Configuration API（local-core）

```python
# GET /api/v1/publish-service/config
# 獲取當前配置的發佈服務

# PUT /api/v1/publish-service/config
# 配置發佈服務
# Body: {
#   "api_url": "https://api.mindscape-ai-cloud.com",
#   "api_key": "your-api-key",
#   "enabled": true
# }

# POST /api/v1/publish-service/test
# 測試發佈服務連接
```

#### 3.2.2 Publish API（local-core）

```python
# POST /api/v1/publish
# 發佈內容到配置的發佈服務
# Body: {
#   "content_type": "playbook" | "capability",
#   "content_id": "openseo.seo_optimization",
#   "version": "1.0.0",
#   "options": {...}
# }
# 此 API 會調用配置的發佈服務 API（不關心是 mindscape-ai-cloud 還是其他）

# GET /api/v1/publish/history
# 獲取發佈歷史（從配置的發佈服務查詢）

# GET /api/v1/publish/{publish_id}/status
# 查詢發佈狀態（從配置的發佈服務查詢）
```

#### 3.2.3 Publish API（mindscape-ai-cloud）

```python
# POST /api/v1/publish
# 實際執行發佈邏輯
# Body: {
#   "content_type": "playbook" | "capability",
#   "content_id": "openseo.seo_optimization",
#   "version": "1.0.0",
#   "provider_id": "mindscape-ai",
#   "storage_backend": "gcs" | "s3" | "r2",
#   "options": {...}
# }
# 此 API 會：
# 1. 打包內容為 .mindpack
# 2. 上傳到 Storage
# 3. 調用 site-hub Publisher API 註冊

# GET /api/v1/publish/history
# 獲取發佈歷史

# GET /api/v1/publish/{publish_id}/status
# 查詢發佈狀態
```

### 3.3 Adapter 介面定義

```python
class PublishAdapter(ABC):
    """發佈適配器抽象基類"""

    @abstractmethod
    def get_adapter_id(self) -> str:
        """返回適配器 ID"""
        pass

    @abstractmethod
    def get_adapter_name(self) -> str:
        """返回適配器名稱"""
        pass

    @abstractmethod
    def get_adapter_type(self) -> str:
        """返回適配器類型：cloud | self-hosted | hybrid"""
        pass

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """驗證配置"""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """檢查是否已配置"""
        pass

    @abstractmethod
    async def publish(
        self,
        content_type: str,  # "playbook" | "capability"
        content_id: str,
        package_path: Path,  # .mindpack 文件路徑
        version: str,
        options: Dict[str, Any]
    ) -> PublishResult:
        """執行發佈"""
        pass

    @abstractmethod
    async def test_connection(self) -> Tuple[bool, str]:
        """測試連接"""
        pass
```

## 四、實現方案

### 4.1 第一階段：基礎架構

1. **local-core 端（中性接口）**
   - 實現發佈服務配置 API（`/api/v1/publish-service/config`）
   - 實現 `/api/v1/publish` 端點（調用配置的發佈服務）
   - 實現發佈歷史查詢（從配置的發佈服務查詢）
   - 完善 `CloudPublishPanel` 組件
   - 實現發佈服務配置 UI
   - 實現內容選擇器

2. **發佈服務端**（如 mindscape-ai-cloud，需要實現）
   - 實現 `/api/v1/publish` 端點（實際發佈邏輯）
   - 實現打包邏輯（重用 `package_capability.py`）
   - 實現上傳到 Storage 邏輯
   - 實現調用 site-hub Publisher API 邏輯
   - 實現發佈歷史記錄

### 4.2 第二階段：mindscape-ai-cloud 發佈服務實現

1. **發佈服務**
   - 創建 `PublishService` 處理發佈邏輯
   - 重用 `package_capability.py` 進行打包
   - 實現 Storage 上傳（GCS/S3/R2）
   - 實現 site-hub Publisher API 調用

2. **配置管理**
   - 管理 Publisher API Key（從 site-hub 獲取或配置）
   - 管理 Storage 配置（bucket、credentials）
   - 管理 provider_id 配置

### 4.3 第三階段：進階功能

1. **批量發佈**
   - 一次發佈多個 Playbook/Capability
   - 批次處理和進度追蹤

2. **版本管理**
   - 自動版本號生成
   - 版本衝突檢測

3. **發佈預覽**
   - 發佈前預覽內容
   - 差異對比

## 五、與現有系統的整合

### 5.1 利用現有機制

- **Cloud Providers**：重用 `CloudExtensionManager` 和 `GenericHttpProvider`
- **Capability Installer**：重用打包和驗證邏輯
- **.mindpack 格式**：使用現有的打包格式

### 5.2 擴展點

- **Adapter 註冊**：允許動態註冊自定義 Adapter
- **發佈後處理**：支援發佈後的 hook（通知、同步等）

## 六、資料模型

### 6.1 發佈服務配置（local-core）

```json
{
  "api_url": "https://api.mindscape-ai-cloud.com",
  "api_key": "your-api-key",
  "enabled": true,
  "provider_id": "mindscape-ai",
  "storage_backend": "gcs",
  "storage_config": {
    "bucket": "your-bucket"
  }
}
```

**配置說明**：
- `api_url`: 發佈服務的 API 端點（可以是 mindscape-ai-cloud 或其他服務）
- `api_key`: 認證用的 API Key
- `enabled`: 是否啟用發佈服務
- `provider_id`: Provider ID（用於 site-hub Publisher API）
- `storage_backend`: Storage 後端（gcs, s3, r2）
- `storage_config`: Storage 配置（bucket、credentials 等）

### 6.2 發佈記錄

```json
{
  "publish_id": "uuid",
  "adapter_id": "cloud-provider",
  "content_type": "playbook",
  "content_id": "openseo.seo_optimization",
  "version": "1.0.0",
  "status": "success" | "failed" | "pending",
  "created_at": "2026-01-03T10:00:00Z",
  "completed_at": "2026-01-03T10:01:00Z",
  "error": null
}
```

## 七、用戶流程

1. **配置發佈服務**
   - 進入「雲端發佈」設定頁
   - 配置發佈服務 API URL（例如：`https://api.mindscape-ai-cloud.com`）
   - 配置 API Key
   - 配置 Provider ID 和 Storage 設定（可選）
   - 測試連接

2. **選擇發佈內容**
   - 選擇 Playbook 或 Capability
   - 選擇版本
   - 預覽內容

3. **執行發佈**
   - 確認發佈選項
   - 執行發佈（local-core 會調用配置的發佈服務）
   - 查看發佈狀態

4. **查看歷史**
   - 查看發佈記錄（從配置的發佈服務查詢）
   - 重新發佈或回滾

## 八、技術要點

### 8.1 打包流程

1. 驗證 manifest 和 schema
2. 收集所有依賴
3. 打包成 .mindpack
4. 計算 checksum
5. 準備 metadata

### 8.2 發佈流程（local-core）

1. 讀取發佈服務配置
2. 驗證配置有效性
3. 調用發佈服務 API（POST /api/v1/publish）
4. 返回發佈結果

### 8.2.1 發佈流程（發佈服務，如 mindscape-ai-cloud）

1. 接收發佈請求
2. 驗證內容（manifest、schema）
3. 打包成 .mindpack
4. 上傳到 Storage
5. 調用 site-hub Publisher API 註冊
6. 記錄發佈結果

### 8.3 錯誤處理

- **配置缺失**：提示用戶配置發佈服務
- **網路錯誤**：重試機制（local-core 和發佈服務都需要）
- **認證失敗**：提示重新配置 API Key
- **版本衝突**：提示處理方案
- **驗證失敗**：顯示詳細錯誤（從發佈服務返回）

## 九、後續擴展

1. **CI/CD 整合**：自動發佈流程
2. **多環境支援**：開發、測試、生產環境
3. **權限控制**：發佈權限管理
4. **審核流程**：發佈前審核機制
5. **回滾功能**：版本回滾

