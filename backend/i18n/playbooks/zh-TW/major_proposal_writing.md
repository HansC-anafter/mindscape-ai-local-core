---
playbook_code: major_proposal_writing
version: 1.0.0
name: 重大申請文件撰寫助手
description: 上傳簡章/範本，自動萃出模板，引導你逐節撰寫申請文件
tags:
  - writing
  - proposal
  - document
  - application

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_files.upload
  - core_files.extract_text
  - core_llm.generate
  - core_llm.structured_extract
  - core_export.markdown
  - core_export.docx
  - major_proposal.import_template_from_files
  - major_proposal.start_proposal_project
  - major_proposal.generate_section_draft
  - major_proposal.assemble_full_proposal

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: 📝
---

# 重大申請文件撰寫助手

## 目標

協助你撰寫重大申請文件（如政府補助、貸款申請、創業提案等）。透過上傳簡章或範本，系統會自動萃取出模板結構，然後引導你逐節填寫內容，最後組裝成完整的申請文件。

## 功能說明

這個 Playbook 會：

1. **解析模板**：上傳簡章/範本檔案，自動提取文字內容並分析模板結構
2. **建立專案**：確認模板結構，建立新的申請文件專案
3. **逐節撰寫**：引導你逐節填寫內容，AI 根據你的資訊生成章節草稿
4. **組裝文件**：將所有章節組裝成完整的申請文件，並匯出為 DOCX 格式

## 使用情境

- 政府補助申請文件
- 貸款申請文件
- 創業提案文件
- 其他重大申請文件

## 輸入

- `template_files`: 簡章/範本檔案（PDF/DOCX，必填）
- `template_type`: 模板類型（gov_grant, loan, startup, other）
- `project_name`: 申請項目名稱（必填）

## 輸出

- `template_id`: 建立的模板 ID
- `project_id`: 申請文件專案 ID
- `proposal_markdown`: 完整的申請文件 Markdown
- `proposal_docx_path`: 生成的 DOCX 檔案路徑

## 步驟（概念性）

1. 上傳並解析模板檔案
2. 建立申請文件專案
3. 逐節撰寫內容（循環）
4. 組裝完整文件並匯出

### 階段 6: 文件生成與保存

#### 步驟 6.1: 保存提案草稿
**必須**使用 `filesystem_write_file` 工具保存提案草稿：

- 文件路徑: `artifacts/major_proposal_writing/{{execution_id}}/proposal_draft.md`
- 內容: 完整的申請文件草稿（Markdown 格式）
- 格式: Markdown 格式

#### 步驟 6.2: 保存提案大綱
**必須**使用 `filesystem_write_file` 工具保存提案大綱：

- 文件路徑: `artifacts/major_proposal_writing/{{execution_id}}/proposal_outline.md`
- 內容: 提案結構和大綱，包含所有章節和要點
- 格式: Markdown 格式

#### 步驟 6.3: 保存 DOCX 文件（如已生成）
如果已生成 DOCX 文件，記錄文件路徑到執行摘要中。

## 注意事項

- 模板解析：系統會自動分析模板結構，但可能需要人工確認和調整
- 內容生成：AI 生成的內容需要人工審核和調整
- 格式要求：確保最終文件符合申請單位的格式要求
- 截止日期：注意申請截止日期，預留足夠時間完成文件
- 所有生成的提案文件已保存到文件供後續參考

