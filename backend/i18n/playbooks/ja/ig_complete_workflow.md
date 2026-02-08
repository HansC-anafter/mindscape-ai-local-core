---
playbook_code: ig_complete_workflow
version: 1.0.0
name: IG 完全ワークフロー
description: 複数の playbook を順番に編成してエンドツーエンドのワークフローを実行
tags:
  - instagram
  - workflow
  - orchestration
  - automation

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_complete_workflow_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: coder
icon: 🔄
---

# IG 完全ワークフロー

## 目標

IG 投稿作成、レビュー、公開のエンドツーエンドワークフローを実行するために複数の playbook を編成。

## 機能

この Playbook は以下を実行します：

1. **ワークフロー実行**: 複数のステップを持つ事前定義されたワークフローを実行
2. **投稿作成ワークフロー**: 完全なワークフローに従って新しい投稿を作成
3. **レビューワークフロー**: 既存の投稿に対してレビューワークフローを実行

## 使用例

- 完全な投稿作成ワークフローを実行
- 複数の playbook を順番に編成
- エンドツーエンドの投稿公開プロセスを自動化
- 投稿レビューワークフローを管理

## 入力

- `action`: 実行するアクション - "execute_workflow"、"create_post_workflow" または "review_workflow"（必須）
- `vault_path`: Obsidian Vault パス（必須）
- `workflow_name`: ワークフロー名（execute_workflow アクションに必要）
- `workflow_steps`: ワークフローステップリスト（execute_workflow アクションに必要）
- `initial_context`: 初期コンテキスト変数（オプション）
- `post_content`: 投稿コンテンツ（create_post_workflow アクションに必要）
- `post_metadata`: 投稿メタデータ/frontmatter（create_post_workflow アクションに必要）
- `target_folder`: 投稿のターゲットフォルダ（デフォルト：20-Posts）
- `post_path`: 投稿ファイルパス（review_workflow アクションに必要）
- `review_notes`: レビューノートリスト（オプション）

## 出力

- `result`: ステップ結果と最終コンテキストを含むワークフロー実行結果

## ワークフローアクション

1. **execute_workflow**: 複数のステップを持つ事前定義されたワークフローを実行
2. **create_post_workflow**: 完全なワークフローに従って新しい投稿を作成
3. **review_workflow**: 既存の投稿に対してレビューワークフローを実行

## ステップ（概念的）

1. 選択されたアクションに基づいてワークフローを実行
2. 順番にワークフローステップを実行
3. 結果を収集して最終コンテキストを返す

## 備考

- カスタムワークフロー定義をサポート
- 複数の playbook を編成可能
- ワークフローステップ間でコンテキストを維持

