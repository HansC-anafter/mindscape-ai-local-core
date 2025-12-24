---
playbook_code: ig_interaction_templates
version: 1.0.0
name: IG インタラクションテンプレート
description: 一般的なコメント返信、DM スクリプト、トーン切り替えを含むインタラクションテンプレートを管理
tags:
  - instagram
  - templates
  - interaction
  - automation

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_interaction_templates_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: writer
icon: 💬
capability_code: instagram
---

# IG インタラクションテンプレート

## 目標

一般的なコメント返信、DM スクリプト、ストーリー返信のインタラクションテンプレートを管理し、トーン切り替えと変数レンダリングをサポート。

## 機能

この Playbook は以下を実行します：

1. **テンプレート作成**: 新しいインタラクションテンプレートを作成
2. **テンプレート取得**: ID でテンプレートを取得
3. **テンプレートリスト**: フィルタリングでテンプレートをリスト
4. **テンプレートレンダリング**: 変数でテンプレートをレンダリング
5. **テンプレート提案**: コンテキストに基づいてテンプレートを提案
6. **トーン切り替え**: テンプレートトーンを切り替え
7. **テンプレート更新**: 既存のテンプレートを更新

## 使用例

- 再利用可能なコメント返信テンプレートを作成
- 一般的なシナリオの DM スクリプトを管理
- 異なるコンテキストでテンプレートトーンを切り替え
- インタラクション応答を自動化

## 入力

- `action`: 実行するアクション - "create"、"get"、"list"、"render"、"suggest"、"switch_tone" または "update"（必須）
- `vault_path`: Obsidian Vault パス（必須）
- `template_id`: テンプレート識別子（get、render、switch_tone、update に必要）
- `template_type`: テンプレートタイプ - "comment_reply"、"dm_script" または "story_reply"（オプション）
- `content`: {{variable}} プレースホルダーを含むテンプレートコンテンツ（create に必要）
- `tone`: トーン - "friendly"、"professional"、"casual" または "formal"（オプション）
- `category`: カテゴリ（例：'greeting'、'product_inquiry'、'complaint'）（オプション）
- `tags`: 分類用のタグリスト（オプション）
- `variables`: テンプレートで使用される変数名リスト（オプション）
- `render_variables`: レンダリング用の変数値辞書（render に必要）
- `context`: テンプレート提案のコンテキスト説明（suggest に必要）
- `new_tone`: switch_tone アクションの新しいトーン（switch_tone に必要）
- `updates`: 更新するフィールド辞書（update に必要）

## 出力

- `template`: テンプレート情報
- `templates`: テンプレートリスト
- `rendered_content`: レンダリングされたテンプレートコンテンツ
- `suggested_template`: コンテキストに基づいて提案されたテンプレート

## テンプレートタイプ

- **comment_reply**: コメント返信テンプレート
- **dm_script**: ダイレクトメッセージスクリプトテンプレート
- **story_reply**: ストーリー返信テンプレート

## ステップ（概念的）

1. テンプレートを作成、取得、またはリスト
2. 必要に応じて変数でテンプレートをレンダリング
3. 必要に応じてトーンを切り替えたりテンプレートを更新

## 備考

- テンプレート内の変数プレースホルダーをサポート
- コンテキストに基づいてテンプレートを提案可能
- 異なるシナリオのトーン切り替えをサポート

