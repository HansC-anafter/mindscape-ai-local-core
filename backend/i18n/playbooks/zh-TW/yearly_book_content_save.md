---
playbook_code: yearly_book_content_save
version: 1.0.0
capability_code: obsidian_book
name: 年度書籍內容儲存
description: 將外部內容（OCR 結果、生成的貼文、腳本等）儲存到年度書籍中
tags:
  - journal
  - content-save
  - yearly-book
  - storage

kind: system_tool
interaction_mode:
  - silent
visible_in:
  - workspace_tools_panel
  - console_only

required_tools:
  - yearly_book.save_external_content

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 💾
---

# 年度書籍內容儲存

## 目標

將外部內容（如 OCR 結果、生成的 IG 貼文、YT 腳本等）儲存到年度書籍中，作為年度知識累積的一部分。

## 功能說明

這個 Playbook 會：

1. **接收外部內容**：接受各種格式的外部內容（文字、markdown 等）
2. **組織內容**：根據內容類型和時間，將內容組織到年度書籍的適當位置
3. **儲存內容**：將內容儲存到本地檔案系統，整合到年度書籍結構中
4. **記錄元資料**：記錄內容來源、類型、標籤等資訊

## 使用情境

- 儲存 OCR 提取的文字內容
- 儲存生成的 IG 貼文
- 儲存生成的 YT 腳本
- 儲存其他外部內容到年度書籍

## 輸入

- `external_content`: 外部內容（必填）
- `content_type`: 內容類型（ocr, ig_post, yt_script, article, note, other）
- `year`: 年份（預設為當前年份）
- `month`: 月份（1-12，預設為當前月份）
- `title`: 內容標題（可選）
- `source_files`: 來源檔案路徑列表（可選）
- `tags`: 標籤列表（可選）
- `metadata`: 額外的元資料（可選）

## 輸出

- `saved_entry`: 儲存的條目資訊
- `yearly_book_path`: 年度書籍檔案路徑
- `entry_path`: 儲存的條目檔案路徑

## 步驟（概念性）

1. 驗證輸入內容和參數
2. 組織內容格式和位置
3. 儲存內容到檔案系統
4. 記錄元資料和索引

## 注意事項

- 內容整合：儲存的外部內容不會自動整合到年度年鑑中
- 檔案路徑：確保提供的來源檔案路徑是有效的
- 內容格式：內容會以 markdown 格式儲存
- 隱私保護：所有內容只存在本地，不會上傳到雲端












