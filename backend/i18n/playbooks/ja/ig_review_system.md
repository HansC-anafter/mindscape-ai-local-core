---
playbook_code: ig_review_system
version: 1.0.0
name: IG レビューシステム
description: 変更ログ追跡、レビューノート、意思決定ログを含むレビューワークフローを管理
tags:
  - instagram
  - review
  - workflow
  - collaboration

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_review_system_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: writer
icon: 👁️
---

# IG レビューシステム

## 目標

バージョン変更ログ追跡、レビューノート、意思決定ログ、レビューステータス管理を含むレビューワークフローを管理。

## 機能

この Playbook は以下を実行します：

1. **変更ログ追加**: バージョン変更ログエントリを追加
2. **レビューノート追加**: 優先度とステータスを持つレビューノートを追加
3. **意思決定ログ追加**: 理由を含む意思決定ログを追加
4. **レビューノートステータス更新**: レビューノートステータスを更新
5. **サマリー取得**: レビューサマリーを取得

## 使用例

- 投稿バージョン変更を追跡
- レビューノートとフィードバックを管理
- 意思決定と理由を記録
- レビューステータスを追跡

## 入力

- `action`: 実行するアクション - "add_changelog"、"add_review_note"、"add_decision_log"、"update_review_note_status" または "get_summary"（必須）
- `vault_path`: Obsidian Vault パス（必須）
- `post_path`: 投稿ファイルパス（必須）
- `version`: バージョン文字列（add_changelog アクションに必要）
- `changes`: 変更の説明（add_changelog アクションに必要）
- `author`: 作成者名（オプション）
- `reviewer`: レビュアー名（add_review_note アクションに必要）
- `note`: レビューノートコンテンツ（add_review_note アクションに必要）
- `priority`: 優先度 - "high"、"medium" または "low"（デフォルト：medium）
- `status`: レビューステータス - "pending"、"addressed"、"resolved" または "rejected"（オプション）
- `decision`: 意思決定の説明（add_decision_log アクションに必要）
- `rationale`: 意思決定の理由（オプション）
- `decision_maker`: 意思決定者名（オプション）
- `note_index`: レビューノートインデックス（update_review_note_status アクションに必要）
- `new_status`: 新しいステータス（update_review_note_status アクションに必要）

## 出力

- `frontmatter`: レビュー情報を含む更新された frontmatter
- `summary`: レビューサマリー

## レビューステータス

- **pending**: レビューノートが処理待ち
- **addressed**: レビューノートが処理済み
- **resolved**: レビューノートが解決済み
- **rejected**: レビューノートが拒否済み

## ステップ（概念的）

1. 変更ログ、レビューノート、または意思決定ログを追加
2. 必要に応じてレビューノートステータスを更新
3. レビューサマリーを取得

## 備考

- レビューノートの優先度をサポート
- 意思決定の理由を追跡
- frontmatter でレビュー履歴を維持

