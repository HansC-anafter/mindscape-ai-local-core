---
playbook_code: yoga_session_report
version: 1.0.0
locale: en
name: "Session Report & Practice Loop"
description: "Summarize current session, track progress, and plan next session"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: Session Report & Practice Loop

**Playbook Code**: `yoga_session_report`
**Version**: 1.0.0
**Purpose**: Summarize current session, track progress, and plan next session

---

## Input Data

```json
{
  "session_id": "session_20251224_001",
  "user_id": "user_123",
  "segments": [
    {
      "segment_id": "seg_001",
      "asana_id": "downward_dog",
      "start_time": 5.2,
      "end_time": 20.8
    }
  ],
  "metrics": [
    {
      "segment_id": "seg_001",
      "angles": {...},
      "symmetry": {...},
      "stability": {...},
      "events": [...]
    }
  ],
  "safety_labels": ["yellow"],
  "events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone"
    }
  ],
  "asanas_practiced": ["downward_dog"],
  "user_feedback": null,
  "user_goal": null,
  "historical_sessions": null
}
```

---

## Processing Steps

### Step 1: Generate Session Summary

Calculate session summary:
- **total_duration**: Total practice duration (seconds)
- **segments_analyzed**: Number of segments analyzed
- **overall_safety**: Overall safety label (green/yellow/red)
- **key_improvements**: Key improvement areas (max 5)
- **strengths**: Strengths (max 5)

### Step 2: Extract 3 Key Points + 1 Avoid Point

Extract from events and metrics:
- **three_key_points**: 3 most important improvement points or strengths
- **one_avoid_point**: 1 action to avoid (usually red zone event)

### Step 3: Plan Next Session

Plan next session based on current performance:
- If yellow/red events → Repeat same asana, focus on improvements
- If all green → Can deepen practice or progress
- Always include rest pose (child_pose)

### Step 4: Track Progress

Compare with historical records:
- **stability_trend**: Stability trend (improving/stable/degrading)
- **symmetry_trend**: Symmetry trend
- **notes**: Progress notes

---

## Output Data

```json
{
  "session_id": "session_20251224_001",
  "user_id": "user_123",
  "date": "2025-12-24T10:30:00Z",
  "asanas_practiced": ["downward_dog"],
  "summary": {
    "total_duration": 30,
    "segments_analyzed": 1,
    "overall_safety": "yellow",
    "key_improvements": [
      "Knee alignment needs attention"
    ],
    "strengths": [
      "Shoulder stability is good",
      "Breathing rhythm is steady"
    ]
  },
  "three_key_points": [
    "Pay attention to right knee, slightly bend to avoid hyperextension",
    "Keep shoulders stable, this part is done well",
    "Next time can try adjusting hip height slightly"
  ],
  "one_avoid_point": "Avoid locking knees and bearing pressure",
  "next_session_plan": {
    "recommended_asanas": ["downward_dog", "child_pose"],
    "focus_areas": ["Knee alignment", "Hip stability"],
    "estimated_duration": 20
  },
  "progress_tracking": {
    "stability_trend": "improving",
    "symmetry_trend": "stable",
    "notes": "Knee alignment is a new focus point"
  },
  "user_feedback": null
}
```

### Decision Logic

- Plan next session based on overall_safety
- If improvements needed → Repeat same asana
- If all green → Can progress or deepen
- Always include rest pose

---

## Tool Dependencies

- `yogacoach.session_report` - Session report generator

---

## Related Documentation

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) Section 7









