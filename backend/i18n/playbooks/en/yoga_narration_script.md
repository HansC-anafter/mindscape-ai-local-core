---
playbook_code: yoga_narration_script
version: 1.0.0
locale: en
name: "AI Narration Script Generation"
description: "Generate narration scripts that focus on one thing at a time with non-pushy tone"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: AI Narration Script Generation

**Playbook Code**: `yoga_narration_script`
**Version**: 1.0.0
**Purpose**: Generate narration scripts that focus on one thing at a time with non-pushy tone

---

## Input Data

```json
{
  "allowed_actions": {
    "give_detailed_feedback": true,
    "suggest_progression": false,
    "suggest_modifications": true,
    "suggest_alternatives": true
  },
  "priority_events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5
    }
  ],
  "coach_playlist": {
    "playlist": [...]
  },
  "rubric": {
    "asana_code": "downward_dog",
    "modifications": {...}
  },
  "segment_id": "seg_001",
  "asana_name": "Downward-Facing Dog"
}
```

---

## Processing Steps

### Step 1: Select Focus Points (1-2 Things Only)

Select 1-2 most important events from priority events:
- Priority: red > yellow
- Maximum 2 focus points (default 1)
- Ensure "one thing at a time" principle

### Step 2: Generate Narration (Yoga-Friendly Tone)

Generate narration for each focus event:
- **observation**: Observation description (friendly, non-judgmental)
- **adjustment**: Adjustment suggestion (only if allowed_actions.give_detailed_feedback is true)
- **self_check**: Self-check prompt (always included, cultivate body awareness)
- **safety_note**: Safety reminder (included for yellow/red events)

### Step 3: Generate Alternative Paths

Generate alternative versions based on rubric:
- **beginner**: Beginner version (if available)
- **with_props**: With props version (if available)
- **rest**: Rest pose (always included)

### Step 4: Generate On-Screen Cues

Generate short on-screen cue text:
- Display during pose hold
- Show only focus point text
- Position: center

---

## Output Data

```json
{
  "segment_id": "seg_001",
  "main_feedback": {
    "focus_point": "Knee alignment",
    "observation": "In Downward-Facing Dog, your knee angle is in yellow zone.",
    "adjustment": "Try slightly bending your knees, imagine knees facing forward, avoid locking.",
    "self_check": "Feel if the back of your thighs have moderate extension, not the knees bearing pressure.",
    "safety_note": "If knees feel uncomfortable, you can switch to a bent-knee version."
  },
  "alternative_paths": [
    {
      "path_type": "beginner",
      "description": "Beginner version",
      "demo_link": "https://youtube.com/watch?v=abc123xyz&t=120s"
    },
    {
      "path_type": "with_props",
      "description": "Using yoga block",
      "demo_link": "https://youtube.com/watch?v=abc123xyz&t=150s"
    },
    {
      "path_type": "rest",
      "description": "Rest pose (Child's Pose)",
      "demo_link": null
    }
  ],
  "on_screen_cues": [
    {
      "timing": "during_hold",
      "text": "Knee alignment",
      "position": "center"
    }
  ]
}
```

### Decision Logic

- If no events → Generate general positive feedback
- If allowed_actions.give_detailed_feedback is false → No adjustment included
- If event severity is red → Include strong safety reminder
- If event severity is yellow → Include gentle safety reminder

---

## Tool Dependencies

- `yogacoach.narration_script` - AI narration script generator
- `yogacoach.rubric_loader` - Load asana rubric (get modifications)

---

## Related Documentation

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) Section 6









