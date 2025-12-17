---
playbook_code: user_story_mapping
version: 1.0.0
name: 使用者故事映射
description: 將產品功能映射到使用者故事，透過收集使用者角色和情境、生成使用者故事（作為...我想要...以便...）、將功能映射到故事、優先排序，並生成故事地圖
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
locale: zh-TW
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

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存用戶故事地圖
**必須**使用 `sandbox.write_file` 工具保存用戶故事地圖（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `user_story_map.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的用戶故事地圖，包含所有故事、優先級和關係
- 格式: Markdown 格式

#### 步驟 6.2: 保存故事分解
**必須**使用 `sandbox.write_file` 工具保存故事分解（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `story_breakdown.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 詳細的故事分解，包含功能映射和依賴關係
- 格式: Markdown 格式

## Success Criteria
- User roles and scenarios are clearly identified
- User stories are generated in standard format
- Features are mapped to relevant stories
- Stories are prioritized based on value and impact
- A comprehensive story map is generated
- All story mapping documents are saved to files for future reference
- User has a clear understanding of feature-to-story relationships
