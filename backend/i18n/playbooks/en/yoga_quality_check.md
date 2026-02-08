---
playbook_code: yoga_quality_check
version: 1.0.0
locale: en
name: "Quality Check & Privacy Verification"
description: "Check video quality before analysis and complete privacy commitment loop"
capability_code: yogacoach
tags:
  - yoga
  - quality-check
  - privacy
---

# Playbook: Quality Check & Privacy Verification

**Playbook Code**: `yoga_quality_check`
**Version**: 1.0.0
**Purpose**: Check video quality before analysis and complete privacy commitment loop

---

## Input Data

```json
{
  "video_metadata": {
    "duration": 30.5,
    "resolution": "640x480",
    "fps": 15
  },
  "frames_sample": [
    {
      "frame_id": 0,
      "timestamp": 0.0,
      "keypoints": {
        "nose": {"x": 320, "y": 180, "confidence": 0.95},
        "left_shoulder": {"x": 280, "y": 220, "confidence": 0.92}
      }
    }
  ],
  "user_consent": {
    "privacy_policy_accepted": true,
    "data_retention_days": 7
  },
  "user_pain_report": {
    "has_pain": false,
    "pain_location": null,
    "pain_level": null
  }
}
```

---

## Processing Steps

### Step 1: Video Quality Check

Check items:
- Video duration (10-60 seconds)
- Resolution (recommended 640x480 or higher)
- FPS (recommended 15fps or higher)

### Step 2: Keypoints Quality Validation

Use `KeypointsQualityChecker` to check:
- Frame count (at least 150 frames, ~10 seconds @ 15fps)
- Key joint detection rate (at least 70%)
- Average confidence (at least 0.6)
- Abnormal jump detection (may indicate detection failure)

### Step 3: Privacy Receipt Generation

Generate privacy receipt including:
- Timestamp
- User consent version
- Data types stored
- Data types not stored
- Retention days
- Deletion token (for one-click deletion)
- Expiration time

### Step 4: User Pain Report Check

If user reports pain:
- Record pain information
- Subsequent playbooks will adjust recommendations based on this

---

## Output Data

```json
{
  "quality_score": 85,
  "confidence_gate": "pass",
  "warnings": [],
  "privacy_receipt": {
    "timestamp": "2025-12-24T10:30:00Z",
    "consent_version": "1.0",
    "data_stored": [
      "keypoints (joint sequence)",
      "metrics (angles, symmetry, stability)",
      "events (error event timestamps)"
    ],
    "data_not_stored": [
      "original video file"
    ],
    "retention_days": 7,
    "deletion_token": "del_abc123xyz",
    "expires_at": "2025-12-31T10:30:00Z"
  }
}
```

### Decision Logic

- `pass`: Continue to Playbook 02 (Motion Segmentation)
- `reject`: Terminate flow, return re-shoot guidance
- `re_shoot`: Provide specific re-shoot suggestions

---

## Tool Dependencies

- `yogacoach.quality_checker` - Quality check tool

---

## Related Documentation

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) Section 1
- [ARCHITECTURE_COMPLIANCE_FIX.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/ARCHITECTURE_COMPLIANCE_FIX.md) Section 2.1-2.2









