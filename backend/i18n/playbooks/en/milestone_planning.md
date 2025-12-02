---
playbook_code: milestone_planning
version: 1.0.0
name: Milestone Planning & Project Timeline
description: Plan key project milestones by collecting project goals, identifying critical nodes, defining milestone criteria, setting timelines, and identifying risks and dependencies
tags:
  - planning
  - project
  - milestone
  - timeline

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
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
icon: 🎯
---

# Milestone Planning & Project Timeline - SOP

## Goal
Help users plan key project milestones by collecting project goals and scope, identifying critical nodes, defining milestone criteria, setting timelines, and identifying risks and dependencies.

## Execution Steps

### Phase 1: Collect Project Goals and Scope
- Ask user about project objectives and expected outcomes
- Understand project scope and boundaries
- Identify key stakeholders and their expectations
- Collect any existing project documentation

### Phase 2: Identify Critical Nodes
- Analyze project structure to find critical decision points
- Identify key deliverables and checkpoints
- Recognize dependencies between tasks
- Map out the project flow

### Phase 3: Define Milestone Criteria
- Establish clear criteria for each milestone
- Define success metrics and acceptance criteria
- Set quality standards and requirements
- Create measurable checkpoints

### Phase 4: Set Timeline
- Estimate duration for each milestone
- Create a realistic timeline with buffer time
- Identify critical path and dependencies
- Set target dates for each milestone

### Phase 5: Identify Risks and Dependencies
- Analyze potential risks for each milestone
- Identify external dependencies
- Assess resource requirements
- Plan mitigation strategies
- Document assumptions and constraints

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "project manager", emphasize stakeholder communication and risk management
- **Work Style**: If prefers "structured", provide detailed milestone breakdowns
- **Detail Level**: If prefers "high", include more granular risk analysis

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Launch product MVP"), explicitly reference it in responses:
> "Since you're working towards 'Launch product MVP', I recommend setting milestones around..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `project_breakdown` - Use project breakdown results to inform milestone planning
- `daily_planning` - Convert milestones into daily/weekly tasks

## Success Criteria
- Clear project goals and scope are established
- Critical nodes are identified
- Milestone criteria are well-defined
- Realistic timeline is created
- Risks and dependencies are documented
- User has a comprehensive milestone plan document

