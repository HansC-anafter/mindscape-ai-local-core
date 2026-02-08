---
playbook_code: cross_channel_story
version: 1.0.0
name: Cross-Channel Storyline
description: Generate cross-platform consistent content (website, social media, course, ebook) based on brand storyline
tags:
  - brand
  - content
  - multi-platform
  - storyline
  - content-generation

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.generate
  - core_llm.structured_extract
  - cloud_capability.call

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: content_creator
icon: 📖
---

# 📖 Cross-Channel Storyline

> **The same story axis, presented in different forms on different platforms, but with consistent core message.**

## Goal

Generate cross-platform consistent content based on brand storyline, ensuring core message consistency across all channels.

## Execution Flow

### Step 1: Load Storyline

Load brand storyline data.

### Step 2: Generate Cross-Channel Content

Generate content for multiple platforms (website, social media, course, ebook) based on storyline.

---

## Inputs

- `storyline_data`: Storyline data
- `workspace_id`: Workspace ID
- `channels`: Target platforms (website, social_media, course, ebook)

## Outputs

- `cross_channel_content`: Generated cross-platform content


