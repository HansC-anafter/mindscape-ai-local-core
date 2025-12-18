---
playbook_code: ig_export_pack_generator
version: 1.0.0
name: IG 匯出包生成器
description: 為 IG 貼文生成完整的匯出包，包括 post.md、hashtags.txt、CTA 變體和檢查清單
tags:
  - instagram
  - export
  - publishing
  - checklist

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_export_pack_generator_tool
  - ig_hashtag_manager_tool
  - ig_asset_manager_tool
  - obsidian_read_note

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 📦
---

# IG 匯出包生成器

## 目標

為 IG 貼文生成完整的匯出包，包括貼文 markdown、hashtag 文字檔案、CTA 變體和發布前檢查清單。

## 功能說明

這個 Playbook 會：

1. **讀取貼文**：從 Obsidian vault 讀取貼文內容和 frontmatter
2. **取得 Hashtag**：生成或使用提供的 hashtag
3. **掃描素材**：如果啟用，掃描貼文素材
4. **生成匯出包**：創建包含所有必需檔案的完整匯出包

## 使用情境

- 準備貼文發布
- 為批量發布生成匯出包
- 創建發布前檢查清單
- 打包包含所有必需素材的貼文

## 輸入

- `post_folder`: 貼文資料夾路徑（相對於 vault）（必填）
- `post_path`: 貼文 markdown 檔案路徑（相對於 vault）（必填）
- `vault_path`: Obsidian Vault 路徑（必填）
- `hashtags`: Hashtag 清單（如果未提供，將生成）
- `cta_variants`: CTA 變體清單（選填）
- `include_assets`: 是否在檢查清單中包含素材（預設：true）

## 輸出

- `export_pack_path`: 匯出包資料夾路徑
- `files_generated`: 生成的檔案清單
- `export_pack`: 匯出包內容

## 匯出包內容

1. **post.md**: Markdown 格式的貼文內容
2. **hashtags.txt**: Hashtag 清單
3. **cta_variants.txt**: CTA 變體
4. **checklist.md**: 發布前檢查清單

## 步驟（概念性）

1. 讀取貼文內容和 frontmatter
2. 生成或檢索 hashtag
3. 如果啟用，掃描素材
4. 生成包含所有檔案的匯出包

## 備註

- 如果未提供，自動生成 hashtag
- 如果掃描素材，包含素材檢查清單
- 創建準備發布的完整匯出包

