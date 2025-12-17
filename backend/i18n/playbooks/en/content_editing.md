---
playbook_code: content_editing
version: 1.0.0
name: Content Editing & Optimization
description: Edit and optimize content quality by analyzing content structure and logic, checking tone and style consistency, improving readability, checking brand guidelines, and generating editing suggestions
tags:
  - editing
  - content
  - optimization
  - quality

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
  - review.suggest
  - core_llm.generate
optional_tools:
  - voice_recording.transcribe

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: editor
icon: ✏️
---

# Content Editing & Optimization - SOP

## Goal
Help users edit and optimize content quality by analyzing content structure and logic, checking tone and style consistency, improving readability, checking brand guidelines, and generating comprehensive editing suggestions and optimized versions.

## Execution Steps

### Phase 1: Analyze Content Structure and Logic
- Extract text from content files or receive text input
- Analyze overall content structure and organization
- Check logical flow and coherence
- Identify structural issues (missing sections, unclear transitions)
- Evaluate content hierarchy and organization

### Phase 2: Check Tone and Style Consistency
- Analyze tone throughout the content
- Check style consistency (formal vs. informal, technical vs. accessible)
- Identify tone shifts or inconsistencies
- Verify alignment with target audience
- Check for brand voice compliance

### Phase 3: Optimize Readability
- Analyze sentence length and complexity
- Check paragraph structure and length
- Improve clarity and conciseness
- Enhance flow and transitions
- Optimize vocabulary for target audience

### Phase 4: Check Brand Guidelines
- Review content against brand guidelines (if provided)
- Check terminology and naming conventions
- Verify brand voice and messaging alignment
- Ensure compliance with style guide
- Identify any brand guideline violations

### Phase 5: Generate Editing Suggestions
- Compile all analysis findings
- Generate prioritized editing suggestions
- Create optimized version of content
- Provide before/after comparisons for key changes
- Generate editing checklist

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "content creator", emphasize engagement and readability
- **Work Style**: If prefers "structured", provide detailed editing checklists
- **Detail Level**: If prefers "high", include more granular editing suggestions

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Improve content quality"), explicitly reference it in responses:
> "Since you're working towards 'Improve content quality', I recommend focusing on..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `content_analysis` - Use analysis results to inform editing priorities
- `seo_optimization` - Apply SEO optimizations during editing
- `publishing_workflow` - Prepare content for publishing after editing

## Integration with Voice Recording

If content includes audio files or requires audio analysis:
- Use `voice_recording.transcribe` to transcribe audio content for editing
- Analyze transcribed text for consistency with written content
- Ensure audio and written content alignment

### Phase 6: File Generation and Saving

#### Step 6.1: Save Edited Content
**Must** use `sandbox.write_file` tool to save edited content (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `edited_content.md` (relative path, relative to sandbox root)
- Content: Optimized complete content
- Format: Markdown format

#### Step 6.2: Save Editing Notes
**Must** use `sandbox.write_file` tool to save editing notes (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `editing_notes.md` (relative path, relative to sandbox root)
- Content: All editing suggestions, improvement notes, and before/after comparisons
- Format: Markdown format

## Success Criteria
- Content structure and logic are analyzed
- Tone and style consistency are verified
- Readability is optimized
- Brand guidelines are checked
- Comprehensive editing suggestions are generated
- Optimized version of content is provided
- User has clear editing checklist and priorities

