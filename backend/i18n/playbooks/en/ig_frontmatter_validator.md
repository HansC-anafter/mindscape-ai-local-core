---
playbook_code: ig_frontmatter_validator
version: 1.0.0
name: IG Frontmatter Validator
description: Validate post frontmatter against Unified Frontmatter Schema v2.0.0 and calculate Readiness Score
tags:
  - instagram
  - frontmatter
  - validation
  - schema

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_frontmatter_validator_tool
  - obsidian_read_note

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 📋
capability_code: instagram
---

# IG Frontmatter Validator

## Goal

Validate post frontmatter against Unified Frontmatter Schema v2.0.0 and calculate Readiness Score to assess post publication readiness.

## Functionality

This Playbook will:

1. **Read Post**: Read post file from Obsidian vault
2. **Validate Frontmatter**: Validate frontmatter against schema and calculate readiness score

## Use Cases

- Validate frontmatter before publishing
- Calculate post readiness score
- Identify missing required fields
- Ensure schema compliance

## Inputs

- `post_path`: Path to post Markdown file (relative to vault) (optional)
- `vault_path`: Path to Obsidian Vault (required if post_path provided)
- `frontmatter`: Frontmatter dictionary to validate (alternative to post_path)
- `strict_mode`: Strict mode - all required fields must be present (default: false)
- `domain`: Expected domain - "ig", "wp", "seo", "book", "brand", "ops", or "blog" (optional)

## Outputs

- `is_valid`: Whether frontmatter is valid
- `readiness_score`: Readiness score (0-100)
- `missing_fields`: List of missing required fields
- `warnings`: List of warnings (e.g., v1.0 schema detection)
- `errors`: List of validation errors

## Readiness Score

The readiness score (0-100) indicates how complete the post frontmatter is:
- 100: All required and recommended fields present
- 80-99: All required fields present, some recommended fields missing
- 60-79: Most required fields present
- Below 60: Critical required fields missing

## Steps (Conceptual)

1. Read post file from vault or use provided frontmatter
2. Validate against Unified Frontmatter Schema v2.0.0
3. Calculate readiness score based on field completeness

## Notes

- Supports strict mode for complete validation
- Detects schema version and provides warnings
- Can validate frontmatter directly or from file

