# IG Site-Hub 對接型 Playbook 設計文檔

**日期**: 2026-01-05
**版本**: 1.0.0
**目的**: 說明輕量級「對接型」playbook 的設計理念和實作範圍

---

## 📋 設計理念

### 核心原則

**避免複製 site-hub 的 OAuth/UI**：
- OAuth 授權流程完全由 site-hub 管理
- Token 生命週期由 site-hub 統一管理
- local-core/ig pack 只負責消費 site-hub 提供的配置與 Token

**輕量對接**：
- 只做數據拉取和發布，不做授權管理
- 權限校驗：只校驗 `channel_config_id` 可用（由 site-hub/Registry 管理）
- 降低耦合：local-core 不再管理 IG 授權/Token

### 架構優勢

1. **開發效率**：開發和運維都走現有 site-hub 通道
2. **維護性**：授權邏輯集中在一處（site-hub），易於維護
3. **擴展性**：未來擴展其他平台（FB/TikTok）時，只需在 site-hub 添加 OAuth，local-core 無需修改
4. **安全性**：Token 和授權統一管理，降低安全風險

---

## 📦 實作範圍

### Playbook 1: `ig_sync_content`

**功能**：從 Instagram 拉取內容到本地 workspace

**輸入參數**：
- `channel_config_id` (integer, 必需): Channel Config ID（由 site-hub 管理）
- `workspace_id` (string, 必需): Mindscape workspace ID
- `content_type` (string, 可選): 內容類型（posts/reels/stories/all，預設：all）
- `media_type` (string, 可選): 媒體類型過濾（IMAGE/VIDEO/CAROUSEL_ALBUM，僅用於 posts）
- `limit` (integer, 可選): 每次拉取的數量限制（預設：25）
- `since` (string, 可選): 開始時間（ISO 8601 格式）
- `until` (string, 可選): 結束時間（ISO 8601 格式）
- `trigger_openseo` (boolean, 可選): 是否觸發 openseo pipeline（預設：false）

**工具調用**：
- `ig.ig_fetch_posts` - 拉取 posts
- `ig.ig_fetch_reels` - 拉取 reels
- `ig.ig_fetch_stories` - 拉取 stories（24小時內）
- `openseo.ai_seo_pipeline` - 可選的 SEO 處理

**輸出**：
- `posts`: 拉取的 posts 列表
- `reels`: 拉取的 reels 列表
- `stories`: 拉取的 stories 列表
- `media_files`: 下載的媒體文件路徑列表
- `metadata`: 內容 metadata
- `seo_results`: SEO 處理結果（如果啟用）

### Playbook 2: `ig_publish_content`

**功能**：發布內容到 Instagram

**輸入參數**：
- `channel_config_id` (integer, 必需): Channel Config ID（由 site-hub 管理）
- `workspace_id` (string, 必需): Mindscape workspace ID
- `media_type` (string, 必需): 媒體類型（photo/reel/carousel）
  - ⚠️ **不支持 story**（Graph API 限制）
- `media_path` (string, 必需): 媒體文件路徑
- `caption` (string, 必需): 貼文標題/描述
- `hashtags` (array, 可選): Hashtags 列表
- `scheduled_publish_time` (string, 可選): 延遲發布時間（僅支持 photo，最多 6 個月後）
- `location_id` (string, 可選): 位置 ID
- `user_tags` (array, 可選): 用戶標籤列表

**工具調用**：
- `ig.ig_validate_media` - 驗證媒體文件格式和大小限制
- `ig.ig_publish_post` - 發布內容（photo/reel/carousel）

**輸出**：
- `published_post`: 發布的 post 信息（photo）
- `published_reel`: 發布的 reel 信息
- `published_carousel`: 發布的 carousel 信息
- `media_id`: 發布的媒體 ID
- `permalink`: 發布內容的永久連結
- `validation_result`: 媒體驗證結果

---

## 🔗 與 Site-Hub 的整合

### Token 獲取流程

```
1. Playbook 接收 channel_config_id
   ↓
2. 調用 site-hub Registry API 獲取 access_token
   ├─ 端點：GET /api/v1/channel_configs/{channel_config_id}
   ├─ 授權：使用 site-hub API token 或 workspace 綁定的 tenant_uuid
   └─ 權限檢查：驗證 workspace 是否有權限訪問該 channel_config_id
   ↓
3. 從 ChannelConfig.access_token 讀取 token（已加密）
   ↓
4. 使用 token 調用 IG Graph API
```

### App Secret 獲取流程

