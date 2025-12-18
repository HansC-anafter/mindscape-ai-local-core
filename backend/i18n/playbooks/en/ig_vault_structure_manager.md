---
playbook_code: ig_vault_structure_manager
version: 1.0.0
name: IG Vault Structure Manager
description: Manage Obsidian Vault structure for IG Post workflow. Supports initialization, validation, and content scanning.
tags:
  - instagram
  - obsidian
  - vault
  - structure

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_vault_structure_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 📁
---

# IG Vault Structure Manager

## Goal

Manage standard Obsidian Vault folder structure for IG Post content workflow. Supports initialization, validation, and content scanning.

## Functionality

This Playbook will:

1. **Initialize Structure**: Create standard folder structure for IG Post workflow
2. **Validate Structure**: Check if vault structure matches standard requirements
3. **Scan Content**: Scan vault content and generate index of posts, series, and ideas

## Use Cases

- Set up new Obsidian vault for IG Post workflow
- Validate existing vault structure
- Generate content index for vault management
- Ensure folder structure compliance

## Inputs

- `vault_path`: Path to Obsidian Vault (required)
- `action`: Action to perform - "init", "validate", or "scan" (default: "validate")
- `create_missing`: Whether to create missing folders when validating (default: false)

## Outputs

- `structure_status`: Structure status (initialized, incomplete, valid, etc.)
- `is_valid`: Whether vault structure is valid
- `created_folders`: List of created folders (init action only)
- `missing_folders`: List of missing folders
- `content_index`: Content index with posts, series, and ideas (scan action)
- `post_count`: Number of IG posts found
- `series_count`: Number of series found
- `idea_count`: Number of ideas found

## Standard Folder Structure

- `10-Ideas`: Post ideas and concepts
- `20-Posts`: IG Post content
- `30-Assets`: Post assets (images, videos)
- `40-Series`: Post series organization
- `50-Playbooks`: Playbook templates
- `60-Reviews`: Review and feedback
- `70-Metrics`: Performance metrics
- `90-Export`: Export packs

## Steps (Conceptual)

1. Initialize or validate vault folder structure
2. Check for missing required folders
3. Scan content and generate index (if scan action)

## Notes

- Standard structure ensures consistent organization
- Supports automatic folder creation during validation
- Content scanning provides overview of vault contents

