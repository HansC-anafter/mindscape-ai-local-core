# Trend Signal Detection

## Purpose

Detect emerging trend signals by analyzing content features over time. This playbook helps identify rising patterns, fading trends, and optimal timing for content strategy adjustments.

## When to Use

- During monthly/quarterly content strategy reviews
- When noticing shifts in engagement patterns
- Before planning seasonal campaigns
- After accumulating sufficient historical data

## Inputs

- **feature_refs** (required): Array of content/visual feature references with timestamps
  - Each ref should include timestamp for timeline analysis
- **time_window_days** (optional): Number of days to analyze (default: 30)

## Process

1. **Timeline Aggregation**: Sort and analyze features chronologically
2. **Pattern Detection**: Identify rising and declining patterns
3. **Insight Extraction**: Generate trend-focused actionable insights

## Outputs

- **timeline_analysis**: Chronological analysis of feature evolution
  - Timeline points with visual tokens and mood data
  - Change indicators
- **trend_insights**: Actionable insights with planning recommendations

## Example Usage

```yaml
inputs:
  feature_refs:
    - source: "competitor_content"
      timestamp: "2026-01-01T00:00:00Z"
      features:
        visual_tokens: ["neon", "gradient"]
        dominant_mood: "energetic"
    - source: "competitor_content"
      timestamp: "2026-01-15T00:00:00Z"
      features:
        visual_tokens: ["soft", "organic", "gradient"]
        dominant_mood: "calm"
  time_window_days: 30
```

## Related Playbooks

- `ana_competitor_style`: Detailed style analysis for trend validation
- `content_calendar_planning`: Apply trend insights to calendar
- `ana_content_gap`: Combine with gap analysis for strategic positioning
