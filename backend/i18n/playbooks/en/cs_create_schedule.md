# Create Schedule

## Purpose

Create a new scheduled content item for cross-platform publishing. Supports IG, web, newsletter, and Canva platforms.

## When to Use

- Schedule future content publication
- Set up automated posting workflows
- Plan content calendar in advance

## Inputs

- **content_ref** (required): Reference to content asset
  - `pack`: Source pack (e.g., "ig", "web_generation")
  - `asset_id`: Asset identifier
  - `version`: Version ("latest" or specific version)
  - `playbook_to_trigger`: Playbook to execute on dispatch
- **target_platform** (required): Target platform (ig, web, newsletter, canva)
- **scheduled_time** (required): Scheduled publish time (ISO format)
- **timezone** (optional): Timezone - default: "Asia/Taipei"
- **retry_policy** (optional): Retry configuration

## Process

1. **Validate Input**: Check content_ref and platform
2. **Create Schedule Item**: Store in local ledger
3. **Register Trigger**: Set up time-based trigger

## Outputs

- **schedule_id**: Unique identifier for the schedule
- **schedule_item**: Full schedule item details

## Example Usage

```yaml
inputs:
  content_ref:
    pack: "ig"
    asset_id: "post_20260121_001"
    version: "latest"
    playbook_to_trigger: "ig_publish_content"
  target_platform: "ig"
  scheduled_time: "2026-01-22T09:00:00Z"
  timezone: "Asia/Taipei"
  retry_policy:
    max_retries: 3
    retry_interval_sec: 300
```

## Related Playbooks

- `cs_batch_schedule`: Schedule multiple items
- `cs_cancel_schedule`: Cancel pending schedule
- `cs_view_calendar`: View schedule calendar
