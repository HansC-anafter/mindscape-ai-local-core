---
playbook_code: ig_post_generation
version: 1.0.0
name: IG Post Generation
description: Generate Instagram posts from content, optimized for IG platform features (character limits, hashtags, tone, etc.)
tags:
  - social-media
  - instagram
  - content-creation
  - marketing

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.analyze
  - core_llm.generate

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 📱
---

# IG Post Generation

## Goal

Generate multiple Instagram posts from source content (such as OCR text, articles, notes, etc.), optimized for IG platform features including character limits, hashtag usage, tone adjustments, etc.

## Functionality

This Playbook will:

1. **Analyze Content**: Extract key topics and points from source content
2. **Generate Posts**: Generate multiple posts in IG format based on topics
3. **Optimize Format**: Automatically add hashtags, adjust tone, comply with character limits

## Use Cases

- Convert long articles into multiple IG posts
- Generate social media content from research reports
- Convert notes into IG content
- Batch post generation for content marketing

## Inputs

- `source_content`: Source content (required)
- `post_count`: Number of posts to generate (default: 5)

## Outputs

- `ig_posts`: Generated IG post list, each containing:
  - `text`: Post text content
  - `hashtags`: Relevant hashtag list

## Steps (Conceptual)

1. Analyze source content to extract key topics
2. Generate specified number of IG posts based on topics
3. Add appropriate hashtags to each post
4. Optimize text to match IG platform features

## Examples

**Input**:
- Source content: An article about AI technology
- Post count: 5

**Output**:
- 5 IG posts, each containing text and hashtags

## Notes

- IG post recommended character limit: 2200 characters
- Automatically adds relevant hashtags
- Generated content may require manual review and adjustment
- Supports multi-language content generation

