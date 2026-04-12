---
playbook_code: ig_frontmatter_validator
version: 1.0.0
capability_code: instagram
name: IG Frontmatter 驗證
description: 根據統一 Frontmatter Schema v2.0.0 驗證貼文 frontmatter 並計算就緒分數
tags:
  - instagram
  - frontmatter
  - validation
  - schema

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_frontmatter_validator_tool
  - obsidian_read_note

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 📋
---

# IG Frontmatter 驗證

## 目標

根據統一 Frontmatter Schema v2.0.0 驗證貼文 frontmatter 並計算就緒分數，以評估貼文發布就緒度。

## 功能說明

這個 Playbook 會：

1. **讀取貼文**：從 Obsidian vault 讀取貼文檔案
2. **驗證 Frontmatter**：根據 schema 驗證 frontmatter 並計算就緒分數

## 使用情境

- 發布前驗證 frontmatter
- 計算貼文就緒分數
- 識別缺少的必需欄位
- 確保 schema 合規

## 輸入

- `post_path`: 貼文 Markdown 檔案路徑（相對於 vault）（選填）
- `vault_path`: Obsidian Vault 路徑（如果提供 post_path 則必填）
- `frontmatter`: 要驗證的 frontmatter 字典（post_path 的替代方案）
- `strict_mode`: 嚴格模式 - 所有必需欄位必須存在（預設：false）
- `domain`: 預期領域 - "ig"、"wp"、"seo"、"book"、"brand"、"ops" 或 "blog"（選填）

## 輸出

- `is_valid`: frontmatter 是否有效
- `readiness_score`: 就緒分數（0-100）
- `missing_fields`: 缺少的必需欄位清單
- `warnings`: 警告清單（例如，v1.0 schema 檢測）
- `errors`: 驗證錯誤清單

## 就緒分數

就緒分數（0-100）表示貼文 frontmatter 的完整程度：
- 100：所有必需和建議欄位都存在
- 80-99：所有必需欄位都存在，缺少一些建議欄位
- 60-79：大多數必需欄位都存在
- 低於 60：缺少關鍵必需欄位

## 步驟（概念性）

1. 從 vault 讀取貼文檔案或使用提供的 frontmatter
2. 根據統一 Frontmatter Schema v2.0.0 驗證
3. 根據欄位完整性計算就緒分數

## 備註

- 支援嚴格模式進行完整驗證
- 檢測 schema 版本並提供警告
- 可以直接驗證 frontmatter 或從檔案驗證

