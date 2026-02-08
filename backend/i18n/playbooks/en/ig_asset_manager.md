---
playbook_code: ig_asset_manager
version: 1.0.0
name: IG Asset Manager
description: Manage IG Post assets with naming validation, size checking, and format validation
tags:
  - instagram
  - assets
  - validation
  - obsidian

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_asset_manager_tool

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

# IG Asset Manager

## Goal

Manage IG Post assets (images, videos) with comprehensive validation including naming rules, size checking, and format validation for different post types (post, carousel, reel, story).

## Functionality

This Playbook will:

1. **Scan Assets**: Scan assets in post folder and extract metadata
2. **Validate Assets**: Validate assets against IG specifications (size, ratio, format)
3. **Generate Asset List**: Generate required asset list based on post type

## Use Cases

- Validate assets before publishing IG posts
- Check asset naming conventions
- Generate required asset lists for new posts
- Verify asset dimensions and file sizes

## Inputs

- `post_folder`: Post folder path (relative to vault) (required)
- `vault_path`: Path to Obsidian Vault (required)
- `post_type`: Post type - "post", "carousel", "reel", or "story" (required)

## Outputs

- `asset_list`: Asset list with metadata including names, sizes, and validation status
- `validation_results`: Detailed validation results for each asset
- `missing_assets`: List of missing required assets
- `size_warnings`: Warnings for assets with incorrect dimensions or file sizes

## Steps (Conceptual)

1. Scan assets in post folder to discover all image/video files
2. Validate assets against IG specifications for the specified post type
3. Generate required asset list based on post type requirements

## Asset Specifications

- **Post/Carousel**: 1080x1080 (1:1), max 8MB
- **Reel/Story**: 1080x1920 (9:16), max 100MB

## Notes

- Asset naming should follow convention: `{post_slug}_{index}.{ext}`
- Supports validation for multiple post types
- Provides detailed warnings for non-compliant assets

