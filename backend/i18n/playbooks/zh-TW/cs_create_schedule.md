# 建立排程

## 目的

建立新的跨平台內容排程項目。支援 IG、網站、電子報和 Canva 平台。

## 使用時機

- 排程未來的內容發布
- 設定自動化發文工作流程
- 提前規劃內容日曆

## 輸入

- **content_ref**（必填）：內容資產引用
  - `pack`：來源 pack（如 "ig"、"web_generation"）
  - `asset_id`：資產識別碼
  - `version`：版本（"latest" 或特定版本）
  - `playbook_to_trigger`：分發時要觸發的 playbook
- **target_platform**（必填）：目標平台（ig、web、newsletter、canva）
- **scheduled_time**（必填）：排程發布時間（ISO 格式）
- **timezone**（選填）：時區 - 預設："Asia/Taipei"
- **retry_policy**（選填）：重試配置

## 流程

1. **驗證輸入**：檢查 content_ref 和平台
2. **建立排程項目**：儲存至本地帳本
3. **註冊觸發器**：設定時間觸發器

## 輸出

- **schedule_id**：排程的唯一識別碼
- **schedule_item**：完整排程項目詳情

## 使用範例

```yaml
inputs:
  content_ref:
    pack: "ig"
    asset_id: "post_20260121_001"
    version: "latest"
    playbook_to_trigger: "ig_publish_content"
  target_platform: "ig"
  scheduled_time: "2026-01-22T09:00:00Z"
  timezone: "Asia/Taipei"
  retry_policy:
    max_retries: 3
    retry_interval_sec: 300
```

## 相關 Playbook

- `cs_batch_schedule`：批次排程多個項目
- `cs_cancel_schedule`：取消待處理排程
- `cs_view_calendar`：檢視排程日曆
