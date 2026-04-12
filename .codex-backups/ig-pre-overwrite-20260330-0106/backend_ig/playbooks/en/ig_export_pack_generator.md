---
playbook_code: ig_export_pack_generator
version: 1.0.0
capability_code: instagram
name: IG Export Pack Generator
description: Generate complete export pack for IG Post including post.md, hashtags.txt, CTA variants, and checklist
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
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 📦
---

# IG Export Pack Generator

## Goal

Generate complete export pack for IG Post including post markdown, hashtags text file, CTA variants, and pre-publish checklist.

## Functionality

This Playbook will:

1. **Read Post**: Read post content and frontmatter from Obsidian vault
2. **Get Hashtags**: Generate or use provided hashtags
3. **Scan Assets**: Scan post assets if enabled
4. **Generate Export Pack**: Create complete export pack with all required files

## Use Cases

- Prepare posts for publishing
- Generate export packs for batch publishing
- Create pre-publish checklists
- Package posts with all required assets

## Inputs

- `post_folder`: Post folder path (relative to vault) (required)
- `post_path`: Post markdown file path (relative to vault) (required)
- `vault_path`: Path to Obsidian Vault (required)
- `hashtags`: List of hashtags (if not provided, will be generated)
- `cta_variants`: List of CTA variants (optional)
- `include_assets`: Whether to include assets in checklist (default: true)

## Outputs

- `export_pack_path`: Path to export pack folder
- `files_generated`: List of generated files
- `export_pack`: Export pack content

## Export Pack Contents

1. **post.md**: Post content in markdown format
2. **hashtags.txt**: Hashtags list
3. **cta_variants.txt**: CTA variants
4. **checklist.md**: Pre-publish checklist

## Steps (Conceptual)

1. Read post content and frontmatter
2. Generate or retrieve hashtags
3. Scan assets if enabled
4. Generate export pack with all files

## Notes

- Automatically generates hashtags if not provided
- Includes asset checklist if assets are scanned
- Creates complete export pack ready for publishing

