---
playbook_code: sonic_inpainting
version: 1.0.0
locale: en
name: "Local Editing"
description: "Edit only a segment, frequency band, or element"
kind: user_workflow
capability_code: sonic_space
---

# Local Editing

Edit only a segment, frequency band, or element

## Overview

The Local Editing (Inpainting) playbook enables precise editing of specific segments, frequency bands, or elements within audio without affecting the rest of the audio. It's similar to image inpainting but for audio.

**Key Features:**
- Edit specific audio regions
- Target frequency bands
- Edit individual elements
- Preserve surrounding audio

**Purpose:**
This playbook enables users to make precise edits to audio without affecting the entire file. It's useful for removing unwanted sounds, enhancing specific elements, or making targeted improvements.

**Related Playbooks:**
- `sonic_dsp_transform` - Apply transformations
- `sonic_segment_extract` - Extract segments for editing
- `sonic_variation` - Generate variations

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_inpainting.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Identify Region

Identify segment/frequency band/element to edit

- **Action**: `identify_region`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Apply Inpainting

Apply local editing

- **Action**: `apply_inpainting`
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

1. **Noise Removal**
   - Remove unwanted sounds from specific regions
   - Clean up audio segments
   - Improve audio quality

2. **Element Enhancement**
   - Enhance specific elements (instruments, vocals)
   - Target frequency bands
   - Make precise improvements

3. **Selective Editing**
   - Edit only affected regions
   - Preserve rest of audio
   - Maintain audio integrity

## Examples

### Example 1: Remove Noise

```json
{
  "audio_asset_id": "asset_123",
  "region": {"start": 10.0, "end": 15.0},
  "edit_type": "noise_removal"
}
```

**Expected Output:**
- Edited audio with noise removed
- Surrounding audio preserved
- Quality maintained

## Technical Details

**Inpainting Process:**
- Identifies target region or frequency band
- Applies editing operation
- Preserves surrounding audio
- Maintains audio quality

**Edit Types:**
- Noise removal
- Element enhancement
- Frequency band editing
- Selective processing

**Tool Dependencies:**
- Audio editing and inpainting tools

## Related Playbooks

- **sonic_dsp_transform** - Apply transformations
- **sonic_segment_extract** - Extract segments for editing
- **sonic_variation** - Generate variations

## Reference

- **Spec File**: `playbooks/specs/sonic_inpainting.json`
