---
playbook_code: ig_template_engine
version: 1.0.0
capability_code: instagram
name: IG テンプレートエンジン
description: 異なるトーンと CTA を持つ複数の IG 投稿バリアントを生成するためにテンプレートを適用
tags:
  - instagram
  - templates
  - content-generation
  - variants

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_template_engine_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: writer
icon: 📝
---

# IG テンプレートエンジン

## 目標

ソースコンテンツから異なるスタイルトーンと CTA（行動喚起）を持つ複数の IG 投稿バリアントを生成するためにテンプレートを適用。

## 機能

この Playbook は以下を実行します：

1. **テンプレート読み込み**: タイプ、スタイルトーン、目的に基づいてテンプレートを読み込む
2. **投稿生成**: 異なる CTA を持つ複数の投稿バリアントを生成

## 使用例

- A/B テスト用の複数の投稿バリアントを生成
- ブランドテンプレートをコンテンツに適用
- 異なる CTA を持つ投稿を作成
- 事前定義されたテンプレートを使用してコンテンツを変換

## 入力

- `template_type`: テンプレートタイプ - "carousel"、"reel" または "story"（必須）
- `style_tone`: スタイルトーン - "high_brand"、"friendly"、"coach" または "sponsored"（デフォルト："friendly"）
- `purpose`: 投稿目的 - "save"、"comment"、"dm" または "share"（デフォルト："save"）
- `source_content`: 変換するソースコンテンツ（必須）
- `generate_variants`: 異なる CTA を持つ複数のバリアントを生成するか（デフォルト：true）

## 出力

- `generated_posts`: 生成された IG 投稿バリアント
- `template_applied`: 適用されたテンプレート情報

## テンプレートタイプ

- **Carousel**: 複数画像投稿テンプレート
- **Reel**: 動画投稿テンプレート
- **Story**: ストーリー投稿テンプレート

## スタイルトーン

- **high_brand**: 高ブランド認知トーン
- **friendly**: フレンドリーで親しみやすいトーン
- **coach**: コーチングおよび教育的トーン
- **sponsored**: スポンサーコンテンツトーン

## CTA 目的

- **save**: 投稿の保存を促進
- **comment**: コメントを促進
- **dm**: ダイレクトメッセージを促進
- **share**: シェアを促進

## ステップ（概念的）

1. タイプ、トーン、目的に基づいてテンプレートを読み込む
2. ソースコンテンツにテンプレートを適用
3. 有効な場合、異なる CTA を持つ複数のバリアントを生成

## 備考

- 複数のテンプレートタイプとスタイルトーンをサポート
- テスト用の複数のバリアントを生成可能
- テンプレートには CTA バリアントが含まれる

