---
playbook_code: yogacoach_job_dispatcher
version: 1.0.0
locale: en
name: "Job Dispatcher & Status Tracking"
description: "Receive upload completion notification, create background job for async execution of 7-playbook pipeline, provide job status tracking"
capability_code: yogacoach
tags:
  - yoga
  - job
  - pipeline
---

# Playbook: Job Dispatcher & Status Tracking

**Playbook Code**: `yogacoach_job_dispatcher`
**Version**: 1.0.0
**Purpose**: Receive upload completion notification, create background job for async execution of 7-playbook pipeline, provide job status tracking

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `session_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "payload_type": "keypoints",
  "payload": {
    "keypoints_data": {}
  },
  "callback_config": {
    "channel": "web",
    "user_id": "user-123"
  },
  "pipeline_version": "v1.2.0"
}
```

## Output Data

```json
{
  "job_id": "job-abc123",
  "status": "queued",
  "status_url": "/api/yogacoach/jobs/job-abc123/status",
  "estimated_finish_time": "2025-12-25T10:30:00Z",
  "estimated_wait_seconds": 30,
  "idempotency_key": "idemp-xyz789"
}
```

## Execution Steps

1. **Check Idempotency**
   - Check if task with `(session_id, pipeline_version)` already exists
   - If exists, return existing `job_id` and status

2. **Create Background Job**
   - Generate `job_id` (UUID)
   - Set job status to `queued`
   - Record job metadata (payload_type, callback_config, pipeline_version)

3. **Reserve Quota**
   - Call `yogacoach.plan_quota_guard` capability
   - Reserve estimated quota based on payload estimation

4. **Queue Execution**
   - Add job to execution queue
   - Return job status and estimated completion time

5. **Execute Pipeline Async**
   - Call `pipeline_orchestrator.execute_pipeline()`
   - Execute core 7 playbooks
   - Record actual analysis minutes

6. **Commit Quota**
   - Settle quota based on actual analysis minutes
   - Call `yogacoach.plan_quota_guard` capability's `commit_quota`

7. **Callback Notification**
   - After job completion, call C2 (Channel Delivery) to push results
   - On failure, log error, trigger retry or fallback

## Capability Dependencies

- `yogacoach.job_dispatcher`: Job dispatch and status tracking
- `yogacoach.plan_quota_guard`: Quota management
- `yogacoach.pipeline_orchestrator`: Pipeline execution

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Exactly-once Guarantee

- `session_id` globally unique (PRIMARY KEY)
- `job_id` globally unique (PRIMARY KEY)
- `(session_id, pipeline_version)` unique index (prevent duplicate execution of same session with different versions)
- When Job Dispatcher receives duplicate request, return existing `job_id` and `status_url` (do not create new task)

## Error Handling

- Insufficient quota: Return error, suggest plan upgrade
- Job creation failed: Return error, log details
- Pipeline execution failed: Log error, trigger retry or fallback

