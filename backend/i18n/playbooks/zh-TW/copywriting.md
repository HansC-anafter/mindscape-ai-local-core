---
playbook_code: copywriting
version: 1.0.0
name: 文案撰寫與行銷文案
description: 撰寫行銷文案、標題和行動呼籲。生成多個版本並針對目標受眾優化語氣和表達
tags:
  - writing
  - copywriting
  - marketing
  - content

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
optional_tools:
  - canva

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: writer
icon: 📝
---

# Copywriting & Marketing Copy - SOP

## Goal
Help users write compelling marketing copy, headlines, and CTAs. Generate multiple versions and optimize tone and expression for target audiences.

## Execution Steps

### Phase 1: Collect Product/Service Information
- Ask user about the product or service they want to promote
- Identify key features and benefits
- Understand the unique selling proposition (USP)
- Collect any existing marketing materials or references

### Phase 2: Identify Target Audience
- Define primary and secondary target audiences
- Understand audience demographics and psychographics
- Identify pain points and motivations
- Determine preferred communication style

### Phase 3: Define Core Message
- Articulate the main value proposition
- Identify key messages to communicate
- Determine the emotional appeal
- Set the desired tone and voice

### Phase 4: Generate Multiple Copy Versions
- Create headline variations (3-5 options)
- Generate body copy in different styles
- Develop CTA options
- Produce variations for different channels (if applicable)

### Phase 5: Optimize Tone and Expression
- Refine copy for clarity and impact
- Adjust tone to match target audience
- Enhance persuasive elements
- Ensure consistency across all versions
- Provide recommendations for A/B testing

### Phase 6: Generate Visual Design (Optional)
- Ask user if they want to create visual designs for the copy
- If yes, search for appropriate Canva templates based on content type and target platform
- Create design from selected template
- Update text blocks with generated headlines and CTAs
- Generate multiple size variants for different platforms (Instagram, Facebook, Banner) if needed
- Export designs in requested formats (PNG, JPG, PDF)
- Provide design URLs and export links

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "entrepreneur", emphasize ROI and conversion potential
- **Tone Preference**: If prefers "direct", use straightforward language
- **Detail Level**: If prefers "high", provide more technical details and data points

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Launch product marketing campaign"), explicitly reference it in responses:
> "Since you're working towards 'Launch product marketing campaign', I recommend focusing on..."

### Phase 7: 文件生成與保存

#### 步驟 7.1: 保存文案版本
**必須**使用 `sandbox.write_file` 工具保存所有文案版本（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `copy_variations.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 所有生成的文案版本，包含標題、正文和 CTA 選項
- 格式: Markdown 格式，使用標題和列表組織

#### 步驟 7.2: 保存標題選項
**必須**使用 `sandbox.write_file` 工具保存標題選項（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `headlines.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 所有生成的標題變體（3-5 個選項）
- 格式: Markdown 格式，每個標題一行

#### 步驟 7.3: 保存 CTA 選項
**必須**使用 `sandbox.write_file` 工具保存行動呼籲選項（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `ctas.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 所有生成的 CTA 選項
- 格式: Markdown 格式

#### 步驟 7.4: 保存優化建議（如適用）
如果提供了 A/B 測試建議，**必須**使用 `sandbox.write_file` 工具保存（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `ab_testing_recommendations.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: A/B 測試建議和優化方向

## Success Criteria
- Multiple copy versions are generated
- Copy is tailored to target audience
- Headlines are compelling and attention-grabbing
- CTAs are clear and action-oriented
- User has options for A/B testing
- Visual designs are created (if requested) with copy integrated
- Multiple platform size variants are available (if requested)
- All generated content is saved to files for future reference

## Integration with Canva

This playbook supports optional Canva integration for visual design generation:

**When to use Canva**:
- User requests visual designs for marketing copy
- Social media posts need visual assets
- Multi-platform campaigns require size variants

**Canva Tools Used**:
- `canva.list_templates` - Search for appropriate templates
- `canva.create_design_from_template` - Create design from template
- `canva.update_text_blocks` - Update design with generated copy
- `canva.export_design` - Export final designs

**Note**: Canva integration requires a valid Canva connection. If no connection is available, the playbook will proceed with text-only output.
