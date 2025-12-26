---
playbook_code: ig_frontmatter_validator
version: 1.0.0
name: IG Frontmatter 検証
description: 統一 Frontmatter Schema v2.0.0 に基づいて投稿 frontmatter を検証し、準備スコアを計算
tags:
  - instagram
  - frontmatter
  - validation
  - schema

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_frontmatter_validator_tool
  - obsidian_read_note

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: coder
icon: 📋
---

# IG Frontmatter 検証

## 目標

統一 Frontmatter Schema v2.0.0 に基づいて投稿 frontmatter を検証し、準備スコアを計算して投稿公開準備度を評価。

## 機能

この Playbook は以下を実行します：

1. **投稿読み込み**: Obsidian vault から投稿ファイルを読み込む
2. **Frontmatter 検証**: スキーマに基づいて frontmatter を検証し、準備スコアを計算

## 使用例

- 公開前の frontmatter 検証
- 投稿準備スコアの計算
- 不足している必須フィールドの識別
- スキーマコンプライアンスの確保

## 入力

- `post_path`: 投稿 Markdown ファイルパス（vault 相対）（オプション）
- `vault_path`: Obsidian Vault パス（post_path が提供されている場合は必須）
- `frontmatter`: 検証する frontmatter 辞書（post_path の代替）
- `strict_mode`: 厳密モード - すべての必須フィールドが存在する必要がある（デフォルト：false）
- `domain`: 期待されるドメイン - "ig"、"wp"、"seo"、"book"、"brand"、"ops" または "blog"（オプション）

## 出力

- `is_valid`: frontmatter が有効かどうか
- `readiness_score`: 準備スコア（0-100）
- `missing_fields`: 不足している必須フィールドのリスト
- `warnings`: 警告リスト（例：v1.0 スキーマ検出）
- `errors`: 検証エラーのリスト

## 準備スコア

準備スコア（0-100）は投稿 frontmatter の完全性を示します：
- 100: すべての必須および推奨フィールドが存在
- 80-99: すべての必須フィールドが存在、一部の推奨フィールドが不足
- 60-79: ほとんどの必須フィールドが存在
- 60未満: 重要な必須フィールドが不足

## ステップ（概念的）

1. vault から投稿ファイルを読み込むか、提供された frontmatter を使用
2. 統一 Frontmatter Schema v2.0.0 に基づいて検証
3. フィールドの完全性に基づいて準備スコアを計算

## 備考

- 完全な検証のための厳密モードをサポート
- スキーマバージョンを検出し、警告を提供
- frontmatter を直接検証するか、ファイルから検証可能

