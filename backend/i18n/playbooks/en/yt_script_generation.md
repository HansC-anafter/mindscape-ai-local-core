---
playbook_code: yt_script_generation
version: 1.0.0
name: YT Video Script Generation
description: Generate YouTube video scripts from content, optimized for YT format (timestamps, structure, key points, etc.)
tags:
  - youtube
  - video
  - script
  - content-creation

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.generate

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 🎬
---

# YT Video Script Generation

## Goal

Generate YouTube video scripts from source content (such as OCR results, articles, etc.), optimized for YT platform features including timestamp annotations, structured content, and key point highlights.

## Functionality

This Playbook will:

1. **Analyze Content**: Extract key topics and points from source content
2. **Plan Script Structure**: Design intro, main body, and outro structure
3. **Generate Script Content**: Create complete video script for specified duration
4. **Add Timestamps**: Annotate important sections with timestamps (if needed)

## Use Cases

- Convert long articles into YT video scripts
- Generate video content from research reports
- Convert notes into YT scripts
- Batch script generation for content creation

## Inputs

- `source_content`: Source content (required)
- `duration_minutes`: Video duration in minutes (default: 5)
- `script_type`: Script type (educational, tutorial, review, storytelling, interview)
- `tone`: Tone style (engaging, professional, casual, energetic, calm)
- `include_timestamps`: Include timestamp annotations (default: true)

## Outputs

- `script`: Complete video script (structured object)
- `script_markdown`: Markdown format script (better readability)

## Steps (Conceptual)

1. Analyze source content to extract key topics
2. Plan script structure (intro, main body, outro)
3. Generate script content with timestamp annotations
4. Optimize content to match YT platform features

## Examples

**Input**:
- Source content: An article about AI technology
- Duration: 5 minutes
- Script type: educational

**Output**:
- Complete YT video script with timestamps and structured content

## Notes

- Duration control: Generated script duration is an estimate, actual recording may vary
- Speaking speed: Script length based on average speaking speed (approximately 150-160 words/minute)
- Visual elements: Script does not include visual elements, but can suggest suitable visuals
- Copyright: If source content has copyright restrictions, please note usage scope

