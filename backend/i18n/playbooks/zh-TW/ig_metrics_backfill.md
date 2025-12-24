---
playbook_code: ig_metrics_backfill
version: 1.0.0
name: IG 指標回填
description: 管理發布後指標，包括手動回填、數據分析和績效元素追蹤
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
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 📊
capability_code: instagram
---

# IG 指標回填

## 目標

管理發布後指標，包括手動回填、績效分析、元素追蹤和系列聚合。

## 功能說明

這個 Playbook 會：

1. **回填指標**：手動回填貼文指標
2. **分析績效**：使用閾值分析貼文績效
3. **追蹤元素**：追蹤績效元素
4. **寫入規則**：寫入績效規則
5. **聚合系列**：跨系列聚合指標

## 使用情境

- 從外部來源回填指標
- 分析貼文績效
- 追蹤績效元素
- 聚合系列指標

## 輸入

- `action`: 要執行的動作 - "backfill"、"analyze"、"track_elements"、"write_rules" 或 "aggregate_series"（必填）
- `vault_path`: Obsidian Vault 路徑（必填）
- `post_path`: 貼文檔案路徑（大多數動作需要）
- `metrics`: 指標字典（backfill 動作需要）
- `backfill_source`: 回填來源（例如 'manual'、'api'、'scraper'）（選填）
- `threshold_config`: 自訂閾值配置（選填）
- `elements`: 績效元素清單（track_elements 動作需要）
- `performance_level`: 績效等級 - "good"、"average" 或 "poor"（預設：good）
- `rules`: 績效規則清單（write_rules 動作需要）
- `series_code`: 系列代碼（aggregate_series 動作需要）
- `series_posts`: 系列中的貼文路徑清單（aggregate_series 動作需要）

## 輸出

- `frontmatter`: 包含指標的更新 frontmatter
- `analysis`: 績效分析結果
- `aggregation`: 聚合的系列指標

## 動作

1. **backfill**: 手動回填貼文指標
2. **analyze**: 根據閾值分析貼文績效
3. **track_elements**: 追蹤績效元素
4. **write_rules**: 寫入績效規則
5. **aggregate_series**: 跨系列貼文聚合指標

## 步驟（概念性）

1. 根據動作回填或分析指標
2. 如果需要，追蹤元素或寫入規則
3. 如果適用，聚合系列指標

## 備註

- 支援多種回填來源
- 可以使用自訂閾值分析績效
- 追蹤績效元素以進行優化

