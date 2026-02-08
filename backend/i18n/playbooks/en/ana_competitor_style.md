# Competitor Style Analysis

## Purpose

Analyze competitor visual styles by aggregating visual features extracted from mind_lens. This playbook helps identify common patterns, trending styles, and opportunities for differentiation.

## When to Use

- When conducting competitor research
- Before major brand refresh or visual identity updates
- When planning content strategy and need to understand market positioning
- After collecting visual feature data from competitor content

## Inputs

- **feature_refs** (required): Array of visual feature references from mind_lens extractions
  - Each ref should include `source` (e.g., "competitor_a", "own"), `feature_set_id`, and either `storage_key` or inline `features`
- **aggregation_strategy** (optional): Strategy for analysis
  - `cluster`: Group similar visual patterns together
  - `timeline`: Analyze style evolution over time
  - `comparison`: Compare across different sources (default)

## Process

1. **Load Features**: Retrieve visual feature sets from provided references
2. **Aggregate**: Apply selected strategy to combine and analyze features
3. **Extract Insights**: Transform aggregated results into actionable insights

## Outputs

- **aggregation_result**: Detailed analysis based on selected strategy
  - Top visual tokens and their frequency
  - Color palette trends
  - Mood vector analysis
- **insights**: Actionable insights for planning and content strategy

## Example Usage

```yaml
inputs:
  feature_refs:
    - source: "competitor_a"
      feature_set_id: "fs_001"
      storage_key: "mind_lens/extractions/competitor_a/..."
    - source: "competitor_b"
      feature_set_id: "fs_002"
      features:
        visual_tokens: ["gradient", "minimalist", "soft_shadow"]
        colors: ["#6366F1", "#EC4899"]
  aggregation_strategy: "comparison"
```

## Related Playbooks

- `ana_content_gap`: Use gap analysis results as input for competitive positioning
- `bi_define_vi`: Apply insights to visual identity refinement
