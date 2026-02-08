---
playbook_code: yogacoach_retention_loop
version: 1.0.0
locale: en
name: "User Retention & Re-engagement"
description: "Weekly summaries, practice reminders, consecutive practice streak, teacher dashboard overview"
capability_code: yogacoach
tags:
  - yoga
  - retention
  - engagement
---

# Playbook: User Retention & Re-engagement

**Playbook Code**: `yogacoach_retention_loop`
**Version**: 1.0.0
**Purpose": Weekly summaries, practice reminders, consecutive practice streak, teacher dashboard overview

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `user_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "trigger": "weekly_digest",
  "digest_config": {
    "include_trends": true,
    "include_next_plan": true,
    "include_streak": true
  },
  "frequency_control": {
    "max_pushes_per_week": 3,
    "allow_unsubscribe": true
  }
}
```

## Output Data

```json
{
  "nudge_plan": {
    "user_id": "user-123",
    "nudge_type": "weekly_digest",
    "scheduled_at": "2025-12-25T10:00:00Z",
    "channel": "line"
  },
  "weekly_digest": {
    "period": {
      "start_date": "2025-12-18",
      "end_date": "2025-12-24"
    },
    "summary": {
      "sessions_completed": 3,
      "total_minutes": 45,
      "improvement_highlights": [
        "Symmetry improved 12%",
        "Stability maintained above 85"
      ]
    },
    "next_week_plan": {
      "recommended_asanas": ["warrior_ii", "triangle_pose"],
      "goal": "Improve balance and symmetry"
    },
    "streak_status": {
      "current_streak": 7,
      "best_streak": 14,
      "achievement": "🔥 7 days in a row!"
    }
  }
}
```

## Execution Steps

1. **Check Push Frequency"
   - Check number of pushes this week
   - If exceeds max_pushes_per_week, skip push

2. **Check Unsubscribe Status"
   - Check if user has unsubscribed
   - If unsubscribed, skip push

3. **Generate Weekly Digest"
   - Get trend data from E1 (Progress State Store)
   - Generate improvement_highlights
   - Generate next_week_plan

4. **Calculate Streak"
   - Calculate consecutive practice days
   - Generate achievement message

5. **Generate Push Content"
   - Generate content based on trigger type
   - weekly_digest: Weekly summary
   - practice_reminder: Practice reminder
   - achievement: Achievement notification

6. **Call C2 (Channel Delivery)"
   - Push content to specified channel
   - Record push status

## Capability Dependencies

- `yogacoach.retention_manager": Retention management
- `yogacoach.progress_tracker": Progress tracking (get trend data)
- `yogacoach.channel_delivery": Channel delivery

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Frequency Control & Unsubscribe

- **max_pushes_per_week**: Default maximum 3 pushes per week
- **allow_unsubscribe**: Must provide unsubscribe link (especially LINE, mass blocking will disable channel)
- **unsubscribe tracking**: Record unsubscribe status to `user_channels.push_enabled`

## Error Handling

- Push frequency exceeded: Skip push, log details
- Unsubscribed: Skip push, log details
- Push failed: Log error, trigger retry

