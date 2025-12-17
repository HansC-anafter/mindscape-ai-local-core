---
playbook_code: copywriting
version: 1.0.0
name: Copywriting & Marketing Copy
description: Write marketing copy, headlines, and CTAs. Generate multiple versions and optimize tone and expression for target audiences
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
locale: en
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

### Phase 7: File Generation and Saving

#### Step 7.1: Save Copy Versions
**Must** use `sandbox.write_file` tool to save all copy versions (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `copy_variations.md` (relative path, relative to sandbox root)
- Content: All generated copy versions, including headlines, body copy, and CTA options
- Format: Markdown format, organized with headings and lists

#### Step 7.2: Save Headline Options
**Must** use `sandbox.write_file` tool to save headline options (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `headlines.md` (relative path, relative to sandbox root)
- Content: All generated headline variations (3-5 options)
- Format: Markdown format, one headline per line

#### Step 7.3: Save CTA Options
**Must** use `sandbox.write_file` tool to save call-to-action options (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `ctas.md` (relative path, relative to sandbox root)
- Content: All generated CTA options
- Format: Markdown format

#### Step 7.4: Save Optimization Recommendations (if applicable)
If A/B testing recommendations are provided, **must** use `sandbox.write_file` tool to save (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `ab_testing_recommendations.md` (relative path, relative to sandbox root)
- Content: A/B testing recommendations and optimization directions

## Success Criteria
- Multiple copy versions are generated
- Copy is tailored to target audience
- Headlines are compelling and attention-grabbing
- CTAs are clear and action-oriented
- User has options for A/B testing
- Visual designs are created (if requested) with copy integrated
- Multiple platform size variants are available (if requested)

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

