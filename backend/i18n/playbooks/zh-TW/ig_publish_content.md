# IG 內容發布

## 概述

發布內容到 Instagram（支持 photo、reel、carousel）。

## ⚠️ 前置要求

**必須先在 site-hub 完成以下步驟**：

1. **OAuth 授權**：在 site-hub UI 完成 Instagram OAuth 授權
2. **Channel 綁定**：綁定 Instagram Business Account 到 ChannelConfig
3. **獲取 channel_config_id**：從 site-hub 獲取對應的 `channel_config_id`

**重要**：
- Token 和授權由 site-hub 統一管理
- 本 playbook 只負責發布內容，不做 OAuth 授權
- 如果 channel_config_id 無效或 token 過期，會返回錯誤

## 功能

- ✅ 支持發布 photo（支持延遲發布，最多 6 個月後）
- ✅ 支持發布 reel（不支持延遲發布，必須立即發布）
- ✅ 支持發布 carousel（多張圖片）
- ❌ **不支持發布 Stories**（Graph API 限制，只能拉取）

## 媒體限制

### Photo

- **格式**：JPEG, PNG
- **最大尺寸**：8192x8192 像素
- **文件大小**：最大 30MB
- **延遲發布**：支持 `scheduled_publish_time`（最多 6 個月後）

### Reel

- **格式**：MP4, MOV
- **視頻長度**：3 秒 - 90 秒
- **視頻尺寸**：最小 500x500 像素，最大 1920x1920 像素
- **文件大小**：最大 100MB
- **延遲發布**：❌ 不支持（必須立即發布）

### Carousel

- **格式**：支持多張圖片，每張限制同 Photo
- **延遲發布**：支持 `scheduled_publish_time`（最多 6 個月後）

## 輸入參數

### 必需參數

- `channel_config_id` (integer): Channel Config ID（由 site-hub 管理）
- `workspace_id` (string): Mindscape workspace ID
- `media_type` (string): 媒體類型
  - `photo`: 發布照片
  - `reel`: 發布 Reel
  - `carousel`: 發布輪播
  - ⚠️ **不支持 `story`**（Graph API 限制）
- `media_path` (string): 媒體文件路徑（workspace 內的相對路徑或絕對路徑）
- `caption` (string): 貼文標題/描述

### 可選參數

- `hashtags` (array): Hashtags 列表（會自動添加到 caption）
- `scheduled_publish_time` (string): 延遲發布時間（ISO 8601 格式，僅支持 photo，最多 6 個月後）
- `location_id` (string): 位置 ID
- `user_tags` (array): 用戶標籤列表
- `cover_url` (string): Reel 封面 URL（僅用於 reel）
- `share_to_feed` (boolean): 是否分享到 Feed（僅用於 reel，預設：true）

## 輸出

- `published_post`: 發布的 post 信息（photo）
- `published_reel`: 發布的 reel 信息
- `published_carousel`: 發布的 carousel 信息
- `media_id`: 發布的媒體 ID
- `permalink`: 發布內容的永久連結
- `validation_result`: 媒體驗證結果

## 使用範例

### 發布 Photo

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "media_type": "photo",
  "media_path": "posts/photo_001.jpg",
  "caption": "這是一張美麗的照片",
  "hashtags": ["photography", "nature", "beautiful"]
}
```

### 發布 Photo（延遲發布）

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "media_type": "photo",
  "media_path": "posts/photo_002.jpg",
  "caption": "這張照片將在明天發布",
  "scheduled_publish_time": "2024-12-31T12:00:00Z"
}
```

### 發布 Reel

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "media_type": "reel",
  "media_path": "reels/reel_001.mp4",
  "caption": "這是一個精彩的 Reel",
  "hashtags": ["reel", "video", "fun"],
  "share_to_feed": true
}
```

### 發布 Carousel

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "media_type": "carousel",
  "media_path": "carousels/carousel_001/",
  "caption": "這是一個輪播貼文",
  "hashtags": ["carousel", "multiple", "images"]
}
```

## 注意事項

1. **Stories 不支持發布**：Graph API 不支持發布 Stories，只能拉取
2. **Reel 必須立即發布**：不支持延遲發布
3. **媒體驗證**：發布前會自動驗證媒體格式和大小限制
4. **API 配額**：注意 Instagram Graph API 的配額限制（10 請求/秒 per app）
5. **Token 管理**：如果 token 過期，需要回到 site-hub 重新授權
6. **權限要求**：需要 `instagram_content_publish` 權限

## 相關文檔

- [IG Channel 串接實作計劃](../../openseo/docs/IG_CHANNEL_IMPLEMENTATION_PLAN_2026-01-05.md)
- [Site-Hub Channel Binding API](../../../site-hub/site-hub-api/v1/channel_binding.py)

