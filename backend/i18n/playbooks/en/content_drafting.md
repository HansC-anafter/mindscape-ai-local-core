---
playbook_code: content_drafting
version: 1.0.0
capability_code: content
name: Content / Copy Drafting
description: Help users draft copy, articles, posts, or fundraising page content, including structure, key paragraphs, and tone style
tags:
  - writing
  - content
  - copywriting
  - marketing

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

entry_agent_type: writer
icon: ✍️
---

# Content / Copy Drafting - SOP

## Goal
Help users draft copy, articles, posts, or fundraising page content, including structure, key paragraphs, and suggested tone style.

## Execution Steps

### Phase 1: Understand Requirements
- Ask about target audience and purpose of the content
- Understand content type and format requirements
- Collect key information and points

### Phase 2: Structure Design
- Design overall content architecture (opening, body, conclusion)
- Plan focus and function of each section
- Determine narrative logic and flow

### Phase 3: Content Drafting
- Draft specific content for each section
- Ensure content matches target audience's language habits
- Maintain consistent tone and style

### Phase 4: Optimization Suggestions
- Provide tone and style adjustment suggestions
- Suggest key paragraphs that can be strengthened
- Provide polishing and optimization directions

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "Entrepreneur", emphasize persuasiveness and ROI presentation
- **Tone Preference**: If preferring "direct", reduce decorations and formalities
- **Detail Level**: If preferring "high", provide more technical details and examples

## Integration with Long-term Intents

If the user has relevant Active Intents (e.g., "Complete Fundraising Page Content"), explicitly mention in the response:
> "Since you're working on 'Complete Fundraising Page Content', I would suggest..."

## Success Criteria
- Content structure is clear and complete
- Tone and style match target audience
- User obtains usable draft and optimization suggestions
