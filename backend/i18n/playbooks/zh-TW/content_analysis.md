---
playbook_code: content_analysis
version: 1.0.0
name: 內容分析
description: 分析內容品質和 SEO 表現，透過分析內容結構、檢查關鍵字密度、評估可讀性、識別改進機會，並生成分析報告
tags:
  - seo
  - analysis
  - content
  - quality

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

entry_agent_type: consultant
icon: 📊
---

# Content Analysis - SOP

## Goal
Help users analyze content quality and SEO performance by analyzing content structure, checking keyword density, evaluating readability, identifying improvement opportunities, and generating comprehensive analysis reports.

## Execution Steps

### Phase 1: Analyze Content Structure
- Extract text from content files (PDF, DOCX, or plain text)
- Analyze heading hierarchy (H1, H2, H3)
- Check paragraph structure and length
- Identify content sections and organization
- Evaluate overall content flow

### Phase 2: Check Keyword Density
- Identify target keywords in the content
- Calculate keyword density for primary and secondary keywords
- Check keyword distribution across content
- Analyze keyword placement (title, headings, body)
- Identify keyword stuffing or under-optimization

### Phase 3: Evaluate Readability
- Analyze sentence length and complexity
- Check paragraph length and structure
- Evaluate vocabulary level and accessibility
- Assess content clarity and coherence
- Calculate readability scores (if applicable)

### Phase 4: Identify Improvement Opportunities
- Compare content against SEO best practices
- Identify missing SEO elements (meta descriptions, alt texts, etc.)
- Find opportunities for keyword optimization
- Suggest content structure improvements
- Recommend readability enhancements

### Phase 5: Generate Analysis Report
- Compile all analysis findings
- Create structured report with:
  - Content structure analysis
  - Keyword density analysis
  - Readability assessment
  - Improvement opportunities
  - Prioritized action items
- Provide actionable recommendations

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "content creator", emphasize readability and engagement
- **Work Style**: If prefers "structured", provide detailed metrics and scores
- **Detail Level**: If prefers "high", include more granular analysis and technical details

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Improve content quality"), explicitly reference it in responses:
> "Since you're working towards 'Improve content quality', I recommend focusing on..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `seo_optimization` - Use analysis results to inform SEO optimization
- `content_editing` - Apply analysis findings during content editing

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存內容分析報告
**必須**使用 `filesystem_write_file` 工具保存完整的內容分析報告：

- 文件路徑: `content_analysis_report.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的分析報告，包含：
  - 內容結構分析
  - 關鍵字密度分析
  - 可讀性評估
  - 改進機會
  - 優先級行動項目
- 格式: Markdown 格式

#### 步驟 6.2: 保存指標摘要
**必須**使用 `sandbox.write_file` 工具保存指標摘要（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `metrics_summary.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 所有分析指標和分數的摘要
- 格式: Markdown 格式

## Success Criteria
- Content structure is thoroughly analyzed
- Keyword density is calculated and evaluated
- Readability is assessed
- Improvement opportunities are identified
- Comprehensive analysis report is generated
- User has clear, prioritized action items
