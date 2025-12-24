---
playbook_code: ig_batch_processor
version: 1.0.0
name: IG Batch Processor
description: Manage batch processing of multiple posts including validation, generation, and export operations
tags:
  - instagram
  - batch
  - automation
  - processing

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_batch_processor_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: ⚙️
capability_code: instagram
---

# IG Batch Processor

## Goal

Manage batch processing of multiple IG posts including validation, export pack generation, status updates, and custom operations.

## Functionality

This Playbook will:

1. **Batch Validate**: Validate multiple posts at once
2. **Batch Generate Export Packs**: Generate export packs for multiple posts
3. **Batch Update Status**: Update status for multiple posts
4. **Batch Process**: Execute custom operations on multiple posts

## Use Cases

- Validate multiple posts before publishing
- Generate export packs for batch publishing
- Update post status in bulk
- Execute custom batch operations

## Inputs

- `action`: Action to perform - "batch_validate", "batch_generate_export_packs", "batch_update_status", or "batch_process" (required)
- `vault_path`: Path to Obsidian Vault (required)
- `post_paths`: List of post file paths (relative to vault) (required)
- `strict_mode`: If True, all required fields must be present (default: false)
- `output_folder`: Output folder for export packs (optional)
- `new_status`: New status to set (required for batch_update_status action)
- `operations`: List of operations to perform (required for batch_process action)
- `operation_config`: Configuration for operations (optional)

## Outputs

- `result`: Batch processing results with operation status for each post

## Actions

1. **batch_validate**: Validate multiple posts against frontmatter schema
2. **batch_generate_export_packs**: Generate export packs for multiple posts
3. **batch_update_status**: Update status field for multiple posts
4. **batch_process**: Execute custom operations on multiple posts

## Steps (Conceptual)

1. Process multiple posts based on selected action
2. Execute operation for each post
3. Collect and return results

## Notes

- Supports strict mode for validation
- Can process custom operations via batch_process action
- Returns detailed results for each post

