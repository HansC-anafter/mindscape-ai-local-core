---
playbook_code: ig_metrics_backfill
version: 1.0.0
name: IG Metrics Backfill
description: Manage post-publication metrics including manual backfill, data analysis, and performance element tracking
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
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 📊
capability_code: instagram
---

# IG Metrics Backfill

## Goal

Manage post-publication metrics including manual backfill, performance analysis, element tracking, and series aggregation.

## Functionality

This Playbook will:

1. **Backfill Metrics**: Manually backfill post metrics
2. **Analyze Performance**: Analyze post performance with thresholds
3. **Track Elements**: Track performance elements
4. **Write Rules**: Write performance rules
5. **Aggregate Series**: Aggregate metrics across series

## Use Cases

- Backfill metrics from external sources
- Analyze post performance
- Track performance elements
- Aggregate series metrics

## Inputs

- `action`: Action to perform - "backfill", "analyze", "track_elements", "write_rules", or "aggregate_series" (required)
- `vault_path`: Path to Obsidian Vault (required)
- `post_path`: Path to post file (required for most actions)
- `metrics`: Metrics dictionary (required for backfill action)
- `backfill_source`: Source of backfill (e.g., 'manual', 'api', 'scraper') (optional)
- `threshold_config`: Custom threshold configuration (optional)
- `elements`: List of performance elements (required for track_elements action)
- `performance_level`: Performance level - "good", "average", or "poor" (default: good)
- `rules`: List of performance rules (required for write_rules action)
- `series_code`: Series code (required for aggregate_series action)
- `series_posts`: List of post paths in series (required for aggregate_series action)

## Outputs

- `frontmatter`: Updated frontmatter with metrics
- `analysis`: Performance analysis results
- `aggregation`: Aggregated series metrics

## Actions

1. **backfill**: Manually backfill post metrics
2. **analyze**: Analyze post performance against thresholds
3. **track_elements**: Track performance elements
4. **write_rules**: Write performance rules
5. **aggregate_series**: Aggregate metrics across series posts

## Steps (Conceptual)

1. Backfill or analyze metrics based on action
2. Track elements or write rules if needed
3. Aggregate series metrics if applicable

## Notes

- Supports multiple backfill sources
- Can analyze performance with custom thresholds
- Tracks performance elements for optimization

