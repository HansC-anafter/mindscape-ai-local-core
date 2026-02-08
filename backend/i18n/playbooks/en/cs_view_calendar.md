# View Calendar

## Purpose

View scheduled content calendar with filtering and grouping by date.

## When to Use

- Review upcoming content schedule
- Check schedule status across platforms
- Plan content gaps

## Inputs

- **start_date** (optional): Start date - defaults to today
- **end_date** (optional): End date - defaults to 30 days from start
- **platforms** (optional): Filter by platforms
- **status_filter** (optional): Filter by status (pending, completed, failed, cancelled)

## Outputs

- **date_range**: Calendar date range
- **total_items**: Total scheduled items in range
- **dates**: Items grouped by date
- **by_platform**: Count by platform
- **by_status**: Count by status

## Example Usage

```yaml
inputs:
  start_date: "2026-01-20"
  end_date: "2026-01-31"
  platforms: ["ig", "web"]
  status_filter: ["pending", "completed"]
```

## Related Playbooks

- `cs_create_schedule`: Create new schedule
- `cs_batch_schedule`: Batch schedule items
