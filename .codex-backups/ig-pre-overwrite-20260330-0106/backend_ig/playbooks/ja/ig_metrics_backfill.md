---
playbook_code: ig_metrics_backfill
version: 1.0.0
capability_code: instagram
name: IG メトリクスバックフィル
description: 手動バックフィル、データ分析、パフォーマンス要素追跡を含む投稿公開後のメトリクスを管理
tags:
  - instagram
  - metrics
  - analytics
  - performance

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_metrics_backfill_tool

language_strategy: model_native
locale: ja
supported_locales:
  - zh-TW
  - en
  - ja
default_locale: ja
auto_localize: true

entry_agent_type: coder
icon: 📊
---

# IG メトリクスバックフィル

## 目標

手動バックフィル、パフォーマンス分析、要素追跡、シリーズ集約を含む投稿公開後のメトリクスを管理。

## 機能

この Playbook は以下を実行します：

1. **メトリクスバックフィル**: 投稿メトリクスを手動でバックフィル
2. **パフォーマンス分析**: しきい値で投稿パフォーマンスを分析
3. **要素追跡**: パフォーマンス要素を追跡
4. **ルール記述**: パフォーマンスルールを記述
5. **シリーズ集約**: シリーズ間でメトリクスを集約

## 使用例

- 外部ソースからメトリクスをバックフィル
- 投稿パフォーマンスを分析
- パフォーマンス要素を追跡
- シリーズメトリクスを集約

## 入力

- `action`: 実行するアクション - "backfill"、"analyze"、"track_elements"、"write_rules" または "aggregate_series"（必須）
- `vault_path`: Obsidian Vault パス（必須）
- `post_path`: 投稿ファイルパス（ほとんどのアクションに必要）
- `metrics`: メトリクス辞書（backfill アクションに必要）
- `backfill_source`: バックフィルソース（例：'manual'、'api'、'scraper'）（オプション）
- `threshold_config`: カスタムしきい値設定（オプション）
- `elements`: パフォーマンス要素リスト（track_elements アクションに必要）
- `performance_level`: パフォーマンスレベル - "good"、"average" または "poor"（デフォルト：good）
- `rules`: パフォーマンスルールリスト（write_rules アクションに必要）
- `series_code`: シリーズコード（aggregate_series アクションに必要）
- `series_posts`: シリーズ内の投稿パスリスト（aggregate_series アクションに必要）

## 出力

- `frontmatter`: メトリクスを含む更新された frontmatter
- `analysis`: パフォーマンス分析結果
- `aggregation`: 集約されたシリーズメトリクス

## アクション

1. **backfill**: 投稿メトリクスを手動でバックフィル
2. **analyze**: しきい値に基づいて投稿パフォーマンスを分析
3. **track_elements**: パフォーマンス要素を追跡
4. **write_rules**: パフォーマンスルールを記述
5. **aggregate_series**: シリーズ投稿間でメトリクスを集約

## ステップ（概念的）

1. アクションに基づいてメトリクスをバックフィルまたは分析
2. 必要に応じて要素を追跡またはルールを記述
3. 該当する場合、シリーズメトリクスを集約

## 備考

- 複数のバックフィルソースをサポート
- カスタムしきい値でパフォーマンスを分析可能
- 最適化のためにパフォーマンス要素を追跡

