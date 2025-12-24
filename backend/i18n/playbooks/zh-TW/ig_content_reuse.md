---
playbook_code: ig_content_reuse
version: 1.0.0
name: IG 內容重用
description: 管理不同 IG 格式之間的內容轉換和重用
tags:
  - instagram
  - content-reuse
  - transformation
  - formats

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_content_reuse_tool

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: ♻️
capability_code: instagram
---

# IG 內容重用

## 目標

在不同 IG 格式之間轉換和重用內容，包括文章轉輪播、輪播轉 Reel 和 Reel 轉限時動態。

## 功能說明

這個 Playbook 會：

1. **文章轉輪播**：將文章內容轉換為輪播格式
2. **輪播轉 Reel**：將輪播貼文轉換為 Reel 格式
3. **Reel 轉限時動態**：將 Reel 內容轉換為限時動態格式

## 使用情境

- 將文章內容重新用於輪播貼文
- 將輪播貼文轉換為 Reel 影片
- 將 Reel 內容轉換為限時動態系列
- 跨格式最大化內容價值

## 輸入

- `action`: 要執行的動作 - "article_to_carousel"、"carousel_to_reel" 或 "reel_to_stories"（必填）
- `vault_path`: Obsidian Vault 路徑（必填）
- `source_post_path`: 來源貼文路徑（article_to_carousel 需要）
- `carousel_posts`: 輪播貼文路徑清單（carousel_to_reel 需要）
- `source_reel_path`: 來源 Reel 貼文路徑（reel_to_stories 需要）
- `target_folder`: 生成貼文的目標資料夾（必填）
- `carousel_slides`: 輪播投影片數量（預設：7）
- `slide_structure`: 自訂投影片結構配置（選填）
- `reel_duration`: Reel 持續時間（秒）（選填）
- `story_count`: 要創建的限時動態數量（預設：3）

## 輸出

- `result`: 轉換結果，包含創建的貼文資訊

## 轉換類型

1. **article_to_carousel**: 將文章拆分為多個輪播投影片
2. **carousel_to_reel**: 將輪播貼文組合為 Reel 腳本
3. **reel_to_stories**: 將 Reel 拆分為限時動態系列

## 步驟（概念性）

1. 從 vault 讀取來源內容
2. 根據目標格式轉換內容
3. 在目標資料夾中創建新貼文

## 備註

- 支援輪播的自訂投影片結構
- 可以指定 Reel 持續時間和限時動態數量
- 跨格式維護內容一致性

