---
playbook_code: ig_review_system
version: 1.0.0
capability_code: instagram
name: IG Review System
description: Manage review workflow including changelog tracking, review notes, and decision logs
tags:
  - instagram
  - review
  - workflow
  - collaboration

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_review_system_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: 👁️
---

# IG Review System

## Goal

Manage review workflow including changelog tracking, review notes, decision logs, and review status management.

## Functionality

This Playbook will:

1. **Add Changelog**: Add version changelog entry
2. **Add Review Note**: Add review note with priority and status
3. **Add Decision Log**: Add decision log with rationale
4. **Update Review Note Status**: Update review note status
5. **Get Summary**: Get review summary

## Use Cases

- Track post version changes
- Manage review notes and feedback
- Log decisions and rationale
- Track review status

## Inputs

- `action`: Action to perform - "add_changelog", "add_review_note", "add_decision_log", "update_review_note_status", or "get_summary" (required)
- `vault_path`: Path to Obsidian Vault (required)
- `post_path`: Path to post file (required)
- `version`: Version string (required for add_changelog action)
- `changes`: Description of changes (required for add_changelog action)
- `author`: Author name (optional)
- `reviewer`: Reviewer name (required for add_review_note action)
- `note`: Review note content (required for add_review_note action)
- `priority`: Priority level - "high", "medium", or "low" (default: medium)
- `status`: Review status - "pending", "addressed", "resolved", or "rejected" (optional)
- `decision`: Decision description (required for add_decision_log action)
- `rationale`: Rationale for decision (optional)
- `decision_maker`: Decision maker name (optional)
- `note_index`: Index of review note (required for update_review_note_status action)
- `new_status`: New status (required for update_review_note_status action)

## Outputs

- `frontmatter`: Updated frontmatter with review information
- `summary`: Review summary

## Review Status

- **pending**: Review note pending action
- **addressed**: Review note has been addressed
- **resolved**: Review note has been resolved
- **rejected**: Review note has been rejected

## Steps (Conceptual)

1. Add changelog, review note, or decision log
2. Update review note status if needed
3. Get review summary

## Notes

- Supports priority levels for review notes
- Tracks decision rationale
- Maintains review history in frontmatter

