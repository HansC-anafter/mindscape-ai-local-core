---
playbook_code: cis_apply_content
version: 1.0.0
name: "Apply: Content Generation"
description: Generate copywriting, blog, and social media content based on CIS Lens
tags:
  - brand
  - content
  - copywriting
  - blog
  - social-media
  - cis-application
  - lens

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - cloud_capability.call
  - core_llm.generate

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: content_creator
icon: ✍️
capability_code: brand_identity
---

# ✍️ Apply: Content Generation

> **Generate copywriting, blog, and social media content that matches brand tone based on Brand Lens.**

## Goal

Use established Brand Lens to generate various content that matches brand identity.

## Execution Flow

### Step 1: Load Brand Lens

Load the Brand Lens for the workspace.

### Step 2: Generate Content

Generate content based on Brand Lens and content type, ensuring it matches brand tone.

---

## Inputs

- `lens_id`: Brand Lens ID
- `workspace_id`: Workspace ID
- `content_type`: Content type (blog, social_media, copywriting, article)
- `content_topic`: Content topic (optional)

## Outputs

- `generated_content`: Generated content







