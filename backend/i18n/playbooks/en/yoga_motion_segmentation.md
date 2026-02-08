---
playbook_code: yoga_motion_segmentation
version: 1.0.0
locale: en
name: "Motion Segmentation"
description: "Segment video into asana phases (entry/hold/exit) within teacher-approved library"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: Motion Segmentation

**Playbook Code**: `yoga_motion_segmentation`
**Version**: 1.0.0
**Purpose**: Segment video into asana phases (entry/hold/exit) within teacher-approved library

---

## Input Data

```json
{
  "keypoints": [
    {
      "frame_id": 0,
      "timestamp": 0.0,
      "keypoints": {
        "nose": {"x": 320, "y": 180, "confidence": 0.95},
        "left_shoulder": {"x": 280, "y": 220, "confidence": 0.92}
      }
    }
  ],
  "teacher_asana_library": [
    "downward_dog",
    "warrior_ii",
    "triangle_pose",
    "bridge_pose",
    "cat_cow"
  ],
  "time_features": []
}
```

---

## Processing Steps

### Step 1: Asana Classification (Library-Limited)

Use sliding window approach to scan keypoints:
- Only classify within `teacher_asana_library` scope
- Calculate similarity with each asana
- Only accept classification results with confidence > 0.7
- Mark segments not in library as `unrecognized`

### Step 2: Phase Segmentation (Entry/Hold/Exit)

For each identified asana segment:
- Extend forward and backward to find complete segment
- Detect entry, hold, exit phases
- Use heuristic: first 20% = entry, middle 60% = hold, last 20% = exit

### Step 3: Confidence Score Calculation

Calculate overall confidence:
- Pose classification confidence (50%)
- Keypoint detection quality (30%)
- Phase detection confidence (20%)

### Step 4: Filter Low-Confidence Segments

Only keep:
- Segments with confidence > 0.7
- Segments with duration >= 3 seconds

---

## Output Data

```json
{
  "segments": [
    {
      "segment_id": "seg_0005",
      "asana_id": "downward_dog",
      "start_time": 5.2,
      "end_time": 20.8,
      "confidence": 0.87,
      "phases": {
        "entry": {"start": 5.2, "end": 8.1},
        "hold": {"start": 8.1, "end": 18.5},
        "exit": {"start": 18.5, "end": 20.8}
      }
    }
  ],
  "unrecognized_segments": [
    {
      "start_time": 25.0,
      "end_time": 30.0,
      "reason": "not_in_library"
    }
  ]
}
```

### Decision Logic

- If `segments` exist and confidence > 0.7 → Continue to Playbook 03
- If only `unrecognized_segments` → Return "Asana not in library"
- If no segments → Return "Unable to identify asana"

---

## Tool Dependencies

- `yogacoach.motion_segmenter` - Motion segmentation tool
- `yogacoach.rubric_loader` - Load asana rubric (for similarity calculation)

---

## Related Documentation

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) Section 2









