---
playbook_code: sonic_variation
version: 1.0.0
locale: en
name: "Reference Audio Variation Generation"
description: "Preserve fingerprint but generate new segments"
kind: user_workflow
capability_code: sonic_space
---

# Reference Audio Variation Generation

Preserve fingerprint but generate new segments

## Overview

The Reference Audio Variation Generation playbook generates new audio segments while preserving the sonic fingerprint of a reference audio. It creates variations that maintain core characteristics but offer new creative possibilities.

**Key Features:**
- Preserve sonic fingerprint from reference
- Generate new segments with variations
- Maintain core audio characteristics
- Create diverse variations from single reference

**Purpose:**
This playbook enables users to create multiple variations of a reference sound while maintaining its essential characteristics. It's useful for creating sound libraries with consistent character but diverse options.

**Related Playbooks:**
- `sonic_fingerprint_extract` - Extract fingerprint from reference
- `sonic_dsp_transform` - Apply transformations for variations
- `sonic_prospecting_lite` - Generate variations through prospecting

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_variation.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Load Reference

Load reference audio

- **Action**: `load_reference`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Extract Fingerprint

Extract and preserve fingerprint

- **Action**: `extract_fingerprint`
- **Tool**: `sonic_space.sonic_fingerprint_extractor`
  - ✅ Format: `capability.tool_name`

### Step 3: Generate Variation

Generate new segments preserving fingerprint

- **Action**: `generate_variation`
- **Tool**: `sonic_space.sonic_dsp_transform`
  - ✅ Format: `capability.tool_name`

## Guardrails

No guardrails defined.

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **Sound Library Expansion**
   - Create variations from reference sounds
   - Maintain consistent character across variations
   - Build diverse sound collections

2. **Brand Consistency**
   - Generate variations maintaining brand audio fingerprint
   - Create brand-consistent sound libraries
   - Preserve brand identity across variations

3. **Creative Exploration**
   - Explore variations while preserving core characteristics
   - Generate creative alternatives
   - Maintain reference quality

## Examples

### Example 1: Generate Variations

```json
{
  "reference_audio_id": "audio_123",
  "variation_count": 5,
  "preserve_fingerprint": true
}
```

**Expected Output:**
- Multiple variation segments
- All variations preserve reference fingerprint
- Diverse but consistent character

## Technical Details

**Variation Generation:**
- Extracts and preserves reference fingerprint
- Applies controlled transformations
- Maintains core characteristics
- Generates diverse variations

**Tool Dependencies:**
- `sonic_audio_analyzer` - Load reference audio
- `sonic_fingerprint_extractor` - Extract and preserve fingerprint
- `sonic_dsp_transform` - Generate variations

## Related Playbooks

- **sonic_fingerprint_extract** - Extract fingerprint from reference
- **sonic_dsp_transform** - Apply transformations for variations
- **sonic_prospecting_lite** - Generate variations through prospecting

## Reference

- **Spec File**: `playbooks/specs/sonic_variation.json`
