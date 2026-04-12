# IG 內容同步

## 概述

從 Instagram 拉取 posts/reels/stories 內容到本地 workspace。

## ⚠️ 前置要求

**必須先在 site-hub 完成以下步驟**：

1. **OAuth 授權**：在 site-hub UI 完成 Instagram OAuth 授權
2. **Channel 綁定**：綁定 Instagram Business Account 到 ChannelConfig
3. **獲取 channel_config_id**：從 site-hub 獲取對應的 `channel_config_id`

**重要**：
- Token 和授權由 site-hub 統一管理
- 本 playbook 只負責拉取數據，不做 OAuth 授權
- 如果 channel_config_id 無效或 token 過期，會返回錯誤

## 功能

- ✅ 支持拉取 posts、reels、stories
- ✅ 自動下載媒體文件到 workspace storage
- ✅ 生成 metadata 並保存
- ✅ 可選：觸發 openseo pipeline 處理內容

## 輸入參數

### 必需參數

- `channel_config_id` (integer): Channel Config ID（由 site-hub 管理）
- `workspace_id` (string): Mindscape workspace ID

### 可選參數

- `content_type` (string): 要拉取的內容類型
  - `posts`: 只拉取 posts
  - `reels`: 只拉取 reels
  - `stories`: 只拉取 stories（24小時內）
  - `all`: 拉取所有類型（預設）

- `media_type` (string): 媒體類型過濾（僅用於 posts）
  - `IMAGE`: 只拉取圖片
  - `VIDEO`: 只拉取視頻
  - `CAROUSEL_ALBUM`: 只拉取輪播

- `limit` (integer): 每次拉取的數量限制（預設：25）

- `since` (string): 開始時間（ISO 8601 格式）

- `until` (string): 結束時間（ISO 8601 格式）

- `trigger_openseo` (boolean): 是否觸發 openseo pipeline 處理拉取的內容（預設：false）

## 輸出

- `posts`: 拉取的 posts 列表
- `reels`: 拉取的 reels 列表
- `stories`: 拉取的 stories 列表
- `media_files`: 下載的媒體文件路徑列表
- `metadata`: 內容 metadata
- `seo_results`: SEO 處理結果（如果啟用 trigger_openseo）

## 使用範例

### 拉取所有內容

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "content_type": "all",
  "limit": 25
}
```

### 只拉取 posts

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "content_type": "posts",
  "media_type": "IMAGE",
  "limit": 50
}
```

### 拉取並觸發 SEO 處理

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "content_type": "posts",
  "trigger_openseo": true
}
```

## 注意事項

1. **Stories 時效**：Stories 僅在 24 小時內可用
2. **API 配額**：注意 Instagram Graph API 的配額限制（10 請求/秒 per app）
3. **Token 管理**：如果 token 過期，需要回到 site-hub 重新授權
4. **權限要求**：需要 `instagram_basic`、`instagram_manage_insights`、`pages_read_user_content` 權限

## 相關文檔

- [IG Channel 串接實作計劃](../../openseo/docs/IG_CHANNEL_IMPLEMENTATION_PLAN_2026-01-05.md)
- [Site-Hub Channel Binding API](../../../site-hub/site-hub-api/v1/channel_binding.py)

