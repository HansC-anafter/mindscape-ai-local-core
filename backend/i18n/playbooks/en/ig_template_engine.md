---
playbook_code: ig_template_engine
version: 1.0.0
name: IG Template Engine
description: Apply templates to generate multiple IG post variants with different tones and CTAs
tags:
  - instagram
  - templates
  - content-generation
  - variants

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_template_engine_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: 📝
capability_code: instagram
---

# IG Template Engine

## Goal

Apply templates to generate multiple IG post variants with different style tones and CTAs (Call-to-Action) from source content.

## Functionality

This Playbook will:

1. **Load Template**: Load template based on type, style tone, and purpose
2. **Generate Posts**: Generate multiple post variants with different CTAs

## Use Cases

- Generate multiple post variants for A/B testing
- Apply brand templates to content
- Create posts with different CTAs
- Transform content using predefined templates

## Inputs

- `template_type`: Template type - "carousel", "reel", or "story" (required)
- `style_tone`: Style tone - "high_brand", "friendly", "coach", or "sponsored" (default: "friendly")
- `purpose`: Post purpose - "save", "comment", "dm", or "share" (default: "save")
- `source_content`: Source content to transform (required)
- `generate_variants`: Whether to generate multiple variants with different CTAs (default: true)

## Outputs

- `generated_posts`: Generated IG post variants
- `template_applied`: Template information applied

## Template Types

- **Carousel**: Multi-image post template
- **Reel**: Video post template
- **Story**: Story post template

## Style Tones

- **high_brand**: High brand awareness tone
- **friendly**: Friendly and approachable tone
- **coach**: Coaching and educational tone
- **sponsored**: Sponsored content tone

## CTA Purposes

- **save**: Encourage saving the post
- **comment**: Encourage comments
- **dm**: Encourage direct messages
- **share**: Encourage sharing

## Steps (Conceptual)

1. Load template based on type, tone, and purpose
2. Apply template to source content
3. Generate multiple variants with different CTAs if enabled

## Notes

- Supports multiple template types and style tones
- Can generate multiple variants for testing
- Templates include CTA variations

