---
playbook_code: ig_template_engine
version: 1.0.0
capability_code: instagram
name: IG 模板引擎
description: 應用模板生成多個具有不同語調和 CTA 的 IG 貼文變體
tags:
  - instagram
  - templates
  - content-generation
  - variants

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_template_engine_tool

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 📝
---

# IG 模板引擎

## 目標

應用模板從來源內容生成多個具有不同風格語調和 CTA（行動呼籲）的 IG 貼文變體。

## 功能說明

這個 Playbook 會：

1. **載入模板**：根據類型、風格語調和目的載入模板
2. **生成貼文**：生成多個具有不同 CTA 的貼文變體

## 使用情境

- 為 A/B 測試生成多個貼文變體
- 將品牌模板應用到內容
- 創建具有不同 CTA 的貼文
- 使用預定義模板轉換內容

## 輸入

- `template_type`: 模板類型 - "carousel"、"reel" 或 "story"（必填）
- `style_tone`: 風格語調 - "high_brand"、"friendly"、"coach" 或 "sponsored"（預設："friendly"）
- `purpose`: 貼文目的 - "save"、"comment"、"dm" 或 "share"（預設："save"）
- `source_content`: 要轉換的來源內容（必填）
- `generate_variants`: 是否生成多個具有不同 CTA 的變體（預設：true）

## 輸出

- `generated_posts`: 生成的 IG 貼文變體
- `template_applied`: 應用的模板資訊

## 模板類型

- **Carousel**: 多圖片貼文模板
- **Reel**: 影片貼文模板
- **Story**: 限時動態貼文模板

## 風格語調

- **high_brand**: 高品牌知名度語調
- **friendly**: 友好和親近的語調
- **coach**: 教練和教育性語調
- **sponsored**: 贊助內容語調

## CTA 目的

- **save**: 鼓勵儲存貼文
- **comment**: 鼓勵留言
- **dm**: 鼓勵私訊
- **share**: 鼓勵分享

## 步驟（概念性）

1. 根據類型、語調和目的載入模板
2. 將模板應用到來源內容
3. 如果啟用，生成多個具有不同 CTA 的變體

## 備註

- 支援多種模板類型和風格語調
- 可以生成多個變體進行測試
- 模板包含 CTA 變體

