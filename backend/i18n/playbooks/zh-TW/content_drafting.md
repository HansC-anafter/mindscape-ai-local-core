---
playbook_code: content_drafting
version: 1.0.0
capability_code: content
name: 內容／文案起稿
description: 幫助用戶起草文案、文章、貼文或募資頁內容，包括結構、重點段落和語氣風格
tags:
  - writing
  - content
  - copywriting
  - marketing

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: ✍️
---

# 內容／文案起稿 - SOP

## 目標
幫助用戶起草文案、文章、貼文或募資頁內容，包括結構、重點段落和建議的語氣風格。

## 執行步驟

### 階段 1: 理解需求
- 詢問內容的目標受眾和目的
- 了解內容的類型和格式要求
- 收集關鍵信息和要點

### 階段 2: 結構設計
- 設計內容的整體架構（開頭、主體、結尾）
- 規劃每個區塊的重點和功能
- 確定敘事邏輯和流程

### 階段 3: 內容起草
- 為每個區塊起草具體內容
- 確保內容符合目標受眾的語言習慣
- 保持一致的語氣和風格

### 階段 4: 優化建議
- 提供語氣和風格的調整建議
- 建議可以加強的重點段落
- 提供潤飾和優化方向

## 個性化調整

根據用戶的 Mindscape Profile：
- **角色**: 如果是「創業者」，強調說服力和 ROI 呈現
- **偏好語氣**: 如果偏好「直白」，減少修飾和客套話
- **詳細程度**: 如果偏好「high」，提供更多技術細節和案例

## 與長期意圖的銜接

如果用戶有相關的 Active Intent（如「完成募資頁內容」），在回應中明確提及：
> "因為你正在推進「完成募資頁內容」，我會建議你..."

### 階段 5: 文件生成與保存

#### 步驟 5.1: 保存草稿內容
**必須**使用 `sandbox.write_file` 工具保存起草的內容（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `draft_content.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的草稿內容，包含所有區塊和段落
- 格式: Markdown 格式

#### 步驟 5.2: 保存內容大綱（如適用）
如果生成了內容大綱，**必須**使用 `sandbox.write_file` 工具保存（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `outline.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 內容結構和大綱，包含各區塊的重點和功能
- 格式: Markdown 格式

#### 步驟 5.3: 保存優化建議（如適用）
如果提供了優化建議，**必須**使用 `sandbox.write_file` 工具保存（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `optimization_suggestions.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 語氣和風格調整建議、可加強的重點段落、潤飾和優化方向
- 格式: Markdown 格式

## 成功標準
- 內容結構清晰完整
- 語氣風格符合目標受眾
- 用戶獲得可用的草稿和優化建議
- 所有生成的內容已保存到文件供後續參考

