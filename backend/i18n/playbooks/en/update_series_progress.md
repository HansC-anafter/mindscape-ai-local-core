---
playbook_code: update_series_progress
version: 1.0.0
capability_code: mindscape_book
---
# Update Series Progress

## Overview
Check and update series progress, generate progress report with recommendations.

## Input
- `series_code`: Series code

## Workflow
1. Load series configuration
2. Check each article: draft existence, word count, materials count
3. Update article statuses in config
4. Generate progress report with recommendations

