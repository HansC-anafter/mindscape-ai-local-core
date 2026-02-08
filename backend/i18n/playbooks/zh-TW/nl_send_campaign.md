# 寄送 Campaign

## 目的

透過設定的 ESP（Email Service Provider）將電子報 campaign 寄送給訂閱者。

## 使用時機

- Campaign 準備好要寄送
- 正式寄送前測試 campaign
- 被 content_scheduler 觸發

## 輸入

- **campaign_id**（必填）：要寄送的 campaign
- **subscriber_list_id**（選填）：目標訂閱者列表
- **test_mode**（選填）：僅寄送給測試信箱
- **test_emails**（選填）：測試信箱地址

## 輸出

- **sent_count**：已寄送郵件數
- **failed_count**：寄送失敗數
- **status**：寄送後的 campaign 狀態

## ESP 整合

支援的提供者（透過 `NEWSLETTER_ESP_PROVIDER` 設定）：
- `simulation`：本地測試（不實際寄送）
- `resend`：Resend.com API
- `sendgrid`：SendGrid API

## 使用範例

```yaml
# 測試寄送
inputs:
  campaign_id: "abc123"
  test_mode: true
  test_emails:
    - "test@example.com"

# 正式寄送
inputs:
  campaign_id: "abc123"
  subscriber_list_id: "main_list"
```

## 相關 Playbook

- `nl_create_campaign`：建立 campaign
- `nl_analyze_metrics`：分析結果
