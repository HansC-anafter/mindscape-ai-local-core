---
playbook_code: ig_review_system
version: 1.0.0
name: IG 審查系統
description: 管理審查工作流，包括變更日誌追蹤、審查備註和決策日誌
tags:
  - instagram
  - review
  - workflow
  - collaboration

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_review_system_tool

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 👁️
---

# IG 審查系統

## 目標

管理審查工作流，包括版本變更日誌追蹤、審查備註、決策日誌和審查狀態管理。

## 功能說明

這個 Playbook 會：

1. **新增變更日誌**：新增版本變更日誌條目
2. **新增審查備註**：新增具有優先級和狀態的審查備註
3. **新增決策日誌**：新增包含理由的決策日誌
4. **更新審查備註狀態**：更新審查備註狀態
5. **取得摘要**：取得審查摘要

## 使用情境

- 追蹤貼文版本變更
- 管理審查備註和反饋
- 記錄決策和理由
- 追蹤審查狀態

## 輸入

- `action`: 要執行的動作 - "add_changelog"、"add_review_note"、"add_decision_log"、"update_review_note_status" 或 "get_summary"（必填）
- `vault_path`: Obsidian Vault 路徑（必填）
- `post_path`: 貼文檔案路徑（必填）
- `version`: 版本字串（add_changelog 動作需要）
- `changes`: 變更描述（add_changelog 動作需要）
- `author`: 作者名稱（選填）
- `reviewer`: 審查者名稱（add_review_note 動作需要）
- `note`: 審查備註內容（add_review_note 動作需要）
- `priority`: 優先級 - "high"、"medium" 或 "low"（預設：medium）
- `status`: 審查狀態 - "pending"、"addressed"、"resolved" 或 "rejected"（選填）
- `decision`: 決策描述（add_decision_log 動作需要）
- `rationale`: 決策理由（選填）
- `decision_maker`: 決策者名稱（選填）
- `note_index`: 審查備註索引（update_review_note_status 動作需要）
- `new_status`: 新狀態（update_review_note_status 動作需要）

## 輸出

- `frontmatter`: 包含審查資訊的更新 frontmatter
- `summary`: 審查摘要

## 審查狀態

- **pending**: 審查備註待處理
- **addressed**: 審查備註已處理
- **resolved**: 審查備註已解決
- **rejected**: 審查備註已拒絕

## 步驟（概念性）

1. 新增變更日誌、審查備註或決策日誌
2. 如果需要，更新審查備註狀態
3. 取得審查摘要

## 備註

- 支援審查備註的優先級
- 追蹤決策理由
- 在 frontmatter 中維護審查歷史

