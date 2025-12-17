---
playbook_code: data_analysis
version: 1.0.0
name: 數據分析與趨勢識別
description: 分析數據並識別趨勢，透過收集數據和指標、識別數據模式、分析趨勢和異常、計算關鍵指標，並生成分析報告
tags:
  - data
  - analysis
  - trends
  - metrics

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
  - core_files.extract_text
  - core_llm.structured_extract

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: analyst
icon: 📊
---

# Data Analysis & Trend Identification - SOP

## Goal
Help users analyze data and identify trends by collecting data and metrics, identifying data patterns, analyzing trends and anomalies, calculating key metrics, and generating comprehensive analysis reports.

## Execution Steps

### Phase 1: Collect Data and Metrics
- Ask user to provide data files (CSV, Excel, JSON, or text)
- Extract data from files using appropriate parsers
- Understand data structure and format
- Identify available metrics and dimensions
- Verify data completeness and quality

### Phase 2: Identify Data Patterns
- Analyze data structure and relationships
- Identify patterns in the data (seasonal, cyclical, trends)
- Detect correlations between variables
- Recognize data distributions and outliers
- Map data relationships and dependencies

### Phase 3: Analyze Trends and Anomalies
- Identify trends over time (if time-series data)
- Detect anomalies and outliers
- Analyze changes and variations
- Compare different time periods or segments
- Highlight significant changes or deviations

### Phase 4: Calculate Key Metrics
- Compute relevant statistical metrics (mean, median, mode, standard deviation)
- Calculate growth rates and percentages
- Compute ratios and proportions
- Generate summary statistics
- Calculate performance indicators

### Phase 5: Generate Analysis Report
- Compile all analysis findings
- Create structured analysis report with:
  - Executive summary
  - Data overview and quality assessment
  - Pattern identification results
  - Trend analysis and anomalies
  - Key metrics and statistics
  - Insights and observations
  - Recommendations (if applicable)
- Provide visualizations descriptions (charts, graphs)

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "business analyst", emphasize business metrics and KPIs
- **Work Style**: If prefers "structured", provide detailed statistical breakdowns
- **Detail Level**: If prefers "high", include more granular analysis and calculations

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Improve business performance"), explicitly reference it in responses:
> "Since you're working towards 'Improve business performance', I recommend focusing on metrics that directly impact your goals..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `insight_synthesis` - Use analysis results to extract business insights
- `strategy_planning` - Use data analysis to inform strategy decisions

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存分析報告
**必須**使用 `filesystem_write_file` 工具保存完整的數據分析報告：

- 文件路徑: `data_analysis_report.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的分析報告，包含：
  - 執行摘要
  - 數據概述和品質評估
  - 模式識別結果
  - 趨勢分析和異常
  - 關鍵指標和統計數據
  - 洞察和觀察
  - 建議（如適用）
- 格式: Markdown 格式，使用標題、列表和表格

#### 步驟 6.2: 保存洞察摘要
**必須**使用 `sandbox.write_file` 工具保存洞察摘要（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `insights_summary.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 關鍵洞察和可執行的觀察結果
- 格式: Markdown 格式

#### 步驟 6.3: 保存視覺化說明（如適用）
如果生成了視覺化描述，**必須**使用 `sandbox.write_file` 工具保存（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `visualizations.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 圖表和圖形的描述和建議
- 格式: Markdown 格式

## Success Criteria
- Data is collected and structured
- Data patterns are identified
- Trends and anomalies are analyzed
- Key metrics are calculated
- Comprehensive analysis report is generated
- User has clear insights and actionable observations
- All analysis results are saved to files for future reference
