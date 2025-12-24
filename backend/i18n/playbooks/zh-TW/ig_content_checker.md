---
playbook_code: ig_content_checker
version: 1.0.0
name: IG 內容檢查
description: 檢查 IG 貼文內容的合規問題，包括醫療/投資聲明、版權、個人資料和品牌調性
tags:
  - instagram
  - compliance
  - content-safety
  - validation

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_content_checker_tool
  - obsidian_read_note

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: ✅
capability_code: instagram
---

# IG 內容檢查

## 目標

檢查 IG 貼文內容的合規問題，包括醫療/投資聲明、版權侵權、個人資料暴露和品牌調性違規。

## 功能說明

這個 Playbook 會：

1. **讀取貼文**：從 Obsidian vault 讀取貼文內容或使用提供的內容
2. **檢查內容**：對內容執行全面的合規檢查

## 使用情境

- 發布前內容合規檢查
- 識別潛在法律風險
- 確保品牌調性一致性
- 檢測個人資料暴露

## 輸入

- `content`: 要檢查的貼文內容文字（如果提供 post_path 則選填）
- `post_path`: 貼文 Markdown 檔案路徑（相對於 vault，如果提供 content 則選填）
- `vault_path`: Obsidian Vault 路徑（如果提供 post_path 則必填）
- `frontmatter`: 貼文 frontmatter（選填）

## 輸出

- `risk_flags`: 找到的風險標記（醫療、投資、侵權、個資）
- `warnings`: 警告清單
- `checks`: 每個類別的詳細檢查結果
- `is_safe`: 內容是否安全（無風險標記）

## 檢查類別

1. **醫療聲明**：檢測醫療治療聲明和健康相關關鍵字
2. **投資聲明**：檢測投資建議和財務承諾
3. **版權**：檢測版權相關關鍵字和潛在侵權
4. **個人資料**：檢測個人資訊模式（電話、電子郵件、身份證）
5. **品牌調性**：檢查負面品牌調性關鍵字

## 步驟（概念性）

1. 從 vault 讀取貼文內容或使用提供的內容
2. 在所有類別中執行合規檢查
3. 生成風險標記和警告

## 備註

- 為每個風險類別提供詳細警告
- 可以直接檢查內容或從 Obsidian vault 檢查
- 支援內容字串和檔案路徑輸入

