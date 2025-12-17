---
playbook_code: learning_plan
version: 1.0.0
name: 學習計劃創建
description: 創建結構化學習計劃，透過分解學習目標、設計學習路徑、規劃練習方法，並設定里程碑
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
locale: zh-TW
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

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存學習計劃
**必須**使用 `sandbox.write_file` 工具保存完整的學習計劃（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `learning_plan.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的學習計劃，包含：
  - 學習目標
  - 內容分解
  - 學習路徑
  - 練習方法
  - 里程碑和檢查點
- 格式: Markdown 格式

#### 步驟 6.2: 保存課程大綱
**必須**使用 `sandbox.write_file` 工具保存課程大綱（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `curriculum.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 結構化的課程大綱，包含所有模組和主題
- 格式: Markdown 格式

#### 步驟 6.3: 保存學習里程碑
**必須**使用 `sandbox.write_file` 工具保存學習里程碑（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `milestones.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 所有里程碑、檢查點和時間線
- 格式: Markdown 格式

## Success Criteria
- Clear learning objectives are established
- Content is broken down into manageable modules
- Learning path is structured and logical
- Practice methods are defined
- Milestones and checkpoints are set
- User has a comprehensive learning plan document
- All learning plan documents are saved to files for future reference
