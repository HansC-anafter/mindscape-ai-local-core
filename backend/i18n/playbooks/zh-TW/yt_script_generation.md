---
playbook_code: yt_script_generation
version: 1.0.0
name: YT 影片腳本生成
description: 從內容生成 YouTube 影片腳本，針對 YT 格式優化（時間點、結構、重點標註等）
tags:
  - youtube
  - video
  - script
  - content-creation

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.generate

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 🎬
---

# YT 影片腳本生成

## 目標

從來源內容（如 OCR 結果、文章等）生成 YouTube 影片腳本，針對 YT 平台特性進行優化，包含時間點標註、結構化內容和重點標註。

## 功能說明

這個 Playbook 會：

1. **分析來源內容**：提取關鍵主題和重點
2. **規劃腳本結構**：設計開場、主體、結尾的結構
3. **生成腳本內容**：針對指定時長生成完整的影片腳本
4. **標註時間點**：為重要段落標註時間點（如需要）

## 使用情境

- 將長篇文章轉換為 YT 影片腳本
- 從研究報告生成影片內容
- 將筆記轉換為 YT 腳本
- 內容創作的腳本批量生成

## 輸入

- `source_content`: 來源內容（必填）
- `duration_minutes`: 影片時長（分鐘，預設 5）
- `script_type`: 腳本類型（educational, tutorial, review, storytelling, interview）
- `tone`: 語氣風格（engaging, professional, casual, energetic, calm）
- `include_timestamps`: 是否包含時間點標註（預設 true）

## 輸出

- `script`: 完整的影片腳本（結構化物件）
- `script_markdown`: Markdown 格式的腳本（可讀性較好）

## 步驟（概念性）

1. 分析來源內容，提取關鍵主題
2. 規劃腳本結構（開場、主體、結尾）
3. 生成腳本內容，包含時間點標註
4. 優化內容以符合 YT 平台特性

## 範例

**輸入**：
- 來源內容：一篇關於 AI 技術的文章
- 時長：5 分鐘
- 腳本類型：educational

**輸出**：
- 完整的 YT 影片腳本，包含時間點和結構化內容

## 注意事項

- 時長控制：生成的腳本時長是估算值，實際錄製可能會有差異
- 語速考量：腳本長度基於一般語速（約 150-160 字/分鐘）
- 視覺元素：腳本不包含視覺元素，但可以建議適合的畫面
- 版權考量：如果來源內容有版權限制，請注意使用範圍

