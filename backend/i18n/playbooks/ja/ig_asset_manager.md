---
playbook_code: ig_asset_manager
version: 1.0.0
name: IG アセット管理
description: 命名検証、サイズチェック、フォーマット検証を含む IG 投稿アセットの管理
tags:
  - instagram
  - assets
  - validation
  - obsidian

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_asset_manager_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: coder
icon: 📦
capability_code: instagram
---

# IG アセット管理

## 目標

IG 投稿アセット（画像、動画）を管理し、命名規則の検証、サイズチェック、異なる投稿タイプ（post、carousel、reel、story）のフォーマット検証を含む。

## 機能

この Playbook は以下を実行します：

1. **アセットスキャン**: 投稿フォルダ内のアセットをスキャンし、メタデータを抽出
2. **アセット検証**: IG 仕様に基づいてアセットを検証（サイズ、比率、フォーマット）
3. **アセットリスト生成**: 投稿タイプに基づいて必要なアセットリストを生成

## 使用例

- IG 投稿公開前のアセット検証
- アセット命名規則の確認
- 新規投稿の必要なアセットリスト生成
- アセットサイズとファイルサイズの確認

## 入力

- `post_folder`: 投稿フォルダパス（vault 相対）（必須）
- `vault_path`: Obsidian Vault パス（必須）
- `post_type`: 投稿タイプ - "post"、"carousel"、"reel" または "story"（必須）

## 出力

- `asset_list`: 名前、サイズ、検証ステータスを含むメタデータ付きアセットリスト
- `validation_results`: 各アセットの詳細な検証結果
- `missing_assets`: 不足している必須アセットのリスト
- `size_warnings`: 不正なサイズまたはファイルサイズの警告

## ステップ（概念的）

1. 投稿フォルダ内のアセットをスキャンしてすべての画像/動画ファイルを発見
2. 指定された投稿タイプの IG 仕様に基づいてアセットを検証
3. 投稿タイプの要件に基づいて必要なアセットリストを生成

## アセット仕様

- **Post/Carousel**: 1080x1080 (1:1)、最大 8MB
- **Reel/Story**: 1080x1920 (9:16)、最大 100MB

## 備考

- アセット命名は規則に従う必要があります：`{post_slug}_{index}.{ext}`
- 複数の投稿タイプの検証をサポート
- 非準拠アセットの詳細な警告を提供

