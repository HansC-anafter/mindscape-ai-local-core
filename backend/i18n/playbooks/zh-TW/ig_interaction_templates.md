---
playbook_code: ig_interaction_templates
version: 1.0.0
name: IG 互動模板
description: 管理互動模板，包括常見留言回覆、DM 腳本和語調切換
tags:
  - instagram
  - templates
  - interaction
  - automation

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_interaction_templates_tool

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 💬
capability_code: instagram
---

# IG 互動模板

## 目標

管理常見留言回覆、DM 腳本和限時動態回覆的互動模板，支援語調切換和變數渲染。

## 功能說明

這個 Playbook 會：

1. **創建模板**：創建新的互動模板
2. **取得模板**：根據 ID 檢索模板
3. **列出模板**：使用篩選列出模板
4. **渲染模板**：使用變數渲染模板
5. **建議模板**：根據上下文建議模板
6. **切換語調**：切換模板語調
7. **更新模板**：更新現有模板

## 使用情境

- 創建可重用的留言回覆模板
- 管理常見情境的 DM 腳本
- 為不同上下文切換模板語調
- 自動化互動回應

## 輸入

- `action`: 要執行的動作 - "create"、"get"、"list"、"render"、"suggest"、"switch_tone" 或 "update"（必填）
- `vault_path`: Obsidian Vault 路徑（必填）
- `template_id`: 模板識別碼（get、render、switch_tone、update 需要）
- `template_type`: 模板類型 - "comment_reply"、"dm_script" 或 "story_reply"（選填）
- `content`: 包含 {{variable}} 佔位符的模板內容（create 需要）
- `tone`: 語調 - "friendly"、"professional"、"casual" 或 "formal"（選填）
- `category`: 類別（例如 'greeting'、'product_inquiry'、'complaint'）（選填）
- `tags`: 用於分類的標籤清單（選填）
- `variables`: 模板中使用的變數名稱清單（選填）
- `render_variables`: 用於渲染的變數值字典（render 需要）
- `context`: 模板建議的上下文描述（suggest 需要）
- `new_tone`: switch_tone 動作的新語調（switch_tone 需要）
- `updates`: 要更新的欄位字典（update 需要）

## 輸出

- `template`: 模板資訊
- `templates`: 模板清單
- `rendered_content`: 渲染的模板內容
- `suggested_template`: 根據上下文建議的模板

## 模板類型

- **comment_reply**: 留言回應模板
- **dm_script**: 私訊腳本模板
- **story_reply**: 限時動態回應模板

## 步驟（概念性）

1. 創建、檢索或列出模板
2. 如果需要，使用變數渲染模板
3. 根據需要切換語調或更新模板

## 備註

- 支援模板中的變數佔位符
- 可以根據上下文建議模板
- 支援不同情境的語調切換

