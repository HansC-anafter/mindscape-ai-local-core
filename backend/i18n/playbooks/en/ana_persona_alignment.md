# Persona Alignment Check

## Purpose

Check content alignment with brand personas defined in brand_identity pack. This playbook validates whether produced content maintains consistency with established persona guidelines.

## When to Use

- After generating new content batches
- During content quality reviews
- When onboarding new content creators
- Before publishing high-stakes content

## Inputs

- **content_refs** (required): Array of content references to check alignment
  - Should include visual features, topics, tone indicators
- **persona_ref** (required): Reference to brand persona from brand_identity pack
  - Can include tone settings, vocabulary hints, visual identity guidelines

## Process

1. **Aggregate Content Features**: Analyze visual and content patterns across provided content
2. **Compare with Persona**: Check alignment across tone, visual, and topic dimensions
3. **Generate Report**: Create alignment report with specific recommendations

## Outputs

- **alignment_results**: Detailed alignment analysis
  - Alignment scores by dimension
  - Specific misalignment examples
  - Recommendations for improvement

## Example Usage

```yaml
inputs:
  content_refs:
    - source: "recent_posts"
      features:
        visual_tokens: ["gradient", "minimalist"]
        topics: ["productivity", "ai"]
        tone_indicators: {"formality": 0.4, "warmth": 0.7}
  persona_ref:
    persona_id: "mindscape_voice"
    tone:
      formality: 0.3
      warmth: 0.8
      energy: 0.6
    vocabulary:
      preferred: ["empower", "create", "discover"]
      avoid: ["simply", "just"]
    visual_identity:
      visual_tokens: ["gradient", "soft_shadow", "rounded"]
```

## Related Playbooks

- `bi_create_persona`: Define or update brand personas
- `bi_validate_content_against_persona`: Detailed per-content validation
- `content_drafting`: Create persona-aligned content
