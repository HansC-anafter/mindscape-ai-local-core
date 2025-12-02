---
playbook_code: yearly_personal_book
version: 1.0.0
name: Create Your Annual Book
description: Organize monthly chapters from this year's Mindscape conversations and notes, then compile into an annual narrative
tags:
  - journal
  - reflection
  - personal
  - annual

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools: []

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 📖
---

# Create Your Annual Book

## Goal

Organize an annual yearbook draft from conversations and notes you left in Mindscape this year.

## Functionality

This Playbook will:

1. **Collect Data**: Extract all conversations and notes from this year in local Mindscape database
2. **Organize by Month**: Group data by month and generate a small chapter for each month
3. **Annual Summary**: Integrate 12 monthly chapters into a complete annual yearbook

## Use Cases

- Annual review and reflection
- Personal growth records
- Knowledge accumulation organization
- Annual summary reports

## Inputs

- `year`: Year to organize (default: current year)

## Outputs

- `annual_markdown`: Complete annual yearbook markdown content
- `monthly_chapters`: List of 12 monthly chapter markdown files

## Steps (Conceptual)

1. Collect annual data (conversations and notes)
2. Group data by month
3. Generate monthly chapters
4. Integrate annual yearbook
5. Save results

## Notes

- Data privacy: All data exists only locally, will not be uploaded to cloud
- Only reads content written to yourself: System only reads your conversations with Mindscape
- Preview and edit: Can preview and edit after generation before deciding to export
- No auto-publish: Will not automatically publish or send to anyone

## Expected Results

- Complete annual yearbook markdown file (annual.md)
- 12 independent monthly chapter files (month-01.md ~ month-12.md)
- Can polish, print, and keep for future self

