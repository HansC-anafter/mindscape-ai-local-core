---
playbook_code: ig_vault_structure_manager
version: 1.0.0
name: IG Vault 結構管理
description: 管理 IG 貼文工作流的 Obsidian Vault 結構。支援初始化、驗證和內容掃描。
tags:
  - instagram
  - obsidian
  - vault
  - structure

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_vault_structure_tool

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 📁
---

# IG Vault 結構管理

## 目標

管理 IG 貼文內容工作流的標準 Obsidian Vault 資料夾結構。支援初始化、驗證和內容掃描。

## 功能說明

這個 Playbook 會：

1. **初始化結構**：為 IG 貼文工作流創建標準資料夾結構
2. **驗證結構**：檢查 vault 結構是否符合標準要求
3. **掃描內容**：掃描 vault 內容並生成貼文、系列和想法的索引

## 使用情境

- 為 IG 貼文工作流設置新的 Obsidian vault
- 驗證現有 vault 結構
- 為 vault 管理生成內容索引
- 確保資料夾結構合規

## 輸入

- `vault_path`: Obsidian Vault 路徑（必填）
- `action`: 要執行的動作 - "init"、"validate" 或 "scan"（預設："validate"）
- `create_missing`: 驗證時是否創建缺少的資料夾（預設：false）

## 輸出

- `structure_status`: 結構狀態（initialized、incomplete、valid 等）
- `is_valid`: vault 結構是否有效
- `created_folders`: 創建的資料夾清單（僅 init 動作）
- `missing_folders`: 缺少的資料夾清單
- `content_index`: 包含貼文、系列和想法的內容索引（scan 動作）
- `post_count`: 找到的 IG 貼文數量
- `series_count`: 找到的系列數量
- `idea_count`: 找到的想法數量

## 標準資料夾結構

- `10-Ideas`: 貼文想法和概念
- `20-Posts`: IG 貼文內容
- `30-Assets`: 貼文素材（圖片、影片）
- `40-Series`: 貼文系列組織
- `50-Playbooks`: Playbook 模板
- `60-Reviews`: 審查和反饋
- `70-Metrics`: 績效指標
- `90-Export`: 匯出包

## 步驟（概念性）

1. 初始化或驗證 vault 資料夾結構
2. 檢查缺少的必需資料夾
3. 掃描內容並生成索引（如果是 scan 動作）

## 備註

- 標準結構確保一致的組織方式
- 支援驗證期間自動創建資料夾
- 內容掃描提供 vault 內容概覽

