---
playbook_code: ig_interaction_templates
version: 1.0.0
name: IG Interaction Templates
description: Manage interaction templates including common comment replies, DM scripts, and tone switching
tags:
  - instagram
  - templates
  - interaction
  - automation

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_interaction_templates_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: 💬
capability_code: instagram
---

# IG Interaction Templates

## Goal

Manage interaction templates for common comment replies, DM scripts, and story replies with support for tone switching and variable rendering.

## Functionality

This Playbook will:

1. **Create Template**: Create new interaction template
2. **Get Template**: Retrieve template by ID
3. **List Templates**: List templates with filtering
4. **Render Template**: Render template with variables
5. **Suggest Template**: Suggest template based on context
6. **Switch Tone**: Switch template tone
7. **Update Template**: Update existing template

## Use Cases

- Create reusable comment reply templates
- Manage DM scripts for common scenarios
- Switch template tone for different contexts
- Automate interaction responses

## Inputs

- `action`: Action to perform - "create", "get", "list", "render", "suggest", "switch_tone", or "update" (required)
- `vault_path`: Path to Obsidian Vault (required)
- `template_id`: Template identifier (required for get, render, switch_tone, update)
- `template_type`: Type of template - "comment_reply", "dm_script", or "story_reply" (optional)
- `content`: Template content with {{variable}} placeholders (required for create)
- `tone`: Tone - "friendly", "professional", "casual", or "formal" (optional)
- `category`: Category (e.g., 'greeting', 'product_inquiry', 'complaint') (optional)
- `tags`: List of tags for categorization (optional)
- `variables`: List of variable names used in template (optional)
- `render_variables`: Dictionary of variable values for rendering (required for render)
- `context`: Context description for template suggestion (required for suggest)
- `new_tone`: New tone for switch_tone action (required for switch_tone)
- `updates`: Dictionary of fields to update (required for update)

## Outputs

- `template`: Template information
- `templates`: List of templates
- `rendered_content`: Rendered template content
- `suggested_template`: Suggested template based on context

## Template Types

- **comment_reply**: Templates for comment responses
- **dm_script**: Templates for direct message scripts
- **story_reply**: Templates for story responses

## Steps (Conceptual)

1. Create, retrieve, or list templates
2. Render templates with variables if needed
3. Switch tone or update templates as required

## Notes

- Supports variable placeholders in templates
- Can suggest templates based on context
- Supports tone switching for different scenarios

