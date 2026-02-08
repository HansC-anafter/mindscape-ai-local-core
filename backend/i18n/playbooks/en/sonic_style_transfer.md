---
playbook_code: sonic_style_transfer
version: 1.0.0
locale: en
name: "Style Transfer & Coordinate Proximity"
description: "Steer-to-Coordinate style transfer"
kind: user_workflow
capability_code: sonic_space
---

# Style Transfer & Coordinate Proximity

Steer-to-Coordinate style transfer

## Overview

The Style Transfer playbook applies the style characteristics of one audio to another, similar to neural style transfer for images. It enables creative sound transformation while preserving content structure.

**Key Features:**
- Transfer style from reference audio
- Preserve content structure
- Apply style characteristics
- Create stylized variations

**Purpose:**
This playbook enables users to apply the style of one audio to another, creating stylized variations while maintaining the original content structure. It's useful for creative sound design and experimentation.

**Related Playbooks:**
- `sonic_fingerprint_extract` - Extract style characteristics
- `sonic_dsp_transform` - Apply style transformations
- `sonic_variation` - Generate style variations

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_style_transfer.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Load Source

Load source audio

- **Action**: `load_source`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Load Target Style

Load target style reference

- **Action**: `load_target_style`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 3: Apply Style Transfer

Apply Steer-to-Coordinate style transfer

- **Action**: `apply_style_transfer`
- **Tool**: `sonic_space.sonic_axes_steer`
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

1. **Creative Sound Design**
   - Apply style from reference audio
   - Create stylized variations
   - Experiment with sound characteristics

2. **Brand Adaptation**
   - Apply brand style to content
   - Maintain brand audio identity
   - Create brand-consistent variations

3. **Style Experimentation**
   - Explore different style applications
   - Create unique sound combinations
   - Generate creative variations

## Examples

### Example 1: Transfer Style

```json
{
  "content_audio_id": "audio_123",
  "style_audio_id": "audio_456",
  "style_strength": 0.7
}
```

**Expected Output:**
- Stylized audio with style applied
- Content structure preserved
- Style characteristics transferred

## Technical Details

**Style Transfer:**
- Extracts style from reference audio
- Applies to content audio
- Preserves content structure
- Transfers style characteristics

**Tool Dependencies:**
- Style transfer algorithms
- Audio processing tools

## Related Playbooks

- **sonic_fingerprint_extract** - Extract style characteristics
- **sonic_dsp_transform** - Apply style transformations
- **sonic_variation** - Generate style variations

## Reference

- **Spec File**: `playbooks/specs/sonic_style_transfer.json`
