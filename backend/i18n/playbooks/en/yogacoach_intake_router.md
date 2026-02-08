---
playbook_code: yogacoach_intake_router
version: 1.0.0
locale: en
name: "Intake Router"
description: "Service entry point: session establishment and routing. Create session_id, bind user_id, teacher_id, plan_id, identify channel, check quota, determine upload method"
capability_code: yogacoach
tags:
  - yoga
  - intake
  - routing
---

# Playbook: Intake Router

**Playbook Code**: `yogacoach_intake_router`
**Version**: 1.0.0
**Purpose**: Service entry point: session establishment and routing. Create session_id, bind user_id, teacher_id, plan_id, identify channel, check quota, determine upload method

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `actor_id`, `subject_user_id`, `plan_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "teacher_id": "teacher-789",
  "channel": "web",
  "liff_context": {
    "line_user_id": "U1234567890abcdef"
  }
}
```

## Output Data

```json
{
  "session_id": "session-abc123",
  "idempotency_key": "idemp-xyz789",
  "upload_policy": {
    "method": "frontend_keypoints",
    "max_duration_sec": 900,
    "allowed_formats": ["mp4", "mov"]
  },
  "quota_snapshot": {
    "remaining_minutes": 45,
    "plan_limit": 60
  }
}
```

## Execution Steps

1. **Create Session**
   - Call `yogacoach.intake_router` capability
   - Generate `session_id` and `idempotency_key`
   - Bind `teacher_id` (`user_id`, `plan_id` provided by runtime from execution envelope)

2. **Identify Channel**
   - Check `channel` parameter (web/line)
   - If LINE, extract `line_user_id` from `liff_context`

3. **Check Quota**
   - Call `yogacoach.plan_quota_guard` capability
   - Check if remaining quota is sufficient (`plan_id` provided by runtime from execution envelope)
   - Return quota snapshot

4. **Determine Upload Method**
   - Determine upload method based on channel and quota
   - `frontend_keypoints`: Frontend extracts keypoints
   - `backend_video`: Backend processes video

5. **Generate Upload Policy**
   - Generate corresponding policy based on upload method
   - Set TTL and format restrictions

## Capability Dependencies

- `yogacoach.intake_router`: Session establishment and routing
- `yogacoach.plan_quota_guard`: Quota checking

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Error Handling

- Insufficient quota: Return error, suggest plan upgrade
- Invalid channel: Return error, only web/line supported
- Session creation failed: Return error, log details

