---
playbook_code: seo_optimization
version: 1.0.0
capability_code: openseo
name: SEO 優化
description: 優化內容的 SEO 表現，透過收集目標關鍵字、分析競爭對手、優化標題和描述、改善內容結構，並生成 SEO 報告
tags:
  - seo
  - optimization
  - content
  - marketing

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

entry_agent_type: consultant
icon: 🔍
---

# SEO Optimization - SOP

## Goal
Help users optimize content for SEO performance by collecting target keywords, analyzing competitors, optimizing titles and descriptions, improving content structure, and generating comprehensive SEO reports.

## Execution Steps

### Phase 1: Collect Target Keywords
- Ask user about target keywords or topics
- Identify primary and secondary keywords
- Understand search intent for each keyword
- Collect any existing keyword research or data

### Phase 2: Analyze Competitors
- Identify competitor content for target keywords
- Analyze competitor SEO strategies
- Compare content structure and keyword usage
- Identify opportunities and gaps
- Understand ranking factors

### Phase 3: Optimize Titles and Descriptions
- Create SEO-optimized titles (50-60 characters)
- Write compelling meta descriptions (150-160 characters)
- Include target keywords naturally
- Ensure titles and descriptions are unique and relevant
- Optimize for click-through rates

### Phase 4: Improve Content Structure
- Analyze current content structure
- Optimize headings (H1, H2, H3) hierarchy
- Ensure proper keyword distribution
- Improve content flow and readability
- Add internal linking opportunities
- Optimize image alt texts and file names

### Phase 5: Generate SEO Report
- Compile all optimization recommendations
- Create structured SEO report with:
  - Keyword analysis
  - Competitor insights
  - Title and description optimizations
  - Content structure improvements
  - Action items and priorities
- Provide implementation checklist

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "marketer", emphasize conversion optimization alongside SEO
- **Work Style**: If prefers "structured", provide detailed checklists and priorities
- **Detail Level**: If prefers "high", include more technical SEO recommendations

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Improve website SEO ranking"), explicitly reference it in responses:
> "Since you're working towards 'Improve website SEO ranking', I recommend focusing on..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `content_analysis` - Use content analysis results to inform SEO optimization
- `content_editing` - Apply SEO optimizations during content editing

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存 SEO 報告
**必須**使用 `sandbox.write_file` 工具保存完整的 SEO 優化報告（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `seo_report.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的 SEO 報告，包含：
  - 關鍵字分析
  - 競爭對手洞察
  - 標題和描述優化
  - 內容結構改進
  - 行動項目和優先級
- 格式: Markdown 格式

#### 步驟 6.2: 保存優化檢查清單
**必須**使用 `filesystem_write_file` 工具保存優化檢查清單：

- 文件路徑: `optimization_checklist.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 實施檢查清單和優化步驟
- 格式: Markdown 格式

## Success Criteria
- Target keywords are identified and analyzed
- Competitor strategies are understood
- Titles and descriptions are optimized
- Content structure is improved for SEO
- Comprehensive SEO report is generated
- User has clear action items and priorities









