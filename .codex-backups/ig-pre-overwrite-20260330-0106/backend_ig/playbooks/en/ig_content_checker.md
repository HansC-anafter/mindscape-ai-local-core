---
playbook_code: ig_content_checker
version: 1.0.0
capability_code: instagram
name: IG Content Checker
description: Check IG Post content for compliance issues including medical/investment claims, copyright, personal data, and brand tone
tags:
  - instagram
  - compliance
  - content-safety
  - validation

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_content_checker_tool
  - obsidian_read_note

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: ✅
---

# IG Content Checker

## Goal

Check IG Post content for compliance issues including medical/investment claims, copyright infringement, personal data exposure, and brand tone violations.

## Functionality

This Playbook will:

1. **Read Post**: Read post content from Obsidian vault or use provided content
2. **Check Content**: Perform comprehensive compliance checks on content

## Use Cases

- Pre-publish content compliance checking
- Identify potential legal risks
- Ensure brand tone consistency
- Detect personal data exposure

## Inputs

- `content`: Post content text to check (optional if post_path provided)
- `post_path`: Path to post Markdown file (relative to vault, optional if content provided)
- `vault_path`: Path to Obsidian Vault (required if post_path provided)
- `frontmatter`: Post frontmatter (optional)

## Outputs

- `risk_flags`: Risk flags found (醫療, 投資, 侵權, 個資)
- `warnings`: List of warnings
- `checks`: Detailed check results for each category
- `is_safe`: Whether content is safe (no risk flags)

## Check Categories

1. **Medical Claims**: Detect medical treatment claims and health-related keywords
2. **Investment Claims**: Detect investment advice and financial promises
3. **Copyright**: Detect copyright-related keywords and potential infringement
4. **Personal Data**: Detect personal information patterns (phone, email, ID)
5. **Brand Tone**: Check for negative brand tone keywords

## Steps (Conceptual)

1. Read post content from vault or use provided content
2. Perform compliance checks across all categories
3. Generate risk flags and warnings

## Notes

- Provides detailed warnings for each risk category
- Can check content directly or from Obsidian vault
- Supports both content string and file path inputs

