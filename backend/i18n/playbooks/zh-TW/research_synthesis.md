---
playbook_code: research_synthesis
version: 1.0.0
name: 研究綜合
description: 綜合多個研究來源的資訊，透過收集研究材料和文獻、提取核心觀點、識別共同主題、綜合發現和結論，並生成研究報告
tags:
  - research
  - synthesis
  - analysis
  - knowledge

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_files.extract_text
  - semantic_seeds.extract_seeds
  - core_llm.structured_extract

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: researcher
icon: 📚
---

# Research Synthesis - SOP

## Goal
Help users synthesize information from multiple research sources by collecting research materials and literature, extracting core viewpoints, identifying common themes, synthesizing findings and conclusions, and generating comprehensive research reports.

## Execution Steps

### Phase 1: Collect Research Materials and Literature
- Ask user to provide research materials (files, URLs, or text)
- Extract text from research documents (PDF, DOCX, or plain text)
- Collect literature references and citations
- Organize materials by source and type
- Verify completeness of research collection

### Phase 2: Extract Core Viewpoints
- Analyze each research source individually
- Extract key viewpoints, arguments, and findings
- Identify main claims and supporting evidence
- Note methodology and data sources
- Document author perspectives and biases

### Phase 3: Identify Common Themes
- Compare viewpoints across different sources
- Identify recurring themes and patterns
- Recognize convergent and divergent findings
- Map relationships between different research areas
- Categorize themes by topic or domain

### Phase 4: Synthesize Findings and Conclusions
- Integrate findings from multiple sources
- Resolve contradictions or conflicting evidence
- Build coherent narrative from diverse sources
- Identify gaps in research coverage
- Formulate synthesized conclusions

### Phase 5: Generate Research Report
- Create structured research report with:
  - Executive summary
  - Research methodology and sources
  - Key findings by theme
  - Synthesized conclusions
  - Research gaps and future directions
  - References and citations
- Provide actionable insights and recommendations

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "researcher", emphasize academic rigor and citation standards
- **Work Style**: If prefers "structured", provide detailed categorization and themes
- **Detail Level**: If prefers "high", include more granular analysis and source comparisons

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Complete research paper"), explicitly reference it in responses:
> "Since you're working towards 'Complete research paper', I recommend focusing on synthesizing findings that support your thesis..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `information_organization` - Use synthesis results to organize knowledge base
- `note_organization` - Organize research notes before synthesis

## Success Criteria
- Research materials are collected and organized
- Core viewpoints are extracted from all sources
- Common themes are identified
- Findings are synthesized into coherent conclusions
- Comprehensive research report is generated
- User has clear insights and recommendations
