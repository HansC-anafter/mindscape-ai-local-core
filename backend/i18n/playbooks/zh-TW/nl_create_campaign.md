# 建立 Campaign

## 目的

建立新的電子報 campaign，包含主旨、內容和選擇性排程。

## 使用時機

- 開始新的電子報行銷活動
- 設定自動化電子報
- 建立排程公告

## 輸入

- **name**（必填）：Campaign 名稱（內部追蹤用）
- **subject**（必填）：郵件主旨
- **preview_text**（選填）：收件匣預覽文字
- **template_id**（選填）：使用的模板
- **content**（選填）：Campaign 內容（標題、內文、CTA）
- **schedule_time**（選填）：排程寄送時間（ISO 格式）

## 輸出

- **campaign_id**：Campaign 的唯一識別碼
- **campaign**：完整的 campaign 資料

## 使用範例

```yaml
inputs:
  name: "一月週報"
  subject: "您的週報更新 - 2026/01/21"
  preview_text: "本週重點與新聞"
  template_id: "default_digest"
  content:
    headline: "歡迎閱讀本週週報"
    intro: "以下是您需要知道的..."
    cta_text: "閱讀更多"
    cta_url: "https://example.com/blog"
```

## 相關 Playbook

- `nl_design_template`：設計郵件模板
- `nl_generate_content`：用 AI 生成內容
- `nl_send_campaign`：寄送 campaign
