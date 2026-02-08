---
playbook_code: cis_apply_visual
version: 1.0.0
name: Apply: Visual Assets
description: Generate posters, presentations, and banners based on CIS Lens
tags:
  - brand
  - visual
  - poster
  - presentation
  - banner
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
icon: 🎨
---

# 🎨 Apply: Visual Assets

> **Generate posters, presentations, and banners that match brand visual identity based on Brand Lens.**

## Goal

Use established Brand Lens to generate various visual assets that match brand visual identity.

## Execution Flow

### Step 1: Load Brand Lens

Load the Brand Lens for the workspace.

### Step 2: Generate Visual Specification

Generate visual specification based on Brand Lens and visual type, ensuring it matches brand visual identity.

---

## Inputs

- `lens_id`: Brand Lens ID
- `workspace_id`: Workspace ID
- `visual_type`: Visual asset type (poster, presentation, banner, social_media_image)
- `visual_requirements`: Visual requirements (optional)

## Outputs

- `visual_spec`: Generated visual specification


