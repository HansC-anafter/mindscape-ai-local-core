---
playbook_code: content_editing
version: 1.0.0
name: 內容編輯與優化
description: 編輯和優化內容品質，透過分析內容結構和邏輯、檢查語氣和風格一致性、改善可讀性、檢查品牌指南，並生成編輯建議
tags:
  - editing
  - content
  - optimization
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
  - review.suggest
  - core_llm.generate
optional_tools:
  - voice_recording.transcribe

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: editor
icon: ✏️
---

# Content Editing & Optimization - SOP

## Goal
Help users edit and optimize content quality by analyzing content structure and logic, checking tone and style consistency, improving readability, checking brand guidelines, and generating comprehensive editing suggestions and optimized versions.

## Execution Steps

### Phase 1: Analyze Content Structure and Logic
- Extract text from content files or receive text input
- Analyze overall content structure and organization
- Check logical flow and coherence
- Identify structural issues (missing sections, unclear transitions)
- Evaluate content hierarchy and organization

### Phase 2: Check Tone and Style Consistency
- Analyze tone throughout the content
- Check style consistency (formal vs. informal, technical vs. accessible)
- Identify tone shifts or inconsistencies
- Verify alignment with target audience
- Check for brand voice compliance

### Phase 3: Optimize Readability
- Analyze sentence length and complexity
- Check paragraph structure and length
- Improve clarity and conciseness
- Enhance flow and transitions
- Optimize vocabulary for target audience

### Phase 4: Check Brand Guidelines
- Review content against brand guidelines (if provided)
- Check terminology and naming conventions
- Verify brand voice and messaging alignment
- Ensure compliance with style guide
- Identify any brand guideline violations

### Phase 5: Generate Editing Suggestions
- Compile all analysis findings
- Generate prioritized editing suggestions
- Create optimized version of content
- Provide before/after comparisons for key changes
- Generate editing checklist

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "content creator", emphasize engagement and readability
- **Work Style**: If prefers "structured", provide detailed editing checklists
- **Detail Level**: If prefers "high", include more granular editing suggestions

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Improve content quality"), explicitly reference it in responses:
> "Since you're working towards 'Improve content quality', I recommend focusing on..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `content_analysis` - Use analysis results to inform editing priorities
- `seo_optimization` - Apply SEO optimizations during editing
- `publishing_workflow` - Prepare content for publishing after editing

## Integration with Voice Recording

If content includes audio files or requires audio analysis:
- Use `voice_recording.transcribe` to transcribe audio content for editing
- Analyze transcribed text for consistency with written content
- Ensure audio and written content alignment

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存編輯後的內容
**必須**使用 `sandbox.write_file` 工具保存編輯後的內容（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `edited_content.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 優化後的完整內容
- 格式: Markdown 格式

#### 步驟 6.2: 保存編輯說明
**必須**使用 `sandbox.write_file` 工具保存編輯說明（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `editing_notes.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 所有編輯建議、改進說明和 before/after 比較
- 格式: Markdown 格式

## Success Criteria
- Content structure and logic are analyzed
- Tone and style consistency are verified
- Readability is optimized
- Brand guidelines are checked
- Comprehensive editing suggestions are generated
- Optimized version of content is provided
- User has clear editing checklist and priorities
