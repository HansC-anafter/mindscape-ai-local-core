---
playbook_code: yogacoach_result_packager
version: 1.0.0
locale: en
name: "Result Packager"
description: "Extract core data from Session Report, generate main card, playlists and share link"
capability_code: yogacoach
tags:
  - yoga
  - result
  - packaging
---

# Playbook: Result Packager

**Playbook Code**: `yogacoach_result_packager`
**Version**: 1.0.0
**Purpose**: Extract core data from Session Report, generate main card, playlists and share link

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `session_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "session_report": {
    "segments": [],
    "metrics": [],
    "safety_labels": [],
    "events": [],
    "narration": {}
  },
  "delivery_channel": "web",
  "share_config": {
    "enable_share": true,
    "ttl_hours": 72
  }
}
```

## Output Data

```json
{
  "delivery_bundle": {
    "main_card": {
      "session_id": "session-abc123",
      "summary": {
        "total_asanas": 3,
        "total_duration_minutes": 15,
        "overall_safety_label": "yellow",
        "key_metrics": {
          "alignment_score": 78,
          "stability_score": 85,
          "symmetry_score": 72
        },
        "top_suggestion": "Pay attention to right knee overextension, suggest slight bend to protect knee"
      }
    },
    "playlists": [
      {
        "asana_id": "downward_dog",
        "chapters": [
          {
            "title": "Correct Demo - Entry Phase",
            "youtube_url": "https://youtu.be/xxx?t=5",
            "duration": 10
          }
        ]
      }
    ],
    "detailed_report_url": "/sessions/session-abc123/detailed",
    "expandable_sections": []
  },
  "render_hints": {
    "channel": "web",
    "layout": "card",
    "theme": "light"
  },
  "share_link": {
    "url": "https://yogacoach.app/s/abc12345",
    "short_code": "abc12345",
    "ttl_hours": 72,
    "expires_at": "2025-12-28T10:00:00Z"
  }
}
```

## Execution Steps

1. **Extract Core Data**
   - Extract segments, metrics, safety_labels, events from `session_report`
   - Calculate key metrics (alignment_score, stability_score, symmetry_score)

2. **Generate Main Card**
   - Generate 3 metrics + 1 suggestion + safety label
   - Calculate overall safety label (green/yellow/red)

3. **Generate Playlists**
   - Generate teacher demo timecodes for each asana
   - Generate YouTube links with timestamps

4. **Generate Expandable Sections**
   - Generate expandable detailed metrics section
   - Generate event detection section

5. **Generate Share Link**
   - Generate share link with TTL
   - Set access scope (default: owner only)

6. **Generate Render Hints"
   - Generate layout hints based on delivery_channel
   - Web: card layout
   - LINE: flex_message layout

## Capability Dependencies

- `yogacoach.result_packager`: Result packaging
- `yogacoach.share_link_generator`: Share link generation

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Error Handling

- Session Report format error: Return error, log details
- Share link generation failed: Return error, log details

