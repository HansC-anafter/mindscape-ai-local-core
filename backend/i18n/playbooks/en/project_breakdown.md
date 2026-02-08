---
playbook_code: project_breakdown
version: 1.0.0
capability_code: planning
locale: en
name: Project Breakdown & Milestones
description: Help users break down projects into phases and milestones, identify risks, and provide next-step action recommendations
tags:
  - planning
  - project
  - milestone
  - strategy

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
    - project
    - planning
  optional_intent_tags:
    - milestone
    - risk
icon: 📦
required_tools:
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file
scope:
  visibility: system
  editable: false
owner:
  type: system
---

# Project Breakdown & Milestones - SOP

## Goal
Help users break down projects into phases and milestones, identify risk points, and provide next-step action recommendations.

## Execution Steps

### Phase 1: Understand Project Overview
- Ask about the project's core goals and expected outcomes
- Understand project timeline and resource constraints
- Identify key stakeholders and dependencies

### Phase 2: Phase Division
- Break down the project into major phases
- Define clear deliverables for each phase
- Identify dependencies between phases

### Phase 3: Milestone Setting
- Set key milestones for each phase
- Define acceptance criteria for milestones
- Mark time points for each milestone

### Phase 4: Risk Identification
- Identify potential risks for each phase
- Assess risk impact and probability
- Provide risk mitigation recommendations

### Phase 5: Next Steps
- Provide specific action recommendations for the current phase
- List tasks that need immediate attention
- Provide resource and time estimates

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "System Architect", provide more technical breakdown approach
- **Domain**: If involving "multi-cluster architecture", emphasize technical risks and dependencies
- **Work Style**: If preferring "experimental", allow more flexible milestone adjustments

## Integration with Long-term Intents

If the user has relevant Active Intents, explicitly mention in the response:
> "Since you're working on 'Complete Three-Cluster Cold Start MVP', I would suggest dividing the project into three phases..."

### Phase 6: File Generation and Saving

#### Step 6.1: Save Project Structure
**Must** use `sandbox.write_file` tool to save project structure (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `project_structure.md` (relative path, relative to sandbox root)
- Content: Complete project structure, including all phases, deliverables, and dependencies
- Format: Markdown format

#### Step 6.2: Save Task Breakdown
**Must** use `sandbox.write_file` tool to save task breakdown (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `task_breakdown.md` (relative path, relative to sandbox root)
- Content: Detailed task breakdown, including specific tasks and action items for each phase
- Format: Markdown format

#### Step 6.3: Save Timeline
**Must** use `sandbox.write_file` tool to save timeline (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `timeline.md` (relative path, relative to sandbox root)
- Content: Project timeline, including time points and acceptance criteria for all milestones
- Format: Markdown format

#### Step 6.4: Save Risk Analysis (if applicable)
If risks are identified, **must** use `sandbox.write_file` tool to save (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `risk_analysis.md` (relative path, relative to sandbox root)
- Content: Risk identification and mitigation recommendations
- Format: Markdown format

## Success Criteria
- Project is clearly broken down into phases and milestones
- Risk points are identified with mitigation plans
- User clearly knows the next steps
