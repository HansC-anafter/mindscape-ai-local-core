---
playbook_code: dataset_style_extraction
version: 1.0.0
capability_code: visual_lens
name: 資料集風格提取
description: 使用儲存的風格指紋和關鍵字/色彩映射，直接從資料集中提取 Visual Lens 風格，然後生成完整的 WebVisualLensSchema。
tags:
  - visual-lens
  - style-extraction
  - dataset
  - web-generation
kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - unsplash.extract_style_from_dataset
  - core_llm.structured_extract
  - visual_lens.visual_lens_create

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: false

entry_agent_type: consultant
icon: 🎨
---

# 資料集風格提取 - SOP

## 目標
從現有資料集中提取風格信號（關鍵字、色彩、風格特徵），合成 WebVisualLensSchema，並透過 Visual Lens API 儲存。

## 執行流程（高層級）
1) 使用 `unsplash.extract_style_from_dataset` 從資料集中提取風格資料（關鍵字 + 偏好作為輸入）。
2) 使用 `core_llm.structured_extract` 生成完整的 WebVisualLensSchema，確保所有陣列/欄位都已填入且與風格資料一致。
3) 使用 `visual_lens.visual_lens_create` 儲存 lens（工作區範圍）。

## 輸入（標準格式）
- `theme_keywords`（陣列，必填）
- `style_preferences`（陣列，選填）
- `lens_name`（字串，必填）
- `workspace_id`（字串，必填）

## 輸出
- `style_data`: 提取的風格信號
- `lens_data`: 生成的 Visual Lens schema
- `saved_lens`: 持久化的 lens 記錄

## 防護措施
- 生成的 schema 中不得有空陣列或 null 物件。
- 優先使用資料集衍生的色彩/主題；僅在缺少時才回退到偏好設定。
- 確保 color_palette 至少有 3 種色彩；required/forbidden 元素不得為空。
