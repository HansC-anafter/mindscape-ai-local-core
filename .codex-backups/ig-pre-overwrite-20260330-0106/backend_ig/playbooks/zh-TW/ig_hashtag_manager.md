---
playbook_code: ig_hashtag_manager
version: 1.0.0
capability_code: instagram
name: IG Hashtag 管理
description: 管理 hashtag 群組，並根據意圖、受眾和地區為 IG 貼文組合 hashtag
tags:
  - instagram
  - hashtags
  - social-media
  - marketing

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_hashtag_manager_tool

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: #
---

# IG Hashtag 管理

## 目標

管理 hashtag 群組，並根據貼文意圖、目標受眾和地區智能組合 IG 貼文的 hashtag。支援 hashtag 封鎖和合規檢查。

## 功能說明

這個 Playbook 會：

1. **載入 Hashtag 群組**：載入預定義的 hashtag 群組（品牌固定、主題、活動）
2. **組合 Hashtag**：根據意圖、受眾和地區組合 hashtag
3. **檢查封鎖**：檢查 hashtag 是否在封鎖清單中

## 使用情境

- 為 IG 貼文生成 hashtag 建議
- 從多個群組組合 hashtag
- 檢查 hashtag 合規性和封鎖
- 管理活動的 hashtag 群組

## 輸入

- `intent`: 貼文意圖 - "教育"、"引流"、"轉換" 或 "品牌"（選填）
- `audience`: 目標受眾（選填）
- `region`: 地區（選填）
- `hashtag_count`: 所需 hashtag 數量 - 15、25 或 30（預設：25）
- `action`: 要執行的動作 - "recommend"、"combine" 或 "check_blocked"（預設："recommend"）
- `hashtags`: 要檢查的 hashtag 清單（check_blocked 動作需要）

## 輸出

- `hashtag_groups`: Hashtag 群組（品牌固定、主題、活動）
- `recommended_hashtags`: 建議的 hashtag 清單
- `blocked_hashtags`: 找到的封鎖 hashtag
- `hashtag_groups_used`: 組合中使用的 hashtag 群組
- `total_count`: 總 hashtag 數量

## 步驟（概念性）

1. 從配置載入 hashtag 群組
2. 根據意圖、受眾和地區組合 hashtag
3. 如果提供，檢查封鎖的 hashtag

## 備註

- 支援多種 hashtag 數量選項（15、25、30）
- 自動包含品牌固定 hashtag
- 可以檢查 hashtag 對封鎖清單的合規性

