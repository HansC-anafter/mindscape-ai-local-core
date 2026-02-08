---
playbook_code: seo_content_generation
version: 1.0.0
capability_code: openseo
name: SEO Content Generation
description: |
  Generate SEO-optimized content using Lens Composition, supporting multiple content types (blog, product, landing_page).
  Complete workflow: Select Composition → Fuse Lens → Generate Content → SEO Optimization → Optional WordPress Publishing.
tags:
  - seo
  - content-generation
  - lens-composition
  - wordpress

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - openseo.generate_seo_content
  - openseo.optimize_content_for_seo
  - openseo.publish_to_wordpress
  - openseo.create_wordpress_draft
  - openseo.fuse_lens_composition

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: ✍️
---

# SEO Content Generation - SOP

## Goal

Generate SEO-optimized content using Lens Composition, supporting multiple content types, with optional WordPress publishing.

**Core Value**:
- Generate brand-consistent content based on Lens Composition
- Automatic SEO optimization (keywords, title, meta description)
- Calculate SEO score and readability score
- Optional WordPress publishing (draft or publish)

## Execution Steps

### Phase 0: Prepare Input Data

**Execution Order**:
1. Step 0.0: Collect content requirements
   - Content type (blog, product, landing_page)
   - Target keywords
   - Target audience
   - Content length requirements

2. Step 0.1: Select or create Composition
   - Use existing Composition ID
   - Or quickly create Composition from Preset

### Phase 1: Fuse Lens Composition

**Execution Order**:
1. Step 1.0: Fuse Composition
   - Call `fuse_lens_composition`
   - Get unified context (constraints + syntax)

### Phase 2: Generate SEO Content

**Execution Order**:
1. Step 2.0: Generate content
   - Call `generate_seo_content`
   - Use fused Lens context
   - Generate title, content, meta description

2. Step 2.1: SEO optimization
   - Automatically optimize keyword placement
   - Optimize title and meta description
   - Calculate SEO score

3. Step 2.2: Readability assessment
   - Calculate readability score
   - Generate improvement suggestions

### Phase 3: Review and Adjust (Optional)

**Execution Order**:
1. Step 3.0: Display generated results
   - Show content, title, meta description
   - Show SEO score and readability score
   - Show improvement suggestions

2. Step 3.1: User adjustments (if needed)
   - User can modify content
   - Regenerate or re-optimize

### Phase 4: Publish to WordPress (Optional)

**Execution Order**:
1. Step 4.0: Choose publishing method
   - Draft: Create draft for review
   - Publish: Direct publish

2. Step 4.1: Publish content
   - Call `create_wordpress_draft` or `publish_to_wordpress`
   - Include composition_id for traceability
   - Return post_id and revision_id

## Input Parameters

- `composition_id` (string, required): Lens Composition ID
- `content_type` (string, required): Content type (blog, product, landing_page)
- `target_keywords` (array, required): Target keywords list
- `target_audience` (string, optional): Target audience description
- `tone` (string, optional): Content tone
- `word_count` (integer, optional): Target word count
- `workspace_id` (string, required): Workspace ID
- `publish_to_wordpress` (boolean, optional): Whether to publish to WordPress
- `wordpress_site_id` (string, optional): WordPress site ID
- `publish_status` (string, optional): Publish status (draft, publish)

## Output Results

- `content` (string): Generated content
- `title` (string): SEO-optimized title
- `meta_description` (string): SEO-optimized meta description
- `seo_score` (object): SEO score details
- `readability_score` (float): Readability score
- `keywords_used` (array): Keywords used
- `suggestions` (array): Improvement suggestions
- `wordpress_post_id` (integer, optional): WordPress post ID
- `wordpress_post_url` (string, optional): WordPress post URL
- `revision_id` (string, optional): Revision ID

## Notes

1. **Composition must exist**: Ensure composition_id is valid
2. **Keywords required**: At least one target keyword is required
3. **WordPress publishing optional**: If wordpress_site_id is not provided, only generate content without publishing
4. **SEO score recommendation**: When SEO score is below 70, consider adjusting content or keywords









