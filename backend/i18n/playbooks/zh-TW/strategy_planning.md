---
playbook_code: strategy_planning
version: 1.0.0
capability_code: planning
name: 策略規劃與執行
description: 制定商業策略和執行計劃，透過收集商業目標和現狀、分析市場和競爭、識別機會和威脅、定義策略方向，並規劃執行步驟
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
  - core_llm.generate
  - core_llm.structured_extract

language_strategy: model_native
locale: zh-TW
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

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存策略計劃
**必須**使用 `sandbox.write_file` 工具保存完整的策略計劃（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `strategy_plan.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的策略計劃，包含：
  - 商業目標和現狀
  - 市場和競爭分析
  - 機會和威脅識別
  - 策略方向和定位
  - 執行計劃和行動項目
- 格式: Markdown 格式

#### 步驟 6.2: 保存路線圖
**必須**使用 `sandbox.write_file` 工具保存執行路線圖（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `execution_roadmap.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 詳細的路線圖，包含時間線、里程碑和交付物
- 格式: Markdown 格式

#### 步驟 6.3: 保存里程碑
**必須**使用 `sandbox.write_file` 工具保存里程碑計劃（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `milestone_plan.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 所有里程碑、交付物和成功指標
- 格式: Markdown 格式

## Success Criteria
- Business goals and current state are documented
- Market and competition are analyzed
- Opportunities and threats are identified
- Strategy direction is defined
- Execution plan is created
- User has comprehensive strategy document with actionable roadmap
- All strategy documents are saved to files for future reference
