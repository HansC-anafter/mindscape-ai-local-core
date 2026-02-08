# 設計模板

## 目的

設計或預覽帶有變數替換的郵件模板。

## 使用時機

- 用範例資料預覽模板
- 測試模板渲染
- 為 campaign 選擇模板

## 輸入

- **template_id**（必填）：要渲染的模板
- **variables**（選填）：要替換的變數
- **preview_mode**（選填）：使用範例資料

## 可用模板

- `default_digest`：含區塊的週報
- `default_announcement`：單一主題公告
- `default_promotion`：帶 CTA 的促銷
- `default_update`：產品/服務更新

## 使用範例

```yaml
inputs:
  template_id: "default_digest"
  preview_mode: true
  variables:
    brand_name: "我的公司"
    headline: "每週更新"
```

## 相關 Playbook

- `nl_create_campaign`：在 campaign 使用模板
- `nl_generate_content`：為模板生成內容
