---
playbook_code: yoga_coach_mapping
version: 1.0.0
locale: en
name: "Coach Mapping & Navigation"
description: "Map events to teacher demo video chapters so users can see that exact moment"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: Coach Mapping & Navigation

**Playbook Code**: `yoga_coach_mapping`
**Version**: 1.0.0
**Purpose**: Map events to teacher demo video chapters so users can see "that exact moment"

---

## Input Data

```json
{
  "priority_events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5,
      "event_id": "evt_001"
    }
  ],
  "asana_id": "downward_dog",
  "teacher_demo_video": {
    "youtube_id": "abc123xyz_downward_dog",
    "chapters": [
      {
        "name": "common_mistakes",
        "start": 75,
        "end": 150,
        "error_tags": ["knee_hyperextension", "rounded_back"]
      }
    ]
  },
  "segment_id": "seg_001"
}
```

---

## Processing Steps

### Step 1: Map Events to Chapters

Map priority events to teacher demo video chapters:
- Check if event `type` is in chapter `error_tags`
- Check if chapter name is relevant to event (common_mistakes, modifications, alignment)
- If matching chapter found, select most relevant one
- If no match, use default chapter (common_mistakes or alignment_points)

### Step 2: Generate YouTube Timestamp Links

Generate YouTube links for each playlist item:
- Format: `https://youtube.com/watch?v={youtube_id}&t={start_time}s`
- Include start and end times
- Calculate watch duration

### Step 3: Add Modification Chapters

If playlist not full (max 5 items), add modification chapters:
- Find `modifications_beginner` or `modifications` chapters
- Add to end of playlist

### Step 4: Generate Playlist

Compile complete playlist:
- Include all chapter items
- Calculate total watch time
- Include chapter context and descriptions

---

## Output Data

```json
{
  "segment_id": "seg_001",
  "asana_id": "downward_dog",
  "teacher_demo_video": "abc123xyz_downward_dog",
  "playlist": [
    {
      "sequence": 1,
      "event_id": "evt_001",
      "chapter": "common_mistakes",
      "start_time": 75,
      "end_time": 150,
      "youtube_link": "https://youtube.com/watch?v=abc123xyz_downward_dog&t=75s",
      "reason": "Demonstrate adjustment for Knee angle in yellow zone",
      "watch_duration": 75,
      "context": {
        "zh-TW": "常見錯誤示範",
        "en": "Common mistakes"
      },
      "description": {
        "zh-TW": "常見的錯誤動作與調整方法",
        "en": "Common errors and how to fix them"
      }
    }
  ],
  "total_watch_time": 75,
  "total_items": 1
}
```

### Decision Logic

- Playlist contains max 5 items
- Prioritize chapters relevant to events
- Use default chapter if no match found
- Automatically add modification chapters (if space allows)

---

## Tool Dependencies

- `yogacoach.coach_mapping` - Coach mapping tool
- `yogacoach.rubric_loader` - Load asana rubric (get teacher_demo_video)

---

## Related Documentation

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) Section 5









