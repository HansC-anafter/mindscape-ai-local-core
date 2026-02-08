---
playbook_code: yoga_pose_assessment
version: 1.0.0
locale: en
name: "Pose Assessment & Metrics Calculation"
description: "Calculate angles, symmetry, stability metrics and detect yellow/red events"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: Pose Assessment & Metrics Calculation

**Playbook Code**: `yoga_pose_assessment`
**Version**: 1.0.0
**Purpose**: Calculate angles, symmetry, stability metrics and detect yellow/red events

---

## Input Data

```json
{
  "segments": [
    {
      "segment_id": "seg_0005",
      "asana_id": "downward_dog",
      "keypoints": [
        {
          "frame_id": 0,
          "timestamp": 5.2,
          "keypoints": {
            "nose": {"x": 320, "y": 180, "confidence": 0.95},
            "left_shoulder": {"x": 280, "y": 220, "confidence": 0.92}
          }
        }
      ]
    }
  ],
  "rubric": {
    "asana_code": "downward_dog",
    "key_angles": [...],
    "symmetry_checks": [...],
    "stability_indicators": [...]
  }
}
```

---

## Processing Steps

### Step 1: Keypoint Smoothing

Apply Savitzky-Golay filter to smooth keypoint trajectories:
- Reduce detection noise
- Maintain movement smoothness
- Window size: 5 frames, polynomial order: 2

### Step 2: Calculate Joint Angles

Calculate angles based on `key_angles` definitions in rubric:
- For each key angle, calculate average, min, max, variance over the segment
- Use three-point angle calculation (p1-p2-p3)

### Step 3: Symmetry Check

Check left-right symmetry based on `symmetry_checks` in rubric:
- Calculate average position difference between left and right joints
- Compare with `max_diff_degrees` threshold
- Mark if within threshold

### Step 4: Stability Assessment

Assess stability based on `stability_indicators` in rubric:
- Calculate center of gravity variance
- Calculate hand placement variance
- Compare with `max_variance` threshold

### Step 5: Event Detection (Yellow/Red Zones)

Detect yellow/red zone events:
- **Angle events**: Check if angles are in yellow_range or red_range
- **Symmetry events**: Check if symmetry exceeds threshold
- **Stability events**: Check if stability is unstable
- **Compensation events**: Check common compensations (simplified)

---

## Output Data

```json
{
  "metrics": [
    {
      "segment_id": "seg_0005",
      "angles": {
        "hip_flexion": {
          "avg": 105.2,
          "min": 98.5,
          "max": 112.3,
          "variance": 8.5
        }
      },
      "symmetry": {
        "shoulder_symmetry": {
          "left_avg": 220.5,
          "right_avg": 221.2,
          "diff": 0.7,
          "within_threshold": true
        }
      },
      "stability": {
        "center_of_gravity": {
          "variance": 3.2,
          "status": "stable"
        }
      },
      "events": [
        {
          "type": "knee_hyperextension_yellow",
          "severity": "yellow",
          "description": "Knee angle in yellow zone",
          "value": 178.5,
          "angle_name": "knee_angle"
        }
      ]
    }
  ],
  "events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5
    }
  ],
  "summary": {
    "total_segments": 1,
    "total_events": 1,
    "red_events": 0,
    "yellow_events": 1
  }
}
```

### Decision Logic

- If red_events exist → Continue to Playbook 04 (Safety Engine)
- If only yellow_events → Continue to Playbook 04 (Safety Engine)
- If no events → Continue to Playbook 05 (Coach Mapping)

---

## Tool Dependencies

- `yogacoach.pose_assessment` - Pose assessment tool
  - `AngleCalculator` - Angle calculation
  - `SymmetryChecker` - Symmetry checking
  - `StabilityAssessor` - Stability assessment
  - `EventDetector` - Event detection

---

## Related Documentation

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) Section 3









