---
playbook_code: pdf_ocr_and_index
version: 1.0.0
name: PDF OCR とインデックス
description: PDFファイルを処理し、OCRを実行してテキストコンテンツを抽出し、結果をベクトルデータベースにインデックス化
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
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 📄🔍
---

# PDF OCR とインデックス

## 目標

PDFファイルを処理し、OCR（光学文字認識）を実行してテキストコンテンツを抽出し、結果をベクトルデータベースにインデックス化して、後続のRAG（検索拡張生成）クエリに使用できるようにします。

## 機能

このPlaybookは以下を実行します：

1. **OCRの実行**: 光学文字認識を使用してPDFファイルからテキストコンテンツを抽出
2. **埋め込みの生成**: 抽出されたテキストをベクトル表現に変換
3. **インデックスの作成**: ベクトルをベクトルデータベースに保存し、検索可能なインデックスを作成

## 使用例

- 研究論文や技術文書のインデックス化
- 大量のPDFコレクションのバッチ処理と検索
- ナレッジベース構築前の文書前処理
- RAGシステムの文書準備

## 入力

- `pdf_files`: PDFファイルパスのリスト（必須）

## 出力

- `ocr_text`: OCRで抽出されたテキストコンテンツ
- `vector_ids`: 生成されたベクトルIDのリスト
- `index_id`: 作成されたインデックスID

## ステップ（概念的）

1. PDFファイルを読み込む
2. OCRを実行してテキストを抽出
3. テキストを埋め込みに変換
4. ベクトルデータベースに保存
5. 後続のクエリ用のインデックスを作成

## 例

**入力**：
- 研究論文PDFファイル

**出力**：
- OCRテキストコンテンツ
- ベクトルインデックスID
- RAGクエリに使用可能なインデックス

## 注意事項

- 複数ファイルのバッチ処理をサポート
- OCR品質は元のPDF品質に依存
- ベクトル埋め込みには適切なモデル設定が必要
- インデックス作成には文書サイズに応じて時間がかかる場合があります

