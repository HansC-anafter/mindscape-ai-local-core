---
playbook_code: ig_vault_structure_manager
version: 1.0.0
capability_code: instagram
name: IG Vault 構造管理
description: IG 投稿ワークフローの Obsidian Vault 構造を管理。初期化、検証、コンテンツスキャンをサポート。
tags:
  - instagram
  - obsidian
  - vault
  - structure

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_vault_structure_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: coder
icon: 📁
---

# IG Vault 構造管理

## 目標

IG 投稿コンテンツワークフローの標準 Obsidian Vault フォルダ構造を管理。初期化、検証、コンテンツスキャンをサポート。

## 機能

この Playbook は以下を実行します：

1. **構造初期化**: IG 投稿ワークフローの標準フォルダ構造を作成
2. **構造検証**: vault 構造が標準要件に準拠しているか確認
3. **コンテンツスキャン**: vault コンテンツをスキャンし、投稿、シリーズ、アイデアのインデックスを生成

## 使用例

- IG 投稿ワークフローの新しい Obsidian vault をセットアップ
- 既存の vault 構造を検証
- vault 管理のためのコンテンツインデックスを生成
- フォルダ構造の準拠を確保

## 入力

- `vault_path`: Obsidian Vault パス（必須）
- `action`: 実行するアクション - "init"、"validate" または "scan"（デフォルト："validate"）
- `create_missing`: 検証時に不足しているフォルダを作成するか（デフォルト：false）

## 出力

- `structure_status`: 構造ステータス（initialized、incomplete、valid など）
- `is_valid`: vault 構造が有効かどうか
- `created_folders`: 作成されたフォルダのリスト（init アクションのみ）
- `missing_folders`: 不足しているフォルダのリスト
- `content_index`: 投稿、シリーズ、アイデアを含むコンテンツインデックス（scan アクション）
- `post_count`: 見つかった IG 投稿数
- `series_count`: 見つかったシリーズ数
- `idea_count`: 見つかったアイデア数

## 標準フォルダ構造

- `10-Ideas`: 投稿アイデアとコンセプト
- `20-Posts`: IG 投稿コンテンツ
- `30-Assets`: 投稿アセット（画像、動画）
- `40-Series`: 投稿シリーズ組織
- `50-Playbooks`: Playbook テンプレート
- `60-Reviews`: レビューとフィードバック
- `70-Metrics`: パフォーマンス指標
- `90-Export`: エクスポートパック

## ステップ（概念的）

1. vault フォルダ構造を初期化または検証
2. 不足している必須フォルダを確認
3. コンテンツをスキャンしてインデックスを生成（scan アクションの場合）

## 備考

- 標準構造により一貫した組織化を確保
- 検証中の自動フォルダ作成をサポート
- コンテンツスキャンにより vault コンテンツの概要を提供

