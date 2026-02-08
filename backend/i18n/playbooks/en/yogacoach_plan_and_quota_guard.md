---
playbook_code: yogacoach_plan_and_quota_guard
version: 1.0.0
locale: en
name: "Plan & Quota Guard"
description: "Check quota, reserve quota, commit quota, rollback quota, support billable minutes calculation"
capability_code: yogacoach
tags:
  - yoga
  - quota
  - billing
---

# Playbook: Plan & Quota Guard

**Playbook Code**: `yogacoach_plan_and_quota_guard`
**Version**: 1.0.0
**Purpose": Check quota, reserve quota, commit quota, rollback quota, support billable minutes calculation

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `plan_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "action": "check",
  "resource_request": {
    "estimated_billable_minutes": 15,
    "actual_video_minutes": 15,
    "analysis_sampling_minutes": 15
  }
}
```

## Output Data

```json
{
  "quota_snapshot": {
    "remaining_minutes": 45,
    "plan_limit": 60,
    "used_minutes": 15
  },
  "allowed": true,
  "reservation_id": "reservation-abc123"
}
```

## Execution Steps

1. **Check Quota** (action: check)
   - Query current quota usage
   - Check if remaining quota is sufficient
   - Return quota snapshot

2. **Reserve Quota** (action: reserve)
   - Reserve estimated quota
   - Generate reservation_id
   - Set TTL (auto-release on timeout)

3. **Commit Quota" (action: commit)
   - Settle quota based on actual analysis minutes
   - Calculate actual billable_minutes from segments
   - Release reservation

4. **Rollback Quota" (action: rollback)
   - Release reserved quota
   - Mark reservation as rolled back

## Capability Dependencies

- `yogacoach.plan_quota_guard`: Quota management

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Billable Minutes Calculation

- Billing uses `billable_minutes` (= total analysis segment seconds / 60), not original video minutes
- Calculate actual analysis minutes from segments

## Error Handling

- Insufficient quota: Return error, suggest plan upgrade
- Quota check failed: Return error, log details

