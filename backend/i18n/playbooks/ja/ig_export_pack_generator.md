---
playbook_code: ig_export_pack_generator
version: 1.0.0
name: IG エクスポートパック生成器
description: post.md、hashtags.txt、CTA バリアント、チェックリストを含む IG 投稿の完全なエクスポートパックを生成
tags:
  - instagram
  - export
  - publishing
  - checklist

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_export_pack_generator_tool
  - ig_hashtag_manager_tool
  - ig_asset_manager_tool
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
icon: 📦
---

# IG エクスポートパック生成器

## 目標

投稿 markdown、ハッシュタグテキストファイル、CTA バリアント、公開前チェックリストを含む IG 投稿の完全なエクスポートパックを生成。

## 機能

この Playbook は以下を実行します：

1. **投稿読み込み**: Obsidian vault から投稿コンテンツと frontmatter を読み込む
2. **ハッシュタグ取得**: ハッシュタグを生成または提供されたハッシュタグを使用
3. **アセットスキャン**: 有効な場合、投稿アセットをスキャン
4. **エクスポートパック生成**: すべての必要なファイルを含む完全なエクスポートパックを作成

## 使用例

- 投稿公開の準備
- バッチ公開用のエクスポートパックを生成
- 公開前チェックリストを作成
- すべての必要なアセットを含む投稿をパッケージ化

## 入力

- `post_folder`: 投稿フォルダパス（vault 相対）（必須）
- `post_path`: 投稿 markdown ファイルパス（vault 相対）（必須）
- `vault_path`: Obsidian Vault パス（必須）
- `hashtags`: ハッシュタグリスト（提供されていない場合、生成される）
- `cta_variants`: CTA バリアントリスト（オプション）
- `include_assets`: チェックリストにアセットを含めるか（デフォルト：true）

## 出力

- `export_pack_path`: エクスポートパックフォルダパス
- `files_generated`: 生成されたファイルリスト
- `export_pack`: エクスポートパックコンテンツ

## エクスポートパック内容

1. **post.md**: Markdown 形式の投稿コンテンツ
2. **hashtags.txt**: ハッシュタグリスト
3. **cta_variants.txt**: CTA バリアント
4. **checklist.md**: 公開前チェックリスト

## ステップ（概念的）

1. 投稿コンテンツと frontmatter を読み込む
2. ハッシュタグを生成または取得
3. 有効な場合、アセットをスキャン
4. すべてのファイルを含むエクスポートパックを生成

## 備考

- 提供されていない場合、自動的にハッシュタグを生成
- アセットがスキャンされた場合、アセットチェックリストを含む
- 公開準備が整った完全なエクスポートパックを作成

