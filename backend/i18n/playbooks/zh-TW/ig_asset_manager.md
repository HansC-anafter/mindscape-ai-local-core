---
playbook_code: ig_asset_manager
version: 1.0.0
name: IG 素材管理
description: 管理 IG 貼文素材，包含命名驗證、尺寸檢查和格式驗證
tags:
  - instagram
  - assets
  - validation
  - obsidian

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_asset_manager_tool

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

# IG 素材管理

## 目標

管理 IG 貼文素材（圖片、影片），包含命名規則驗證、尺寸檢查和格式驗證，支援不同貼文類型（post、carousel、reel、story）。

## 功能說明

這個 Playbook 會：

1. **掃描素材**：掃描貼文資料夾中的素材並提取元數據
2. **驗證素材**：根據 IG 規格驗證素材（尺寸、比例、格式）
3. **生成素材清單**：根據貼文類型生成所需素材清單

## 使用情境

- 發布 IG 貼文前驗證素材
- 檢查素材命名規範
- 為新貼文生成所需素材清單
- 驗證素材尺寸和檔案大小

## 輸入

- `post_folder`: 貼文資料夾路徑（相對於 vault）（必填）
- `vault_path`: Obsidian Vault 路徑（必填）
- `post_type`: 貼文類型 - "post"、"carousel"、"reel" 或 "story"（必填）

## 輸出

- `asset_list`: 包含元數據的素材清單，包含名稱、尺寸和驗證狀態
- `validation_results`: 每個素材的詳細驗證結果
- `missing_assets`: 缺少的必需素材清單
- `size_warnings`: 尺寸或檔案大小不正確的警告

## 步驟（概念性）

1. 掃描貼文資料夾中的素材以發現所有圖片/影片檔案
2. 根據指定貼文類型驗證素材是否符合 IG 規格
3. 根據貼文類型需求生成所需素材清單

## 素材規格

- **Post/Carousel**: 1080x1080 (1:1)，最大 8MB
- **Reel/Story**: 1080x1920 (9:16)，最大 100MB

## 備註

- 素材命名應遵循規範：`{post_slug}_{index}.{ext}`
- 支援多種貼文類型的驗證
- 提供非合規素材的詳細警告

