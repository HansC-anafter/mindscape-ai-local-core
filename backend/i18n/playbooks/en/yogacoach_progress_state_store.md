---
playbook_code: yogacoach_progress_state_store
version: 1.0.0
locale: en
name: "Progress State Store"
description: "Store key metrics for each session, calculate trends, generate next practice plan"
capability_code: yogacoach
tags:
  - yoga
  - progress
  - tracking
---

# Playbook: Progress State Store

**Playbook Code**: `yogacoach_progress_state_store`
**Version**: 1.0.0
**Purpose": Store key metrics for each session, calculate trends, generate next practice plan

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `user_id`, `session_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "session_report": {
    "asanas_practiced": ["downward_dog", "warrior_ii"],
    "key_metrics": {
      "alignment_score": 78,
      "stability_score": 85,
      "symmetry_score": 72
    },
    "safety_labels": ["yellow", "green"],
    "events": []
  },
  "user_feedback": {
    "difficulty_rating": 3,
    "enjoyed": true,
    "wants_deeper": false,
    "wants_new": true
  }
}
```

## Output Data

```json
{
  "student_profile": {
    "user_id": "user-123",
    "total_sessions": 12,
    "total_minutes": 180,
    "asanas_mastered": ["mountain", "forward_fold"],
    "asanas_in_progress": ["downward_dog", "warrior_ii"],
    "weak_areas": ["symmetry", "wrist_pressure"]
  },
  "trend_vectors": {
    "alignment_score": {
      "current": 78,
      "previous": 75,
      "trend": "improving",
      "change_percent": 4.0
    }
  },
  "next_plan": {
    "recommended_asanas": ["warrior_ii", "triangle_pose"],
    "focus_areas": ["symmetry", "balance"],
    "estimated_difficulty": 3,
    "rationale": "Based on your progress in Warrior II, suggest trying Triangle Pose to further improve balance and symmetry"
  }
}
```

## Execution Steps

1. **Store Progress Snapshot"
   - Extract key metrics from `session_report`
   - Store to student_profiles table

2. **Calculate Trends"
   - Compare current metrics with historical metrics
   - Calculate improving/declining/stable trends
   - Generate trend_vectors

3. **Update Student Profile"
   - Update total_sessions, total_minutes
   - Update asanas_mastered, asanas_in_progress
   - Update weak_areas

4. **Generate Next Practice Plan"
   - Based on historical data and trends
   - Recommend suitable asanas
   - Generate focus_areas and rationale

## Capability Dependencies

- `yogacoach.progress_tracker`: Progress tracking

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Error Handling

- Session Report format error: Return error, log details
- Progress storage failed: Return error, log details

