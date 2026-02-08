---
playbook_code: dataset_style_extraction
version: 1.0.0
capability_code: visual_lens
name: Dataset Style Extraction
description: Extract Visual Lens style directly from a dataset using stored style fingerprints and keyword/color mappings, then generate a full WebVisualLensSchema.
tags:
  - visual-lens
  - style-extraction
  - dataset
  - web-generation
kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - unsplash.extract_style_from_dataset
  - core_llm.structured_extract
  - visual_lens.visual_lens_create

language_strategy: model_native
locale: en
supported_locales:
  - en
default_locale: en
auto_localize: false

entry_agent_type: consultant
icon: 🎨
---

# Dataset Style Extraction - SOP

## Goal
Extract style signals from an existing dataset (keywords, colors, style features), synthesize a WebVisualLensSchema, and save it via Visual Lens APIs.

## Execution (high level)
1) Extract style data from dataset using `unsplash.extract_style_from_dataset` (keywords + preferences as inputs).  
2) Generate a complete WebVisualLensSchema with `core_llm.structured_extract`, ensuring all arrays/fields are populated and consistent with style data.  
3) Save the lens using `visual_lens.visual_lens_create` (workspace-scoped).

## Inputs (canonical)
- `theme_keywords` (array, required)
- `style_preferences` (array, optional)
- `lens_name` (string, required)
- `workspace_id` (string, required)

## Outputs
- `style_data`: extracted style signals
- `lens_data`: generated Visual Lens schema
- `saved_lens`: persisted lens record

## Guardrails
- No empty arrays or null objects in the generated schema.
- Prefer dataset-derived colors/themes; fall back to preferences only when missing.
- Ensure color_palette has >=3 colors; required/forbidden elements are non-empty.











