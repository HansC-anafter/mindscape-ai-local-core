---
playbook_code: seo_optimization
version: 1.0.0
capability_code: openseo
name: SEO Optimization
description: Optimize content for SEO performance by collecting target keywords, analyzing competitors, optimizing titles and descriptions, improving content structure, and generating SEO reports
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
locale: en
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

### Phase 6: File Generation and Saving

#### Step 6.1: Save SEO Report
**Must** use `sandbox.write_file` tool to save SEO report (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `seo_report.md` (relative path, relative to sandbox root)
- Content: Complete SEO report, including:
  - Keyword analysis
  - Competitor insights
  - Title and description optimizations
  - Content structure improvements
  - Action items and priorities
- Format: Markdown format

#### Step 6.2: Save Optimization Checklist
**Must** use `sandbox.write_file` tool to save optimization checklist (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `optimization_checklist.md` (relative path, relative to sandbox root)
- Content: Implementation checklist and optimization steps
- Format: Markdown format

## Success Criteria
- Target keywords are identified and analyzed
- Competitor strategies are understood
- Titles and descriptions are optimized
- Content structure is improved for SEO
- Comprehensive SEO report is generated
- User has clear action items and priorities










