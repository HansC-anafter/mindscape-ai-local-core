---
playbook_code: yogacoach_demo_video_chapter_suggestion
version: 1.0.0
locale: en
name: "Demo Video Chapter Suggestion"
description: "Automatically detect video chapters and provide suggestions with confidence and reasons"
capability_code: yogacoach
tags:
  - yoga
  - video
  - chapter
  - suggestion
---

# Playbook: Demo Video Chapter Suggestion

**Playbook Code**: `yogacoach_demo_video_chapter_suggestion`
**Version**: 1.0.0
**Purpose**: Automatically detect video chapters and provide suggestions with confidence and reasons

---

## Input Data

```json
{
  "video_ref": {
    "type": "youtube",
    "url": "https://www.youtube.com/watch?v=VIDEO_ID"
  },
  "teacher_id": "teacher_001",
  "asana_id": "downward_dog",
  "existing_chapters": [
    {
      "chapter_id": "chapter_1",
      "title": "Entry",
      "start_time": 0,
      "end_time": 10
    }
  ]
}
```

## Output Data

```json
{
  "job_id": "job-123",
  "status": "queued",
  "status_url": "/api/v1/playbooks/yogacoach_demo_video_chapter_suggestion_status/execute",
  "estimated_completion_seconds": 60
}
```

## Process Flow

1. Receive video reference and teacher ID
2. Call `job_dispatcher` to dispatch async job
3. Immediately return `job_id` and status (does not wait for result)
4. Results are queried via `yogacoach_demo_video_chapter_suggestion_status` playbook

## Notes

- **Async Design**: This playbook only dispatches the job, does not wait for results
- **YouTube Source**: Only metadata/chapter suggestion (no download/full analysis to avoid legal risk)
- **Internal Source**: Full analysis (extract keypoints, analyze motion changes, identify chapter breakpoints)
- Use `yogacoach_demo_video_chapter_suggestion_status` playbook to query results

