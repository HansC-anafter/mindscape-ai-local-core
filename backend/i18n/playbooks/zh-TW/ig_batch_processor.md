---
playbook_code: ig_batch_processor
version: 1.0.0
capability_code: instagram
name: IG 批量處理器
description: 管理多個貼文的批量處理，包括驗證、生成和匯出操作
tags:
  - instagram
  - batch
  - automation
  - processing

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_batch_processor_tool

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: ⚙️
---

# IG 批量處理器

## 目標

管理多個 IG 貼文的批量處理，包括驗證、匯出包生成、狀態更新和自訂操作。

## 功能說明

這個 Playbook 會：

1. **批量驗證**：一次驗證多個貼文
2. **批量生成匯出包**：為多個貼文生成匯出包
3. **批量更新狀態**：批量更新貼文狀態
4. **批量處理**：對多個貼文執行自訂操作

## 使用情境

- 發布前驗證多個貼文
- 為批量發布生成匯出包
- 批量更新貼文狀態
- 執行自訂批量操作

## 輸入

- `action`: 要執行的動作 - "batch_validate"、"batch_generate_export_packs"、"batch_update_status" 或 "batch_process"（必填）
- `vault_path`: Obsidian Vault 路徑（必填）
- `post_paths`: 貼文檔案路徑清單（相對於 vault）（必填）
- `strict_mode`: 如果為 True，所有必需欄位必須存在（預設：false）
- `output_folder`: 匯出包的輸出資料夾（選填）
- `new_status`: 要設置的新狀態（batch_update_status 動作需要）
- `operations`: 要執行的操作清單（batch_process 動作需要）
- `operation_config`: 操作的配置（選填）

## 輸出

- `result`: 批量處理結果，包含每個貼文的操作狀態

## 動作

1. **batch_validate**: 根據 frontmatter schema 驗證多個貼文
2. **batch_generate_export_packs**: 為多個貼文生成匯出包
3. **batch_update_status**: 批量更新多個貼文的狀態欄位
4. **batch_process**: 對多個貼文執行自訂操作

## 步驟（概念性）

1. 根據選擇的動作處理多個貼文
2. 為每個貼文執行操作
3. 收集並返回結果

## 備註

- 支援嚴格模式進行驗證
- 可以通過 batch_process 動作處理自訂操作
- 返回每個貼文的詳細結果

