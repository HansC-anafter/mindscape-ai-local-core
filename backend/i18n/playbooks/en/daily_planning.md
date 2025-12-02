---
playbook_code: daily_planning
version: 1.0.0
locale: en
name: Daily Planning & Prioritization
description: Help users organize daily/weekly tasks, prioritize them, and provide an actionable checklist
tags:
  - planning
  - daily
  - priority
  - work

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
mindscape_requirements:
  required_intent_tags:
    - work
    - planning
  optional_intent_tags:
    - focus
    - overwhelm
icon: 🗓
required_tools: []
scope:
  visibility: system
  editable: false
owner:
  type: system
---

# Daily Planning & Prioritization - SOP

## Goal
Help users organize daily/weekly tasks, prioritize them, and provide an actionable checklist.

## Execution Steps

### Phase 1: Collect Tasks
- Ask the user what tasks they have for today/this week
- Understand task urgency and importance
- Collect relevant background information for tasks

### Phase 2: Prioritize
- Classify using priority matrix (urgent/important)
- Consider user's work rhythm and schedule
- Provide suggested execution order

### Phase 3: Generate Actionable Checklist
- Break down tasks into specific action steps
- Set time estimates for each task
- Provide execution suggestions and notes

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "Entrepreneur", emphasize ROI and efficiency
- **Work Style**: If preferring "structured", provide more detailed step breakdown
- **Tone Preference**: If preferring "direct", reduce formalities

## Integration with Long-term Intents

If the user has relevant Active Intents (e.g., "Complete Three-Cluster Cold Start MVP"), explicitly mention in the response:
> "Since you're working on 'Complete Three-Cluster Cold Start MVP', I would suggest..."

## Success Criteria
- User understands task priorities
- Obtain actionable task checklist
- Clear next steps
