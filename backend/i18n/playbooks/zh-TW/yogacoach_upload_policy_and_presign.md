---
playbook_code: yogacoach_upload_policy_and_presign
version: 1.0.0
locale: zh-TW
name: "上傳策略與預簽名"
description: "根據上傳方式生成策略和預簽名 URL，設置 TTL，生成隱私回執"
capability_code: yogacoach
tags:
  - yoga
  - upload
  - privacy
---

# Playbook: 上傳策略與預簽名

**Playbook Code**: `yogacoach_upload_policy_and_presign`
**版本**: 1.0.0
**用途**: 根據上傳方式生成策略和預簽名 URL，設置 TTL，生成隱私回執

---

## 輸入資料

**注意**：`tenant_id`、`session_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "upload_method": "backend_video",
  "file_metadata": {
    "filename": "yoga_session.mp4",
    "content_type": "video/mp4",
    "size_bytes": 12345678
  },
  "ttl_seconds": 3600,
  "callback_webhook": "https://example.com/webhook/upload-complete"
}
```

## 輸出資料

```json
{
  "upload_config": {
    "method": "backend_video",
    "endpoint": "https://storage.example.com/upload",
    "http_method": "PUT",
    "headers": {
      "X-Session-ID": "session-abc123",
      "X-Idempotency-Key": "idemp-xyz789"
    },
    "fields": {
      "key": "temp/session-abc123/video.mp4",
      "acl": "private"
    }
  },
  "ttl_seconds": 3600,
  "privacy_receipt_id": "PR-xxxxx",
  "callback_webhook": "https://example.com/webhook/upload-complete",
  "expected_payload": "video"
}
```

## 執行步驟

1. **獲取會話資訊**
   - 從 `session_id`（由 runtime 提供）獲取會話資訊
   - 驗證會話存在且有效

2. **生成上傳策略**
   - 根據 `upload_method` 生成對應的上傳策略
   - `frontend_keypoints`: 前端直接上傳 keypoints 數據
   - `backend_video`: 生成預簽名 URL 供後端上傳視頻

3. **生成預簽名 URL**（如需要）
   - 如果 `upload_method` 為 `backend_video`，生成預簽名 URL
   - 設置 TTL（短期暫存，不永久保存原片）
   - 配置對象生命週期規則（自動刪除）

4. **生成隱私回執**
   - 生成隱私回執，證明"不落地保存"
   - 記錄對象 key、過期時間、生命週期策略
   - 生成審計日誌

5. **配置回調 webhook**
   - 設置上傳完成後的回調 webhook
   - 配置回調參數

## 能力依賴

- `yogacoach.upload_policy_generator`: 上傳策略生成
- `yogacoach.storage_manager`: 存儲管理
- `yogacoach.privacy_receipt_manager`: 隱私回執管理

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 隱私保護機制

- ✅ S3/GCS Object Lifecycle Rule（TTL 自動刪除）
- ✅ Server-side Audit Log（記錄刪除排程與到期時間）
- ✅ Receipt 包含 `object_key`（加密）、`expires_at`、`lifecycle_policy_id`
- ❌ 不使用 "hash" 作為刪除證明（hash 只能證明生成，無法證明刪除）

## 錯誤處理

- 會話不存在：返回錯誤，記錄日誌
- 上傳方式無效：返回錯誤，僅支援 frontend_keypoints/backend_video
- 存儲配置錯誤：返回錯誤，記錄日誌

