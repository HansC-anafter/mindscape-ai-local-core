---
playbook_code: insight_synthesis
version: 1.0.0
name: 洞察綜合與商業智慧
description: 從數據中提取商業洞察，透過綜合多個數據來源、識別關鍵洞察、連結商業影響、生成行動建議，並創建洞察報告
tags:
  - insights
  - synthesis
  - business
  - intelligence

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

entry_agent_type: analyst
icon: 💡
---

# Insight Synthesis & Business Intelligence - SOP

## Goal
Help users extract business insights from data by synthesizing multiple data sources, identifying key insights, linking business impact, generating action recommendations, and creating comprehensive insight reports.

## Execution Steps

### Phase 1: Synthesize Multiple Data Sources
- Collect data from multiple sources (analysis reports, metrics, trends)
- Integrate findings from different data sets
- Identify connections and relationships between data sources
- Resolve contradictions or conflicting information
- Build comprehensive data picture

### Phase 2: Identify Key Insights
- Analyze synthesized data to identify key insights
- Extract actionable findings and observations
- Identify patterns and trends across sources
- Recognize opportunities and risks
- Highlight critical business implications

### Phase 3: Link Business Impact
- Connect insights to business objectives and goals
- Assess impact on key business metrics
- Evaluate potential business value or risk
- Identify affected business areas or processes
- Quantify potential impact where possible

### Phase 4: Generate Action Recommendations
- Create prioritized action recommendations
- Link recommendations to specific insights
- Provide implementation guidance
- Estimate effort and expected outcomes
- Create action plan with timelines

### Phase 5: Generate Insight Report
- Compile all synthesis findings
- Create comprehensive insight report with:
  - Executive summary
  - Data synthesis overview
  - Key insights and findings
  - Business impact analysis
  - Action recommendations and priorities
  - Implementation roadmap
- Provide clear, actionable business intelligence

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "business strategist", emphasize strategic implications and long-term impact
- **Work Style**: If prefers "structured", provide detailed action plans and roadmaps
- **Detail Level**: If prefers "high", include more granular impact analysis and recommendations

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Improve business performance"), explicitly reference it in responses:
> "Since you're working towards 'Improve business performance', these insights directly support your goal by..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `data_analysis` - Use analysis results as input for insight synthesis
- `strategy_planning` - Use insights to inform strategy development
- `market_analysis` - Combine with market insights for comprehensive view

## Success Criteria
- Multiple data sources are synthesized
- Key insights are identified
- Business impact is linked and assessed
- Action recommendations are generated
- Comprehensive insight report is created
- User has clear, actionable business intelligence
