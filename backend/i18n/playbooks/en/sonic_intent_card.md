---
playbook_code: sonic_intent_card
version: 1.0.0
locale: en
name: "Sonic Intent Card Generation"
description: "Transform natural language requirements into actionable sonic dimensions"
kind: user_workflow
capability_code: sonic_space
---

# Sonic Intent Card Generation

Transform natural language requirements into actionable sonic dimensions

## Overview

The Sonic Intent Card Generation playbook transforms natural language requirements into actionable sonic dimensions. It elevates vague requests like "I want Lo-fi" into precise, executable intent specifications with dimension targets and prohibitions.

**Core Concept**: Elevate requirements from 'I want Lo-fi' to executable intent dimensions that can be used for precise sound navigation and generation.

**Key Features:**
- Natural language parsing to extract sonic dimensions
- Reference audio analysis (what you want)
- Anti-reference audio analysis (what you don't want)
- Dimension target generation with precise values
- Prohibition identification (forbidden dimension ranges)
- Conflict detection and resolution

**Purpose:**
This playbook is the entry point for sound discovery. Users describe their sonic needs in natural language, and the playbook creates a structured intent card that can be used by `sonic_navigation` to find matching sounds.

**Related Playbooks:**
- `sonic_navigation` - Use intent card to search for sounds
- `sonic_prospecting_lite` - Use intent card for sound generation
- `sonic_decision_trace` - Track intent card iterations

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_intent_card.json`

## Inputs

### Required Inputs

- **intent_description** (`string`)
  - Natural language description (e.g., 'I want something more airy and warm')

### Optional Inputs

- **reference_audio** (`file`)
  - Reference audio file

- **anti_reference_audio** (`file`)
  - Anti-reference (sounds you don't want)

- **target_scene** (`enum`)
  - Options: meditation, brand_audio, ui_sound, background_music, sfx, ambience

## Outputs

**Artifacts:**

- `sonic_intent_card`
  - Schema defined in spec file

## Steps

### Step 1: Parse Natural Language Intent

Extract sonic dimensions from natural language

- **Action**: `nlp_parse`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: extracted_dimensions, extracted_prohibitions

### Step 2: Analyze Reference Audio

Extract fingerprint from reference audio

- **Action**: `analyze_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.reference_audio exists
- **Outputs**: reference_fingerprint

### Step 3: Analyze Anti-Reference

Extract fingerprint from anti-reference

- **Action**: `analyze_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.anti_reference_audio exists
- **Outputs**: anti_fingerprint

### Step 4: Generate Dimension Targets

Map parsed intent to dimension values

- **Action**: `map_to_dimensions`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Identify Prohibitions

Define forbidden dimension ranges

- **Action**: `extract_prohibitions`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Create Intent Card

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **dimension_conflict**
  - Rule: Detect conflicting dimension requirements
  - Action: `warn_and_ask_clarification`

- **unrealistic_target**
  - Rule: Flag impossible dimension combinations
  - Action: `suggest_alternatives`

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **Natural Language Sound Request**
   - Convert "I want something more airy and warm" into dimension targets
   - Extract warmth and brightness dimensions
   - Generate precise intent card

2. **Reference-Based Intent**
   - Use reference audio to define desired sound characteristics
   - Extract fingerprint from reference
   - Create intent card matching reference style

3. **Anti-Reference Intent**
   - Specify sounds to avoid using anti-reference audio
   - Extract prohibited dimension ranges
   - Create intent card with exclusions

4. **Scene-Specific Intent**
   - Create intent for specific usage scenes (meditation, brand_audio, etc.)
   - Set appropriate dimension targets for scene
   - Ensure intent aligns with scene requirements

## Examples

### Example 1: Text-Only Intent

```json
{
  "intent_description": "I want something more airy and warm, with a spacious feel",
  "target_scene": "meditation"
}
```

**Expected Output:**
- `sonic_intent_card` artifact with:
  - Dimension targets: warmth (high), brightness (high), spatiality (high)
  - Target scene: meditation
  - No prohibitions

### Example 2: Reference Audio Intent

```json
{
  "intent_description": "Something similar to this but slightly warmer",
  "reference_audio": "/path/to/reference.wav",
  "target_scene": "background_music"
}
```

**Expected Output:**
- `sonic_intent_card` artifact with:
  - Reference fingerprint extracted
  - Dimension targets based on reference + "warmer" adjustment
  - Target scene: background_music

### Example 3: Anti-Reference Intent

```json
{
  "intent_description": "Warm ambient sound, but not too dark",
  "reference_audio": "/path/to/reference.wav",
  "anti_reference_audio": "/path/to/anti_reference.wav",
  "target_scene": "ambience"
}
```

**Expected Output:**
- `sonic_intent_card` artifact with:
  - Reference fingerprint (warm ambient)
  - Anti-reference fingerprint (too dark)
  - Prohibitions: brightness < threshold
  - Target scene: ambience

## Technical Details

**Sonic Dimensions:**
- **Warmth**: Warm/Cold axis (perceptual)
- **Brightness**: Bright/Dark axis (perceptual)
- **Spatiality**: Spacious/Intimate axis (perceptual)
- Additional dimensions based on ontology

**Dimension Extraction:**
- Parses natural language for dimension keywords
- Maps keywords to dimension values (0-100 scale)
- Handles relative terms ("more", "less", "slightly")

**Reference Audio Analysis:**
- Extracts audio fingerprint using `sonic_fingerprint_extractor`
- Maps fingerprint to dimension space
- Adjusts dimensions based on text intent

**Anti-Reference Analysis:**
- Extracts anti-reference fingerprint
- Identifies prohibited dimension ranges
- Creates exclusion rules

**Conflict Detection:**
- Detects conflicting dimension requirements
- Flags impossible combinations
- Suggests alternatives

**Intent Card Schema:**
The `sonic_intent_card` artifact contains:
- Dimension targets (warmth, brightness, spatiality, etc.)
- Dimension prohibitions (forbidden ranges)
- Target scene (meditation, brand_audio, etc.)
- Reference fingerprint (if provided)
- Anti-reference fingerprint (if provided)

**Tool Dependencies:**
- `sonic_intent_parser` - Parse natural language intent
- `sonic_audio_analyzer` - Analyze reference/anti-reference audio
- `sonic_fingerprint_extractor` - Extract audio fingerprints

**Responsibility Distribution:**
- AI Auto: 40% (automatic parsing and analysis)
- AI Propose: 50% (dimension mapping suggestions)
- Human Only: 10% (final approval for complex intents)

## Related Playbooks

- **sonic_navigation** - Use intent card to search for sounds
- **sonic_prospecting_lite** - Use intent card for sound generation
- **sonic_decision_trace** - Track intent card iterations
- **sonic_quick_calibration** - Calibrate perceptual axes for intent mapping

## Reference

- **Spec File**: `playbooks/specs/sonic_intent_card.json`
