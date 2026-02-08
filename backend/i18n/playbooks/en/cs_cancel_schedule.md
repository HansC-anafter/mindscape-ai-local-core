# Cancel Schedule

## Purpose

Cancel a pending scheduled content item before it is dispatched.

## When to Use

- Content needs revision before posting
- Plans changed and posting is no longer needed
- Emergency content hold

## Inputs

- **schedule_id** (required): ID of schedule to cancel
- **reason** (optional): Cancellation reason for tracking

## Outputs

- **success**: Whether cancellation succeeded
- **previous_status**: Status before cancellation
- **new_status**: New status (cancelled)

## Example Usage

```yaml
inputs:
  schedule_id: "abc123-def456"
  reason: "Content needs revision"
```

## Notes

- Only pending schedules can be cancelled
- Dispatched or completed schedules cannot be cancelled
- Cancellation is recorded in the ledger for audit

## Related Playbooks

- `cs_create_schedule`: Create schedule
- `cs_view_calendar`: View current schedules
