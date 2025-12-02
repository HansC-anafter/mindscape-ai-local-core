---
playbook_code: pdf_ocr_and_index
version: 1.0.0
name: PDF OCR 與索引
description: 處理 PDF 檔案，執行 OCR 提取文字內容，並將結果嵌入向量資料庫建立索引
tags:
  - ocr
  - pdf
  - text-extraction
  - document-processing
  - vector-store
  - indexing

kind: system_tool
interaction_mode:
  - silent
visible_in:
  - workspace_tools_panel
  - console_only

required_tools:
  - core_files.ocr_pdf
  - vector_store.embed_text
  - vector_store.create_index

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 📄🔍
---

# PDF OCR 與索引

## 目標

處理 PDF 檔案，執行 OCR（光學字元辨識）提取文字內容，並將結果嵌入向量資料庫建立索引，供後續 RAG（檢索增強生成）查詢使用。

## 功能說明

這個 Playbook 會：

1. **執行 OCR**：對 PDF 檔案進行光學字元辨識，提取文字內容
2. **生成嵌入向量**：將提取的文字轉換為向量表示
3. **建立索引**：將向量存入向量資料庫，建立可搜尋的索引

## 使用情境

- 研究論文或技術文件的索引
- 大量 PDF 文件的批次處理與搜尋
- 建立知識庫前的文件預處理
- RAG 系統的文件準備

## 輸入

- `pdf_files`: PDF 檔案路徑列表（必填）

## 輸出

- `ocr_text`: OCR 提取的文字內容
- `vector_ids`: 生成的向量 ID 列表
- `index_id`: 建立的索引 ID

## 步驟（概念性）

1. 讀取 PDF 檔案
2. 執行 OCR 提取文字
3. 將文字轉換為嵌入向量
4. 存入向量資料庫
5. 建立索引供後續查詢

## 範例

**輸入**：
- 研究論文 PDF 檔案

**輸出**：
- OCR 文字內容
- 向量索引 ID
- 可用於 RAG 查詢的索引

## 注意事項

- 支援多檔案批次處理
- OCR 品質取決於 PDF 原始品質
- 向量嵌入需要適當的模型配置
- 索引建立可能需要一些時間，取決於文件大小

