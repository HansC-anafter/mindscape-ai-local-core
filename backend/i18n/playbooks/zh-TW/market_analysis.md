---
playbook_code: market_analysis
version: 1.0.0
name: 市場分析與競爭情報
description: 分析市場機會和競爭格局，透過收集市場數據、分析競爭對手、識別市場趨勢、評估機會和風險，並生成市場分析報告
tags:
  - market
  - analysis
  - competition
  - intelligence

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
  - research_synthesis
  - core_llm.structured_extract

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: strategist
icon: 📈
---

# Market Analysis & Competitive Intelligence - SOP

## Goal
Help users analyze market opportunities and competitive landscape by collecting market data, analyzing competitors, identifying market trends, evaluating opportunities and risks, and generating comprehensive market analysis reports.

## Execution Steps

### Phase 1: Collect Market Data
- Gather market research and industry reports
- Collect market size and growth data
- Obtain customer demographics and behavior data
- Collect industry trends and forecasts
- Gather regulatory and policy information

### Phase 2: Analyze Competitors
- Identify key competitors and market players
- Analyze competitor products and services
- Assess competitor strengths and weaknesses
- Evaluate competitor positioning and strategies
- Compare pricing and business models

### Phase 3: Identify Market Trends
- Analyze industry trends and patterns
- Identify emerging technologies and innovations
- Recognize changing customer preferences
- Assess market dynamics and shifts
- Evaluate trend impact and implications

### Phase 4: Evaluate Opportunities and Risks
- Identify market opportunities and gaps
- Assess market entry barriers
- Evaluate competitive advantages
- Recognize potential risks and threats
- Quantify opportunity size and potential

### Phase 5: Generate Market Analysis Report
- Compile all analysis findings
- Create comprehensive market analysis report with:
  - Executive summary
  - Market overview and size
  - Competitive landscape analysis
  - Market trends and dynamics
  - Opportunities and risks assessment
  - Strategic recommendations
- Provide actionable market intelligence

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "business strategist", emphasize strategic implications and positioning
- **Work Style**: If prefers "structured", provide detailed competitive analysis
- **Detail Level**: If prefers "high", include more granular market segmentation

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Enter new market"), explicitly reference it in responses:
> "Since you're working towards 'Enter new market', this analysis identifies key opportunities and risks for market entry..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `research_synthesis` - Use research synthesis to inform market analysis
- `strategy_planning` - Use market analysis to inform strategy development
- `insight_synthesis` - Combine market insights with business insights

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存市場分析報告
**必須**使用 `sandbox.write_file` 工具保存完整的市場分析報告（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `market_analysis_report.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的市場分析報告，包含：
  - 執行摘要
  - 市場概述和規模
  - 競爭格局分析
  - 市場趨勢和動態
  - 機會和風險評估
  - 策略建議
- 格式: Markdown 格式

#### 步驟 6.2: 保存競爭分析
**必須**使用 `sandbox.write_file` 工具保存競爭分析（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `competitive_analysis.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 詳細的競爭對手分析和比較
- 格式: Markdown 格式

## Success Criteria
- Market data is collected and organized
- Competitors are analyzed
- Market trends are identified
- Opportunities and risks are evaluated
- Comprehensive market analysis report is generated
- User has clear market intelligence and strategic recommendations
