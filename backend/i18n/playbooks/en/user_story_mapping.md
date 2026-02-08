---
playbook_code: user_story_mapping
version: 1.0.0
capability_code: planning
name: User Story Mapping
description: Map product features to user stories by collecting user roles and scenarios, generating user stories (As a... I want... So that...), mapping features to stories, prioritizing, and generating a story map
tags:
  - product
  - design
  - planning
  - user_story

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
  - core_llm.generate
  - core_llm.structured_extract

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 🗺️
---

# User Story Mapping - SOP

## Goal
Help users map product features to user stories by collecting user roles and scenarios, generating user stories in the standard format (As a... I want... So that...), mapping features to stories, prioritizing them, and generating a comprehensive story map.

## Execution Steps

### Phase 1: Collect User Roles and Scenarios
- Ask user about the different user roles or personas for the product
- Identify key scenarios and use cases for each role
- Understand user goals and motivations
- Collect any existing user research or persona documentation

### Phase 2: Generate User Stories
- Create user stories in the standard format: "As a [role], I want [action] so that [benefit]"
- Generate stories for each identified user role
- Cover different scenarios and use cases
- Ensure stories are specific, measurable, and user-focused

### Phase 3: Map Features to Stories
- Identify product features or functionality
- Map each feature to relevant user stories
- Create relationships between features and stories
- Identify features that serve multiple stories
- Highlight stories that require multiple features

### Phase 4: Prioritize Stories
- Evaluate stories based on user value and business impact
- Consider dependencies between stories
- Apply prioritization frameworks (e.g., MoSCoW, Value vs. Effort)
- Organize stories into priority tiers (Must Have, Should Have, Could Have, Won't Have)
- Consider user journey and story sequencing

### Phase 5: Generate Story Map
- Organize stories into a structured story map
- Group stories by user activities or themes
- Arrange stories horizontally by user journey flow
- Arrange stories vertically by priority or release planning
- Create a visual representation of the story map
- Document story dependencies and relationships

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "product manager", emphasize business value and ROI
- **Work Style**: If prefers "structured", provide detailed story breakdowns and dependencies
- **Detail Level**: If prefers "high", include more granular story details and acceptance criteria

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Launch product MVP"), explicitly reference it in responses:
> "Since you're working towards 'Launch product MVP', I recommend focusing on Must Have stories that deliver core value..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `product_breakdown` - Use product breakdown results to inform feature-to-story mapping
- `milestone_planning` - Use story priorities to inform milestone planning

### Phase 6: File Generation and Saving

#### Step 6.1: Save User Story Map
**Must** use `sandbox.write_file` tool to save user story map (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `user_story_map.md` (relative path, relative to sandbox root)
- Content: Complete user story map, including all stories, priorities, and relationships
- Format: Markdown format

#### Step 6.2: Save Story Breakdown
**Must** use `sandbox.write_file` tool to save story breakdown (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `story_breakdown.md` (relative path, relative to sandbox root)
- Content: Detailed story breakdown, including feature mapping and dependencies
- Format: Markdown format

## Success Criteria
- User roles and scenarios are clearly identified
- User stories are generated in standard format
- Features are mapped to relevant stories
- Stories are prioritized based on value and impact
- A comprehensive story map is generated
- User has a clear understanding of feature-to-story relationships

