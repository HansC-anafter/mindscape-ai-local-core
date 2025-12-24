---
playbook_code: ig_batch_processor
version: 1.0.0
name: IG バッチプロセッサ
description: 検証、生成、エクスポート操作を含む複数の投稿のバッチ処理を管理
tags:
  - instagram
  - batch
  - automation
  - processing

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_batch_processor_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: coder
icon: ⚙️
capability_code: instagram
---

# IG バッチプロセッサ

## 目標

複数の IG 投稿のバッチ処理を管理し、検証、エクスポートパック生成、ステータス更新、カスタム操作を含む。

## 機能

この Playbook は以下を実行します：

1. **バッチ検証**: 一度に複数の投稿を検証
2. **バッチエクスポートパック生成**: 複数の投稿のエクスポートパックを生成
3. **バッチステータス更新**: 複数の投稿のステータスを一括更新
4. **バッチ処理**: 複数の投稿に対してカスタム操作を実行

## 使用例

- 公開前の複数の投稿を検証
- バッチ公開用のエクスポートパックを生成
- 投稿ステータスを一括更新
- カスタムバッチ操作を実行

## 入力

- `action`: 実行するアクション - "batch_validate"、"batch_generate_export_packs"、"batch_update_status" または "batch_process"（必須）
- `vault_path`: Obsidian Vault パス（必須）
- `post_paths`: 投稿ファイルパスリスト（vault 相対）（必須）
- `strict_mode`: True の場合、すべての必須フィールドが存在する必要がある（デフォルト：false）
- `output_folder`: エクスポートパックの出力フォルダ（オプション）
- `new_status`: 設定する新しいステータス（batch_update_status アクションに必要）
- `operations`: 実行する操作リスト（batch_process アクションに必要）
- `operation_config`: 操作の設定（オプション）

## 出力

- `result`: 各投稿の操作ステータスを含むバッチ処理結果

## アクション

1. **batch_validate**: frontmatter スキーマに基づいて複数の投稿を検証
2. **batch_generate_export_packs**: 複数の投稿のエクスポートパックを生成
3. **batch_update_status**: 複数の投稿のステータスフィールドを一括更新
4. **batch_process**: 複数の投稿に対してカスタム操作を実行

## ステップ（概念的）

1. 選択されたアクションに基づいて複数の投稿を処理
2. 各投稿に対して操作を実行
3. 結果を収集して返す

## 備考

- 検証のための厳密モードをサポート
- batch_process アクションを通じてカスタム操作を処理可能
- 各投稿の詳細な結果を返す

