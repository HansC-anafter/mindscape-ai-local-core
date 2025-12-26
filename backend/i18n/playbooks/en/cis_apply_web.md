---
playbook_code: cis_apply_web
version: 1.0.0
name: Apply: Website Generation
description: Generate website based on CIS Lens
tags:
  - brand
  - website
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
  - filesystem_write_file

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: content_creator
icon: 🌐
---

# 🌐 Apply: Website Generation

> **Generate website that matches brand visual and tone based on Brand Lens.**

## Goal

Use established Brand Lens to generate website specifications and content that match brand identity.

## Execution Flow

### Step 1: Load Brand Lens

Load the Brand Lens for the workspace.

### Step 2: Generate Website Specification

Generate website specification based on Brand Lens and website requirements.

### Step 3: Generate Website Content

Generate website content based on Brand Lens, ensuring it matches brand visual and tone.

---

## Inputs

- `lens_id`: Brand Lens ID
- `workspace_id`: Workspace ID
- `website_requirements`: Website requirements (optional)

## Outputs

- `website_spec`: Generated website specification


