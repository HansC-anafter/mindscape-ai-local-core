# Batch Schedule

## Purpose

Schedule multiple content items with automatic time distribution. Supports even distribution, peak hours optimization, or custom timing.

## When to Use

- Schedule a week's worth of content at once
- Optimize posting times for engagement
- Batch import content calendar from planning

## Inputs

- **items** (required): List of content items to schedule
- **distribution_strategy** (required):
  - `type`: Distribution type (even, peak_hours, custom)
  - `start_time`: Start of distribution window
  - `end_time`: End of distribution window
  - `peak_hours`: Peak hours for peak_hours strategy (0-23)

## Distribution Strategies

### Even Distribution
Distributes items evenly across the time window.

### Peak Hours
Schedules items during specified peak engagement hours.

### Custom
Uses provided custom times for each item.

## Outputs

- **scheduled_count**: Number of items scheduled
- **items**: List of scheduled items with times

## Example Usage

```yaml
inputs:
  items:
    - content_ref: { pack: "ig", asset_id: "post_001" }
      target_platform: "ig"
    - content_ref: { pack: "ig", asset_id: "post_002" }
      target_platform: "ig"
  distribution_strategy:
    type: "peak_hours"
    start_time: "2026-01-22T00:00:00Z"
    end_time: "2026-01-28T23:59:59Z"
    peak_hours: [9, 12, 18, 21]
```

## Related Playbooks

- `cs_create_schedule`: Create single schedule
- `cs_view_calendar`: View resulting calendar
