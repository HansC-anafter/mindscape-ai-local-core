---
playbook_code: strategy_planning
version: 1.0.0
name: Strategy Planning & Execution
description: Develop business strategy and execution plan by collecting business goals and current state, analyzing market and competition, identifying opportunities and threats, defining strategy direction, and planning execution steps
tags:
  - strategy
  - planning
  - business
  - execution

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

entry_agent_type: strategist
icon: 🎯
---

# Strategy Planning & Execution - SOP

## Goal
Help users develop business strategy and execution plan by collecting business goals and current state, analyzing market and competition, identifying opportunities and threats, defining strategy direction, and planning execution steps.

## Execution Steps

### Phase 1: Collect Business Goals and Current State
- Gather business objectives and targets
- Understand current business state and performance
- Identify key stakeholders and their expectations
- Collect relevant business metrics and KPIs
- Document constraints and limitations

### Phase 2: Analyze Market and Competition
- Research market conditions and trends
- Analyze competitive landscape
- Identify market opportunities and gaps
- Assess competitive strengths and weaknesses
- Evaluate market positioning

### Phase 3: Identify Opportunities and Threats
- Conduct SWOT analysis (Strengths, Weaknesses, Opportunities, Threats)
- Identify strategic opportunities
- Recognize potential threats and risks
- Assess internal capabilities and resources
- Evaluate external factors and market forces

### Phase 4: Define Strategy Direction
- Formulate strategic objectives and goals
- Define strategic initiatives and priorities
- Establish strategic positioning
- Create value proposition
- Develop strategic themes and focus areas

### Phase 5: Plan Execution Steps
- Break down strategy into actionable initiatives
- Define milestones and deliverables
- Assign responsibilities and resources
- Create timeline and roadmap
- Establish success metrics and KPIs
- Generate comprehensive strategy document

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "business owner", emphasize practical implementation and ROI
- **Work Style**: If prefers "structured", provide detailed roadmaps and milestones
- **Detail Level**: If prefers "high", include more granular analysis and planning

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Grow business revenue"), explicitly reference it in responses:
> "Since you're working towards 'Grow business revenue', this strategy directly supports your goal by..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `market_analysis` - Use market analysis results to inform strategy
- `insight_synthesis` - Use business insights to guide strategy development
- `data_analysis` - Use data analysis to support strategic decisions

### Phase 6: File Generation and Saving

#### Step 6.1: Save Strategy Plan
**Must** use `sandbox.write_file` tool to save complete strategy plan (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `strategy_plan.md` (relative path, relative to sandbox root)
- Content: Complete strategy plan, including:
  - Business goals and current state
  - Market and competition analysis
  - Opportunities and threats identification
  - Strategy direction and positioning
  - Execution plan and action items
- Format: Markdown format

#### Step 6.2: Save Roadmap
**Must** use `sandbox.write_file` tool to save execution roadmap (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `execution_roadmap.md` (relative path, relative to sandbox root)
- Content: Detailed roadmap, including timeline, milestones, and deliverables
- Format: Markdown format

#### Step 6.3: Save Milestones
**Must** use `sandbox.write_file` tool to save milestone plan (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `milestone_plan.md` (relative path, relative to sandbox root)
- Content: All milestones, deliverables, and success metrics
- Format: Markdown format

## Success Criteria
- Business goals and current state are documented
- Market and competition are analyzed
- Opportunities and threats are identified
- Strategy direction is defined
- Execution plan is created
- User has comprehensive strategy document with actionable roadmap

