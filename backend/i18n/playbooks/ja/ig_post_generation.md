---
playbook_code: ig_post_generation
version: 1.0.0
name: IG投稿生成
description: コンテンツからInstagram投稿を生成し、IGプラットフォームの特性（文字数制限、ハッシュタグ、トーンなど）に最適化
tags:
  - social-media
  - instagram
  - content-creation
  - marketing

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.analyze
  - core_llm.generate

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 📱
capability_code: instagram
---

# IG投稿生成

## 目標

ソースコンテンツ（OCRテキスト、記事、ノートなど）から複数のInstagram投稿を生成し、文字数制限、ハッシュタグの使用、トーン調整などのIGプラットフォームの特性に最適化します。

## 機能

このPlaybookは以下を実行します：

1. **コンテンツの分析**: ソースコンテンツから主要なトピックとポイントを抽出
2. **投稿の生成**: トピックに基づいて複数のIG形式の投稿を作成
3. **フォーマットの最適化**: ハッシュタグを自動追加し、トーンを調整し、文字数制限に準拠

## 使用例

- 長文記事を複数のIG投稿に変換
- 研究レポートからソーシャルメディアコンテンツを生成
- ノートをIGコンテンツに変換
- コンテンツマーケティングの投稿バッチ生成

## 入力

- `source_content`: ソースコンテンツ（必須）
- `post_count`: 生成する投稿数（デフォルト: 5）

## 出力

- `ig_posts`: 生成されたIG投稿のリスト。各投稿には以下が含まれます：
  - `text`: 投稿テキストコンテンツ
  - `hashtags`: 関連ハッシュタグのリスト

## ステップ（概念的）

1. ソースコンテンツを分析して主要なトピックを抽出
2. トピックに基づいて指定された数のIG投稿を生成
3. 各投稿に適切なハッシュタグを追加
4. テキストをIGプラットフォームの特性に合わせて最適化

## 例

**入力**：
- ソースコンテンツ: AI技術に関する記事
- 投稿数: 5

**出力**：
- 5つのIG投稿。各投稿にはテキストとハッシュタグが含まれます

## 注意事項

- IG投稿の推奨文字数: 2,200文字以内
- 関連ハッシュタグを自動追加
- 生成されたコンテンツは手動での確認と調整が必要な場合があります
- 多言語コンテンツ生成をサポート

