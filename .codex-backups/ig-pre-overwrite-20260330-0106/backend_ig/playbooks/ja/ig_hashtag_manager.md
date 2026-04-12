---
playbook_code: ig_hashtag_manager
version: 1.0.0
capability_code: instagram
name: IG Hashtag 管理
description: 投稿意図、オーディエンス、地域に基づいて IG 投稿のハッシュタググループを管理し、ハッシュタグを組み合わせる
tags:
  - instagram
  - hashtags
  - social-media
  - marketing

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_hashtag_manager_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: writer
icon: #
---

# IG Hashtag 管理

## 目標

投稿意図、ターゲットオーディエンス、地域に基づいて IG 投稿のハッシュタググループを管理し、インテリジェントにハッシュタグを組み合わせる。ハッシュタグブロックとコンプライアンスチェックをサポート。

## 機能

この Playbook は以下を実行します：

1. **ハッシュタググループ読み込み**: 事前定義されたハッシュタググループ（ブランド固定、テーマ、キャンペーン）を読み込む
2. **ハッシュタグ組み合わせ**: 意図、オーディエンス、地域に基づいてハッシュタグを組み合わせる
3. **ブロックチェック**: ハッシュタグがブロックリストにあるか確認

## 使用例

- IG 投稿のハッシュタグ推奨を生成
- 複数のグループからハッシュタグを組み合わせる
- ハッシュタグコンプライアンスとブロックを確認
- キャンペーンのハッシュタググループを管理

## 入力

- `intent`: 投稿意図 - "教育"、"引流"、"轉換" または "品牌"（オプション）
- `audience`: ターゲットオーディエンス（オプション）
- `region`: 地域（オプション）
- `hashtag_count`: 必要なハッシュタグ数 - 15、25 または 30（デフォルト：25）
- `action`: 実行するアクション - "recommend"、"combine" または "check_blocked"（デフォルト："recommend"）
- `hashtags`: 確認するハッシュタグのリスト（check_blocked アクションに必要）

## 出力

- `hashtag_groups`: ハッシュタググループ（ブランド固定、テーマ、キャンペーン）
- `recommended_hashtags`: 推奨ハッシュタグリスト
- `blocked_hashtags`: 見つかったブロックされたハッシュタグ
- `hashtag_groups_used`: 組み合わせで使用されたハッシュタググループ
- `total_count`: 総ハッシュタグ数

## ステップ（概念的）

1. 設定からハッシュタググループを読み込む
2. 意図、オーディエンス、地域に基づいてハッシュタグを組み合わせる
3. 提供された場合、ブロックされたハッシュタグを確認

## 備考

- 複数のハッシュタグ数オプション（15、25、30）をサポート
- ブランド固定ハッシュタグを自動的に含める
- ブロックリストに対するハッシュタグコンプライアンスを確認可能

