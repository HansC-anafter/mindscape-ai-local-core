---
playbook_code: ig_content_reuse
version: 1.0.0
capability_code: instagram
name: IG Content Reuse
description: Manage content transformation and reuse across different IG formats
tags:
  - instagram
  - content-reuse
  - transformation
  - formats

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_content_reuse_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: ♻️
---

# IG Content Reuse

## Goal

Transform and reuse content across different IG formats including article to carousel, carousel to reel, and reel to stories.

## Functionality

This Playbook will:

1. **Article to Carousel**: Transform article content into carousel format
2. **Carousel to Reel**: Transform carousel posts into reel format
3. **Reel to Stories**: Transform reel content into story format

## Use Cases

- Repurpose article content for carousel posts
- Transform carousel posts into reel videos
- Convert reel content into story series
- Maximize content value across formats

## Inputs

- `action`: Action to perform - "article_to_carousel", "carousel_to_reel", or "reel_to_stories" (required)
- `vault_path`: Path to Obsidian Vault (required)
- `source_post_path`: Path to source post (required for article_to_carousel)
- `carousel_posts`: List of carousel post paths (required for carousel_to_reel)
- `source_reel_path`: Path to source reel post (required for reel_to_stories)
- `target_folder`: Target folder for generated posts (required)
- `carousel_slides`: Number of carousel slides (default: 7)
- `slide_structure`: Custom slide structure configuration (optional)
- `reel_duration`: Reel duration in seconds (optional)
- `story_count`: Number of stories to create (default: 3)

## Outputs

- `result`: Transformation result with created posts information

## Transformation Types

1. **article_to_carousel**: Split article into multiple carousel slides
2. **carousel_to_reel**: Combine carousel posts into reel script
3. **reel_to_stories**: Break reel into story series

## Steps (Conceptual)

1. Read source content from vault
2. Transform content based on target format
3. Create new posts in target folder

## Notes

- Supports custom slide structure for carousel
- Can specify reel duration and story count
- Maintains content consistency across formats

