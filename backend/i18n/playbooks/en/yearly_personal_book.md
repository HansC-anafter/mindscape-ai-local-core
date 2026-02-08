---
playbook_code: yearly_personal_book
version: 1.0.0
capability_code: obsidian_book
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

required_tools:
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file

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

### Stage 6: File Generation and Saving

#### Step 6.1: Save Annual Book Content
**Must** use `sandbox.write_file` tool to save annual book content (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `yearly_book_content.md` (relative path, relative to sandbox root)
- Content: Complete annual yearbook content
- Format: Markdown format

#### Step 6.2: Save Chapter Outline
**Must** use `sandbox.write_file` tool to save chapter outline (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `chapters_outline.md` (relative path, relative to sandbox root)
- Content: 12 monthly chapter outlines and structure
- Format: Markdown format

#### Step 6.3: Save Monthly Chapters (if generated)
If monthly chapters have been generated, **must** use `sandbox.write_file` tool to save (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `month-{01-12}.md` (relative path, relative to sandbox root, e.g., `month-01.md`, `month-02.md`, etc.)
- Content: Independent chapter content for each month
- Format: Markdown format

## Expected Results

- Complete annual yearbook markdown file (yearly_book_content.md)
- 12 independent monthly chapter files (month-01.md ~ month-12.md)
- Chapter outline file (chapters_outline.md)
- Can polish, print, and keep for future self
- All files saved to sandbox for subsequent use












