---
playbook_code: ig_content_checker
version: 1.0.0
name: IG コンテンツチェッカー
description: 医療/投資の主張、著作権、個人データ、ブランドトーンを含む IG 投稿コンテンツのコンプライアンス問題をチェック
tags:
  - instagram
  - compliance
  - content-safety
  - validation

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_content_checker_tool
  - obsidian_read_note

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: writer
icon: ✅
---

# IG コンテンツチェッカー

## 目標

医療/投資の主張、著作権侵害、個人データの露出、ブランドトーン違反を含む IG 投稿コンテンツのコンプライアンス問題をチェック。

## 機能

この Playbook は以下を実行します：

1. **投稿読み込み**: Obsidian vault から投稿コンテンツを読み込むか、提供されたコンテンツを使用
2. **コンテンツチェック**: コンテンツに対して包括的なコンプライアンスチェックを実行

## 使用例

- 公開前のコンテンツコンプライアンスチェック
- 潜在的な法的リスクの識別
- ブランドトーンの一貫性を確保
- 個人データの露出を検出

## 入力

- `content`: チェックする投稿コンテンツテキスト（post_path が提供されている場合はオプション）
- `post_path`: 投稿 Markdown ファイルパス（vault 相対、content が提供されている場合はオプション）
- `vault_path`: Obsidian Vault パス（post_path が提供されている場合は必須）
- `frontmatter`: 投稿 frontmatter（オプション）

## 出力

- `risk_flags`: 見つかったリスクフラグ（醫療、投資、侵權、個資）
- `warnings`: 警告リスト
- `checks`: 各カテゴリの詳細なチェック結果
- `is_safe`: コンテンツが安全かどうか（リスクフラグなし）

## チェックカテゴリ

1. **医療の主張**: 医療治療の主張と健康関連のキーワードを検出
2. **投資の主張**: 投資アドバイスと金融の約束を検出
3. **著作権**: 著作権関連のキーワードと潜在的な侵害を検出
4. **個人データ**: 個人情報パターン（電話、メール、ID）を検出
5. **ブランドトーン**: ネガティブなブランドトーンキーワードをチェック

## ステップ（概念的）

1. vault から投稿コンテンツを読み込むか、提供されたコンテンツを使用
2. すべてのカテゴリでコンプライアンスチェックを実行
3. リスクフラグと警告を生成

## 備考

- 各リスクカテゴリの詳細な警告を提供
- コンテンツを直接チェックするか、Obsidian vault からチェック可能
- コンテンツ文字列とファイルパス入力をサポート

