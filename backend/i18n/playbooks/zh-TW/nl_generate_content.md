# 生成內容

## 目的

根據主題和風格偏好使用 AI 生成電子報內容。

## 使用時機

- 為新 campaign 建立內容
- 從來源內容生成週報
- 起草公告或更新

## 輸入

- **topic**（必填）：內容的主題
- **content_type**（選填）：內容類型（digest、announcement、promotion、update）
- **tone**（選填）：寫作語氣（formal、casual、friendly、professional）
- **source_content_refs**（選填）：其他 pack 的來源內容引用

## 輸出

- **content**：包含標題、前言、內文、CTA 的生成內容結構

## 使用範例

```yaml
inputs:
  topic: "AI 產品更新"
  content_type: "digest"
  tone: "professional"
  source_content_refs:
    - pack: "content"
      asset_id: "blog_post_123"
```

## 相關 Playbook

- `nl_create_campaign`：使用生成的內容
- `nl_design_template`：用模板預覽
