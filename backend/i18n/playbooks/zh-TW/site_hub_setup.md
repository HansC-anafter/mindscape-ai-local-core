# Site-Hub 執行環境設置

## 目標
引導用戶完成 Site-Hub 執行環境的發現、驗證和註冊。

## 步驟

### 1. 檢查環境變數

首先檢查 `SITE_HUB_API_BASE` 環境變數是否已設置。

如果未設置，提示用戶：
- 請設置 `SITE_HUB_API_BASE` 環境變數，指向 Site-Hub API 基礎 URL
- 例如：`export SITE_HUB_API_BASE=http://localhost:8102`

### 2. 發現 Site-Hub

使用 `site_hub_discover_runtime` 工具發現並驗證 Site-Hub 連接：

```python
discovery_result = await call_tool(
    "site_hub_discover_runtime",
    {
        "site_hub_base_url": None  # 可選，會自動從 SITE_HUB_API_BASE 檢測
    }
)
```

如果發現失敗：
- 檢查 Site-Hub 是否正在運行
- 檢查 URL 是否正確
- 檢查網路連接

### 3. 註冊 Runtime

如果發現成功，使用 `site_hub_register_runtime` 工具註冊：

```python
if discovery_result.get("success"):
    register_result = await call_tool(
        "site_hub_register_runtime",
        {
            "site_hub_base_url": discovery_result.get("site_hub_url"),
            "runtime_name": "Site-Hub"  # 可選，默認為 "Site-Hub"
        }
    )
```

### 4. 驗證設置

註冊完成後，驗證 runtime 是否可用：

- 檢查返回的 `runtime_id`
- 確認狀態為 "active"
- 可選：使用 `site_hub_list_channels` 工具列出可用頻道

## 錯誤處理

### 環境變數未設置
- 提示用戶設置 `SITE_HUB_API_BASE`
- 提供設置範例

### 連接失敗
- 檢查 Site-Hub 服務是否運行
- 檢查 URL 是否正確
- 檢查防火牆/網路設定

### 認證失敗
- 確認 execution_context 可用
- 檢查用戶權限

### URL 驗證失敗
- 檢查 URL 是否在 allowlist 中
- 聯繫管理員添加 URL 到 allowlist

## 完成

設置完成後，Site-Hub 將作為執行環境可用於：
- Dispatch Workspace
- Cell Workspace
- 其他需要 Site-Hub 的功能

