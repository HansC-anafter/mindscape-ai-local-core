---
playbook_code: yogacoach_demo_video_chapter_suggestion_status
version: 1.0.0
locale: en
name: "Demo Video Chapter Suggestion Status"
description: "Query chapter suggestion job execution status and results"
capability_code: yogacoach
tags:
  - yoga
  - video
  - chapter
  - status
---

# Playbook: Demo Video Chapter Suggestion Status

**Playbook Code**: `yogacoach_demo_video_chapter_suggestion_status`
**Version**: 1.0.0
**Purpose**: Query chapter suggestion job execution status and results

---

## Input Data

```json
{
  "job_id": "job-123"
}
```

## Output Data

### Status: queued/running

```json
{
  "job_id": "job-123",
  "status": "running",
  "progress": {
    "current_step": "chapter_suggestion",
    "progress_percentage": 50
  }
}
```

### Status: completed

```json
{
  "job_id": "job-123",
  "status": "completed",
  "result": {
    "suggested_chapters": [
      {
        "chapter_id": "suggested_chapter_1",
        "title": "Entry",
        "start_time": 0,
        "end_time": 20.5,
        "confidence": 0.85,
        "reasons": ["Large motion change", "Long hold time"],
        "detection_method": "motion_change"
      }
    ],
    "detection_metadata": {
      "total_segments_detected": 3,
      "average_confidence": 0.82,
      "detection_method": "motion_segmentation"
    }
  }
}
```

### Status: failed

```json
{
  "job_id": "job-123",
  "status": "failed",
  "error": "Failed to extract keypoints from video"
}
```

## Process Flow

1. Receive `job_id`
2. Call `job_dispatcher` in query mode (only pass `job_id`)
3. Return job status and result (if completed)

## Notes

- Uses `job_dispatcher` query mode (only pass `job_id`, no `job_type`)
- Tool internally determines mode based on presence of `job_id`
- Frontend should poll this playbook until status is `completed` or `failed`

