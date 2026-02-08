---
playbook_code: collect_series_material
version: 1.0.0
capability_code: mindscape_book
---
# Collect Series Material

## Overview
Collect frontier research materials based on series tracking_sources.yaml configuration.

## Input
- `series_code`: Series code
- `article_filter`: Only collect for specific articles (optional)
- `date_range`: Date range (optional, default: last 7 days)

## Workflow
1. Load series config and tracking sources
2. For each source: call appropriate frontier_research playbook
3. Map materials to articles using blog_mappings
4. Translate and save to materials directory

