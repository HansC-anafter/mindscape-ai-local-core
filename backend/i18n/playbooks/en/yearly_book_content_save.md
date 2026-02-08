---
playbook_code: yearly_book_content_save
version: 1.0.0
capability_code: obsidian_book
name: Yearly Book Content Save
description: Save external content (OCR results, generated posts, scripts, etc.) to yearly book
tags:
  - journal
  - content-save
  - yearly-book
  - storage

kind: system_tool
interaction_mode:
  - silent
visible_in:
  - workspace_tools_panel
  - console_only

required_tools:
  - yearly_book.save_external_content

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 💾
---

# Yearly Book Content Save

## Goal

Save external content (such as OCR results, generated IG posts, YT scripts, etc.) to yearly book as part of annual knowledge accumulation.

## Functionality

This Playbook will:

1. **Receive External Content**: Accept external content in various formats (text, markdown, etc.)
2. **Organize Content**: Organize content to appropriate location in yearly book based on content type and time
3. **Save Content**: Save content to local file system, integrated into yearly book structure
4. **Record Metadata**: Record content source, type, tags, and other information

## Use Cases

- Save OCR extracted text content
- Save generated IG posts
- Save generated YT scripts
- Save other external content to yearly book

## Inputs

- `external_content`: External content (required)
- `content_type`: Content type (ocr, ig_post, yt_script, article, note, other)
- `year`: Year (default: current year)
- `month`: Month (1-12, default: current month)
- `title`: Content title (optional)
- `source_files`: Source file paths list (optional)
- `tags`: Tags list (optional)
- `metadata`: Additional metadata (optional)

## Outputs

- `saved_entry`: Saved entry information
- `yearly_book_path`: Yearly book file path
- `entry_path`: Saved entry file path

## Steps (Conceptual)

1. Validate input content and parameters
2. Organize content format and location
3. Save content to file system
4. Record metadata and index

## Notes

- Content integration: Saved external content will not automatically integrate into annual yearbook
- File paths: Ensure provided source file paths are valid
- Content format: Content will be saved in markdown format
- Privacy: All content exists only locally, will not be uploaded to cloud












