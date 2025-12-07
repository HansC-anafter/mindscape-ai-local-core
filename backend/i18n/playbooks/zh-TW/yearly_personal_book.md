---
playbook_code: yearly_personal_book
version: 1.0.0
name: 幫自己每年出本書
description: 從今年的 Mindscape 對話與筆記中，整理出每月小章節，最後合成一本年度敘事
tags:
  - journal
  - reflection
  - personal
  - annual

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools: []

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 📖
---

# 幫自己每年出本書

## 目標

從今年你在 Mindscape 留下的對話與筆記，整理出一份年度年鑑初稿。

## 功能說明

這個 Playbook 會：

1. **收集資料**：從本地 Mindscape 資料庫中抓取今年的所有對話與筆記
2. **分月整理**：將資料按月份分組，為每個月生成一個小章節
3. **年度總結**：將 12 個月的章節整合成一份完整的年度年鑑

## 使用情境

- 年度回顧與反思
- 個人成長記錄
- 知識累積整理
- 年度總結報告

## 輸入

- `year`: 要整理的年份（預設為當前年份）

## 輸出

- `annual_markdown`: 完整的年度年鑑 markdown 內容
- `monthly_chapters`: 12 個月的章節 markdown 列表

## 步驟（概念性）

1. 收集年度資料（對話與筆記）
2. 按月分組資料
3. 生成月度章節
4. 整合年度年鑑
5. 儲存結果

## 注意事項

- 資料隱私：所有資料只存在本地，不會上傳到雲端
- 只讀取寫給自己的內容：系統只會讀取你與 Mindscape 的對話
- 可預覽修改：生成後可以先預覽、修改，再決定要不要匯出
- 不會自動發佈：不會自動幫你發佈、寄給任何人

### 階段 6: 文件生成與保存

#### 步驟 6.1: 保存年度書籍內容
**必須**使用 `filesystem_write_file` 工具保存年度書籍內容：

- 文件路徑: `artifacts/yearly_personal_book/{{execution_id}}/yearly_book_content.md`
- 內容: 完整的年度年鑑內容
- 格式: Markdown 格式

#### 步驟 6.2: 保存章節大綱
**必須**使用 `filesystem_write_file` 工具保存章節大綱：

- 文件路徑: `artifacts/yearly_personal_book/{{execution_id}}/chapters_outline.md`
- 內容: 12 個月的章節大綱和結構
- 格式: Markdown 格式

#### 步驟 6.3: 保存月度章節（如已生成）
如果已生成月度章節，保存到：

- 文件路徑: `artifacts/yearly_personal_book/{{execution_id}}/month-{01-12}.md`
- 內容: 每個月的獨立章節內容
- 格式: Markdown 格式

## 預期結果

- 一份完整的年度年鑑 markdown 檔案（yearly_book_content.md）
- 12 個月的獨立章節檔案（month-01.md ~ month-12.md）
- 可以自行潤稿、列印、留給未來的自己
- 所有文件已保存到 artifacts 目錄供後續使用

