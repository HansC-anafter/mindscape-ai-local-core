---
playbook_code: draft_article
version: 1.0.0
capability_code: mindscape_book
---
# Draft Article

## Overview
Draft a specific article using series template and collected materials.

## Input
- `series_code`: Series code
- `article_code`: Article code
- `draft_mode`: outline | first_draft | revision

## Workflow
1. Load article configuration and template
2. Load collected materials for this article
3. Load Mindscape AI implementation references
4. Generate draft following 7-section template
5. Save to Obsidian vault

