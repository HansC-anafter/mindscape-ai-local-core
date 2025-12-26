---
playbook_code: ig_content_reuse
version: 1.0.0
name: IG コンテンツ再利用
description: 異なる IG フォーマット間でのコンテンツ変換と再利用を管理
tags:
  - instagram
  - content-reuse
  - transformation
  - formats

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_content_reuse_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: writer
icon: ♻️
---

# IG コンテンツ再利用

## 目標

記事からカルーセル、カルーセルから Reel、Reel からストーリーなど、異なる IG フォーマット間でコンテンツを変換および再利用。

## 機能

この Playbook は以下を実行します：

1. **記事からカルーセル**: 記事コンテンツをカルーセル形式に変換
2. **カルーセルから Reel**: カルーセル投稿を Reel 形式に変換
3. **Reel からストーリー**: Reel コンテンツをストーリー形式に変換

## 使用例

- カルーセル投稿のために記事コンテンツを再利用
- カルーセル投稿を Reel 動画に変換
- Reel コンテンツをストーリーシリーズに変換
- フォーマット間でコンテンツ価値を最大化

## 入力

- `action`: 実行するアクション - "article_to_carousel"、"carousel_to_reel" または "reel_to_stories"（必須）
- `vault_path`: Obsidian Vault パス（必須）
- `source_post_path`: ソース投稿パス（article_to_carousel に必要）
- `carousel_posts`: カルーセル投稿パスリスト（carousel_to_reel に必要）
- `source_reel_path`: ソース Reel 投稿パス（reel_to_stories に必要）
- `target_folder`: 生成された投稿のターゲットフォルダ（必須）
- `carousel_slides`: カルーセルスライド数（デフォルト：7）
- `slide_structure`: カスタムスライド構造設定（オプション）
- `reel_duration`: Reel の継続時間（秒）（オプション）
- `story_count`: 作成するストーリー数（デフォルト：3）

## 出力

- `result`: 作成された投稿情報を含む変換結果

## 変換タイプ

1. **article_to_carousel**: 記事を複数のカルーセルスライドに分割
2. **carousel_to_reel**: カルーセル投稿を Reel スクリプトに結合
3. **reel_to_stories**: Reel をストーリーシリーズに分割

## ステップ（概念的）

1. vault からソースコンテンツを読み込む
2. ターゲットフォーマットに基づいてコンテンツを変換
3. ターゲットフォルダに新しい投稿を作成

## 備考

- カルーセルのカスタムスライド構造をサポート
- Reel の継続時間とストーリー数を指定可能
- フォーマット間でコンテンツの一貫性を維持

