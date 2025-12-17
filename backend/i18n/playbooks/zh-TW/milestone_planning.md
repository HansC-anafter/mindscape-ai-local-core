---
playbook_code: milestone_planning
version: 1.0.0
name: 里程碑規劃與專案時程
description: 規劃關鍵專案里程碑，透過收集專案目標、識別關鍵節點、定義里程碑標準、設定時程，並識別風險和依賴關係
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

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存里程碑計劃
**必須**使用 `sandbox.write_file` 工具保存完整的里程碑計劃（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `milestone_plan.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的里程碑計劃，包含：
  - 專案目標和範圍
  - 關鍵節點識別
  - 里程碑標準定義
  - 時程設定
  - 風險和依賴關係
- 格式: Markdown 格式

#### 步驟 6.2: 保存時間線
**必須**使用 `sandbox.write_file` 工具保存時間線（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `timeline.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 詳細的時間線，包含所有里程碑的目標日期和依賴關係
- 格式: Markdown 格式

## Success Criteria
- Clear project goals and scope are established
- Critical nodes are identified
- Milestone criteria are well-defined
- Realistic timeline is created
- Risks and dependencies are documented
- User has a comprehensive milestone plan document
- All milestone planning documents are saved to files for future reference
