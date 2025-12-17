---
playbook_code: learning_plan
version: 1.0.0
name: Learning Plan Creation
description: Create structured learning plans by breaking down learning goals, designing learning paths, planning practice methods, and setting milestones
tags:
  - learning
  - education
  - planning
  - coaching

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

entry_agent_type: coach
icon: 📚
---

# Learning Plan Creation - SOP

## Goal
Help users create structured learning plans by collecting learning goals, breaking down content, designing learning paths, planning practice methods, and setting milestones and checkpoints.

## Execution Steps

### Phase 1: Collect Learning Goals and Existing Knowledge
- Ask user about their learning objectives
- Identify current knowledge level and skills
- Understand time constraints and availability
- Collect any relevant background information

### Phase 2: Break Down Learning Content
- Decompose learning goals into manageable topics
- Identify prerequisite knowledge
- Organize content into logical modules
- Determine the scope and depth for each topic

### Phase 3: Design Learning Path
- Create a structured learning sequence
- Identify dependencies between topics
- Plan the progression from basic to advanced
- Consider different learning styles and preferences

### Phase 4: Plan Practice Methods
- Design practice exercises and activities
- Recommend hands-on projects or assignments
- Suggest review and reinforcement strategies
- Plan assessment and self-evaluation methods

### Phase 5: Set Milestones and Checkpoints
- Define key milestones in the learning journey
- Set up checkpoints for progress evaluation
- Create a timeline with realistic deadlines
- Plan for adjustments and course corrections

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "student", emphasize structured progression and deadlines
- **Work Style**: If prefers "structured", provide detailed schedules and checklists
- **Detail Level**: If prefers "high", include more granular breakdowns and resources

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Master Python programming"), explicitly reference it in responses:
> "Since you're working towards 'Master Python programming', I recommend focusing on..."

### Phase 6: File Generation and Saving

#### Step 6.1: Save Learning Plan
**Must** use `sandbox.write_file` tool to save complete learning plan (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `learning_plan.md` (relative path, relative to sandbox root)
- Content: Complete learning plan, including:
  - Learning objectives
  - Content breakdown
  - Learning path
  - Practice methods
  - Milestones and checkpoints
- Format: Markdown format

#### Step 6.2: Save Course Outline
**Must** use `sandbox.write_file` tool to save course outline (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `curriculum.md` (relative path, relative to sandbox root)
- Content: Structured course outline, including all modules and topics
- Format: Markdown format

#### Step 6.3: Save Learning Milestones
**Must** use `sandbox.write_file` tool to save learning milestones (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `milestones.md` (relative path, relative to sandbox root)
- Content: All milestones, checkpoints, and timeline
- Format: Markdown format

## Success Criteria
- Clear learning objectives are established
- Content is broken down into manageable modules
- Learning path is structured and logical
- Practice methods are defined
- Milestones and checkpoints are set
- User has a comprehensive learning plan document

