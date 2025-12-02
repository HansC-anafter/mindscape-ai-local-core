---
playbook_code: product_breakdown
version: 1.0.0
name: 產品拆解與需求分析
description: 將模糊的產品想法拆解為具體的功能點，識別核心價值主張，並生成結構化產品規格
tags:
  - product
  - design
  - planning
  - requirements

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
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 🎨
---

# Product Breakdown & Requirements Analysis - SOP

## Goal
Help users break down vague product ideas into concrete feature points, identify core value propositions, define user flows, and generate structured product specifications.

## Execution Steps

### Phase 1: Collect Product Ideas and Target Users
- Ask user about their product idea or concept
- Identify target user groups and personas
- Understand the problem the product aims to solve
- Collect any existing documentation or notes

### Phase 2: Identify Core Value Proposition
- Analyze the unique value the product provides
- Compare with existing solutions (if any)
- Define the key differentiators
- Articulate the value proposition clearly

### Phase 3: Break Down Feature Modules
- Decompose the product into major feature modules
- Identify dependencies between modules
- Prioritize features based on value and feasibility
- Define the scope for each module

### Phase 4: Define User Flows
- Map user journeys for key scenarios
- Identify entry points and user actions
- Define the flow between features
- Consider edge cases and error handling

### Phase 5: Generate Feature Specification
- Create structured feature specifications
- Document functional requirements
- Define acceptance criteria
- Generate a comprehensive product specification document

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "entrepreneur", emphasize ROI and market fit
- **Work Style**: If prefers "structured", provide detailed breakdowns
- **Tone Preference**: If prefers "direct", reduce formal language

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Launch MVP in 3 months"), explicitly reference it in responses:
> "Since you're working towards 'Launch MVP in 3 months', I recommend focusing on..."

## Success Criteria
- User understands the product structure
- Clear feature breakdown is established
- User flows are defined
- Comprehensive specification document is generated
