---
playbook_code: ig_post_generation
version: 1.0.0
name: IG 貼文生成
description: 從內容生成 Instagram 貼文，針對 IG 平台特性優化（字數限制、hashtag、語氣等）
tags:
  - social-media
  - instagram
  - content-creation
  - marketing

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.analyze
  - core_llm.generate

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 📱
---

# IG 貼文生成

## 目標

從來源內容（如 OCR 文字、文章、筆記等）生成多篇 Instagram 貼文，針對 IG 平台特性進行優化，包括字數限制、hashtag 使用、語氣調整等。

## 功能說明

這個 Playbook 會：

1. **分析內容**：從來源內容中提取關鍵主題和要點
2. **生成貼文**：根據主題生成多篇符合 IG 格式的貼文
3. **優化格式**：自動添加 hashtag、調整語氣、符合字數限制

## 使用情境

- 將長篇文章轉換為多篇 IG 貼文
- 從研究報告生成社群媒體內容
- 將筆記轉換為 IG 內容
- 內容行銷的貼文批量生成

## 輸入

- `source_content`: 來源內容（必填）
- `post_count`: 要生成的貼文數量（預設 5 篇）

## 輸出

- `ig_posts`: 生成的 IG 貼文列表，每篇包含：
  - `text`: 貼文文字內容
  - `hashtags`: 相關 hashtag 列表

## 步驟（概念性）

1. 分析來源內容，提取關鍵主題
2. 根據主題生成指定數量的 IG 貼文
3. 為每篇貼文添加適當的 hashtag
4. 優化文字以符合 IG 平台特性

## 範例

**輸入**：
- 來源內容：一篇關於 AI 技術的文章
- 貼文數量：5

**輸出**：
- 5 篇 IG 貼文，每篇包含文字和 hashtag

## 注意事項

- IG 貼文建議字數：2200 字以內
- 會自動添加相關 hashtag
- 生成的內容可能需要人工審核和調整
- 支援多語言內容生成