```
1. 需要 app_secret（用於 appsecret_proof）
   ↓
2. 從 Vault 獲取 app_secret
   ├─ 通過 Registry API：GET /api/v1/channel_configs/{id}/secret
   ├─ 或直接從 ChannelSecret.vault_uri 解析
   └─ 權限檢查：確保 workspace 有權限訪問該 secret
   ↓
3. 生成 app_secret_proof
   ├─ 計算方式：HMAC-SHA256(app_secret, access_token)
   └─ 添加到所有 Graph API 請求
```

### 權限校驗

**只校驗 channel_config_id 可用**：
- 不進行 OAuth 授權
- 不管理 Token 生命週期
- 只驗證 channel_config_id 是否存在且有效
- Token 過期時返回明確錯誤，提示用戶回到 site-hub 重新授權

---

## 📝 前置要求

### 必須在 Site-Hub 完成

1. **OAuth 授權**：
   - 在 site-hub UI 完成 Instagram OAuth 授權
   - 獲取 long-lived token（60 天，可自動刷新）

2. **Channel 綁定**：
   - 綁定 Instagram Business Account 到 ChannelConfig
   - 獲取 `channel_config_id`

3. **權限配置**：
   - 確保有必需的權限：
     - `instagram_basic`
     - `instagram_content_publish`
     - `instagram_manage_insights`
     - `pages_read_user_content`

### Playbook 使用前檢查

- ✅ `channel_config_id` 有效
- ✅ Token 未過期（由 site-hub 管理）
- ✅ Workspace 有權限訪問該 channel_config_id

---

## 🎯 使用範例

### 拉取所有內容

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "content_type": "all",
  "limit": 25
}
```

### 只拉取 posts 並觸發 SEO 處理

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "content_type": "posts",
  "media_type": "IMAGE",
  "limit": 50,
  "trigger_openseo": true
}
```

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

---

## ⚠️ 限制與注意事項

### 媒體發布限制

- **Photo**: JPEG/PNG, 最大 30MB, 支持延遲發布（最多 6 個月後）
  - ✅ **我們可以決定延遲發布排程**：通過 `scheduled_publish_time` 參數設置（ISO 8601 格式）
  - ⚠️ **Instagram Graph API 限制**：最多只能延遲 6 個月
  - 💡 **更靈活的排程**：如果需要超過 6 個月或更複雜的排程，可以在我們自己的系統中實現排程服務，在指定時間調用發布 API

- **Reel**: MP4/MOV, 3-90 秒, 最大 100MB, 不支持延遲發布（必須立即發布）
  - ❌ **Instagram Graph API 官方限制**：Reel 不支持 `scheduled_publish_time` 參數
  - 💡 **替代方案**：如果需要延遲發布 Reel，可以在我們自己的系統中實現排程服務，在指定時間調用發布 API

- **Carousel**: 支持多張圖片，每張限制同 Photo
  - ✅ **我們可以決定延遲發布排程**：通過 `scheduled_publish_time` 參數設置（最多 6 個月後）

- **Story**: ❌ **不支持發布**（Graph API 限制，只能拉取）

### API 配額

- **速率限制**：每個應用 10 請求/秒（per app）
- **429 錯誤處理**：實現指數退避（1s → 2s → 4s）
- **監控**：需要實現配額使用監控和 429 錯誤率監控

### Token 管理

- **Token 過期**：如果 token 過期，playbook 會返回錯誤，提示用戶回到 site-hub 重新授權
- **自動刷新**：long-lived token 由 site-hub 自動刷新（提前 7 天），playbook 無需處理

---

## 📚 相關文檔

- [IG Channel 串接實作計劃](../openseo/docs/IG_CHANNEL_IMPLEMENTATION_PLAN_2026-01-05.md)
- [Site-Hub Channel Binding API](../../../site-hub/site-hub-api/v1/channel_binding.py)
- [Instagram Token Manager](../../../site-hub/site-hub-api/v1/services/instagram_token_manager.py)
- [Instagram OAuth 路由](../../../site-hub/site-hub-api/v1/routers/instagram_oauth.py)

---

## 🚀 未來擴展

### Phase 2: IG Graph API 服務（local-core）

需要實作的工具：
- `ig.ig_fetch_posts` - 拉取 posts
- `ig.ig_fetch_reels` - 拉取 reels
- `ig.ig_fetch_stories` - 拉取 stories
- `ig.ig_validate_media` - 驗證媒體文件
- `ig.ig_publish_post` - 發布內容

### Phase 3: Webhook 處理

- 接收 site-hub 轉發的 IG Webhook
- 處理事件（新 post、新評論等）
- 更新本地數據
- 觸發相關 pipeline

---

**最後更新**: 2026-01-05
**維護者**: Mindscape AI 開發團隊

