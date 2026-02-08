---
playbook_code: yoga_safety_engine
version: 1.0.0
locale: en
name: "Safety Engine"
description: "Decision layer that determines allowed actions and prevents dangerous suggestions. This is the product's moat."
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: Safety Engine

**Playbook Code**: `yoga_safety_engine`
**Version**: 1.0.0
**Purpose**: Decision layer that determines allowed actions and prevents dangerous suggestions. This is the product's moat.

---

## Input Data

```json
{
  "events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5
    }
  ],
  "metrics": {
    "angles": {...},
    "symmetry": {...},
    "stability": {...}
  },
  "video_quality_confidence": 0.85,
  "user_pain_report": {
    "has_pain": false,
    "pain_location": null,
    "pain_level": null
  }
}
```

---

## Processing Steps

### Step 1: Assess Confidence Gate

Check video quality and event confidence:
- If `video_quality_confidence < 0.5` → `low` confidence
- If `video_quality_confidence < 0.7` → `medium` confidence
- If > 50% of events have confidence < 0.7 → `medium` confidence
- Otherwise → `high` confidence

### Step 2: Check Pain Report

If user reports pain:
- Stop all progression suggestions
- Only provide alternative asanas
- Mark as `red` safety label

### Step 3: Decision Matrix

Decide allowed actions based on confidence, pain status, and event severity:

**Rule 1: Low Confidence**
- ❌ No detailed feedback
- ✅ Suggest alternatives
- ✅ Show teacher demo

**Rule 2: Pain Reported**
- ❌ No detailed feedback
- ❌ No progression suggestions
- ✅ Only alternatives

**Rule 3: Red Events**
- ✅ Give detailed feedback
- ❌ No progression suggestions
- ✅ Suggest modifications
- ✅ Suggest alternatives
- ✅ Show error demo

**Rule 4: Yellow Events**
- ✅ Give detailed feedback
- ❌ No progression suggestions
- ✅ Suggest modifications
- ✅ Show error demo

**Rule 5: All Green**
- ✅ Give detailed feedback
- ✅ Can suggest progression
- ✅ Suggest modifications

### Step 4: Prioritize Events

Sort events by severity:
- Red events first
- Yellow events second
- Sort by value magnitude

---

## Output Data

```json
{
  "allowed_actions": {
    "give_detailed_feedback": true,
    "suggest_progression": false,
    "suggest_modifications": true,
    "suggest_alternatives": true,
    "show_teacher_demo": true,
    "show_error_demo": true,
    "safety_label": "yellow",
    "reason": "Yellow zone events detected: 1"
  },
  "prioritized_events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5
    }
  ],
  "summary": {
    "confidence_level": "high",
    "confidence_reason": "confidence_sufficient",
    "pain_detected": false,
    "total_events": 1,
    "red_events": 0,
    "yellow_events": 1,
    "safety_label": "yellow"
  },
  "confidence_assessment": {
    "level": "high",
    "reason": "confidence_sufficient",
    "video_confidence": 0.85
  },
  "pain_status": {
    "pain_detected": false,
    "action": "continue"
  }
}
```

### Decision Logic

- Based on `allowed_actions`, determine behavior of subsequent playbooks
- `safety_label` used for frontend display (green/yellow/red badge)
- `prioritized_events` used for Playbook 05 (Coach Mapping)

---

## Tool Dependencies

- `yogacoach.safety_engine` - Safety decision engine

---

## Related Documentation

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) Section 4
- [ARCHITECTURE_COMPLIANCE_FIX.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/ARCHITECTURE_COMPLIANCE_FIX.md) Section 3









