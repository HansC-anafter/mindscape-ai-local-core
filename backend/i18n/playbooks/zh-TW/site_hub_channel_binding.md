# Site-Hub Channel 綁定

## 目標
將 Site-Hub 的特定 Channel 綁定到 Local-Core 工作空間。

## 步驟

### 1. 獲取可用 Channels

使用 `site_hub_get_console_kit_channels` 工具從 Site-Hub 獲取可用頻道：

```python
channels_result = await call_tool(
    "site_hub_get_console_kit_channels",
    {
        "runtime_id": "runtime_abc123",
        "agency": "openseo",  # 可選
        "tenant": "openseo",  # 可選
        "chainagent": "sinnie yoga",  # 可選
        "channel_type": "line"  # 可選
    }
)
```

**注意**: 此工具需要 Runtime Environment 配置了 OAuth2 認證（Google OAuth）。

### 2. 選擇 Channel

如果提供了 `channel_id`，直接使用該 Channel。
否則，從獲取的 Channels 列表中選擇第一個匹配的 Channel。

### 3. 綁定 Channel

使用 `site_hub_bind_channel` 工具將 Channel 綁定到 Workspace：

```python
binding_result = await call_tool(
    "site_hub_bind_channel",
    {
        "workspace_id": "workspace_123",
        "runtime_id": "runtime_abc123",
        "channel_id": "channel_xyz789",
        "channel_type": "line",
        "channel_name": "LINE Channel",
        "agency": "openseo",
        "tenant": "openseo",
        "chainagent": "sinnie yoga",
        "binding_config": {
            "push_enabled": true,
            "notification_enabled": true
        }
    }
)
```

## 輸入參數

### 必需參數
- `workspace_id`: Local-Core 工作空間 ID
- `runtime_id`: Site-Hub Runtime Environment ID

### 可選參數
- `agency`: Agency 名稱（用於過濾）
- `tenant`: Tenant 名稱（用於過濾）
- `chainagent`: ChainAgent 名稱（用於過濾）
- `channel_type`: Channel 類型（用於過濾，例如 "line"）
- `channel_id`: 直接指定 Channel ID（跳過選擇步驟）
- `binding_config`: 綁定配置（push_enabled, notification_enabled 等）

## 輸出

- `binding_id`: 創建的綁定 ID
- `binding`: 完整的綁定資訊
- `channel`: 綁定的 Channel 資訊

## 錯誤處理

### OAuth2 認證未配置
- 確保 Runtime Environment 的 `auth_type` 為 "oauth2"
- 確保 `auth_config` 包含有效的 OAuth2 token

### Channel 未找到
- 檢查過濾條件是否正確
- 確認 Site-Hub 中確實存在該 Channel

### 綁定失敗
- 檢查 workspace_id 是否有效
- 確認執行上下文包含必要的權限

## 完成

綁定完成後，Channel 將可以在 Workspace 中使用，用於：
- 推送消息到 Channel
- 接收來自 Channel 的消息
- 其他 Channel 相關功能

