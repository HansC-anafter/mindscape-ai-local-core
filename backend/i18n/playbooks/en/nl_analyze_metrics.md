# Analyze Metrics

## Purpose

Analyze campaign delivery and engagement metrics including open rates, click rates, and benchmarks.

## When to Use

- After sending a campaign
- Reviewing campaign performance
- Comparing against industry benchmarks

## Inputs

- **campaign_id** (required): Campaign to analyze
- **include_link_clicks** (optional): Include link click breakdown

## Outputs

- **metrics**: Raw metrics (delivered, opened, clicked, etc.)
- **rates**: Calculated rates (open_rate, click_rate, etc.)
- **benchmarks**: Industry average comparisons
- **performance**: Above/below benchmark assessment

## Key Metrics

- **Open Rate**: Unique opens / Delivered
- **Click Rate**: Unique clicks / Delivered
- **Bounce Rate**: Bounced / Total sent
- **Unsubscribe Rate**: Unsubscribed / Delivered

## Example Usage

```yaml
inputs:
  campaign_id: "abc123"
  include_link_clicks: true
```

## Related Playbooks

- `nl_send_campaign`: Send before analyzing
- `nl_create_campaign`: Start new campaign based on learnings
