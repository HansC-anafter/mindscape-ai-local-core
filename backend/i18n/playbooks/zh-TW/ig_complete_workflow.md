---
playbook_code: ig_complete_workflow
version: 1.0.0
name: IG 完整工作流
description: 編排多個 playbook 以執行端到端工作流
tags:
  - instagram
  - workflow
  - orchestration
  - automation

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_complete_workflow_tool

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 🔄
capability_code: instagram
---

# IG 完整工作流

## 目標

編排多個 playbook 以執行 IG 貼文創建、審查和發布的端到端工作流。

## 功能說明

這個 Playbook 會：

1. **執行工作流**：執行具有多個步驟的預定義工作流
2. **創建貼文工作流**：遵循完整工作流創建新貼文
3. **審查工作流**：為現有貼文執行審查工作流

## 使用情境

- 執行完整的貼文創建工作流
- 編排多個 playbook 的順序執行
- 自動化端到端貼文發布流程
- 管理貼文審查工作流

## 輸入

- `action`: 要執行的動作 - "execute_workflow"、"create_post_workflow" 或 "review_workflow"（必填）
- `vault_path`: Obsidian Vault 路徑（必填）
- `workflow_name`: 工作流名稱（execute_workflow 動作需要）
- `workflow_steps`: 工作流步驟清單（execute_workflow 動作需要）
- `initial_context`: 初始上下文變數（選填）
- `post_content`: 貼文內容（create_post_workflow 動作需要）
- `post_metadata`: 貼文元數據/frontmatter（create_post_workflow 動作需要）
- `target_folder`: 貼文的目標資料夾（預設：20-Posts）
- `post_path`: 貼文檔案路徑（review_workflow 動作需要）
- `review_notes`: 審查備註清單（選填）

## 輸出

- `result`: 工作流執行結果，包含步驟結果和最終上下文

## 工作流動作

1. **execute_workflow**: 執行具有多個步驟的預定義工作流
2. **create_post_workflow**: 遵循完整工作流創建新貼文
3. **review_workflow**: 為現有貼文執行審查工作流

## 步驟（概念性）

1. 根據選擇的動作執行工作流
2. 按順序執行工作流步驟
3. 收集結果並返回最終上下文

## 備註

- 支援自訂工作流定義
- 可以編排多個 playbook
- 在工作流步驟之間維護上下文

