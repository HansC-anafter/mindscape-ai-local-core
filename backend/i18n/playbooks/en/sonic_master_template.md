---
playbook_code: sonic_master_template
version: 1.0.0
locale: en
name: "Mixing/Mastering Template"
description: "Standardize loudness/dynamics/spatial depth"
kind: user_workflow
capability_code: sonic_space
---

# Mixing/Mastering Template

Standardize loudness/dynamics/spatial depth

## Overview

The Mixing/Mastering Template playbook standardizes audio assets to consistent loudness, dynamics, and spatial depth using predefined templates. It ensures all audio in a collection meets the same production standards.

**Key Features:**
- Standardize loudness levels
- Normalize dynamics
- Consistent spatial depth
- Template-based processing

**Purpose:**
This playbook ensures audio consistency across collections by applying standardized mixing and mastering templates. It's essential for creating professional sound libraries with consistent production quality.

**Related Playbooks:**
- `sonic_dsp_transform` - Apply DSP transformations
- `sonic_kit_packaging` - Standardize before packaging
- `sonic_qa` - Quality check after mastering

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_master_template.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Analyze Audio

Analyze loudness/dynamics/spatial depth

- **Action**: `analyze_audio`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Apply Template

Apply mixing/mastering template

- **Action**: `apply_template`
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

1. **Collection Standardization**
   - Standardize loudness across collection
   - Normalize dynamics for consistency
   - Apply consistent spatial processing

2. **Professional Production**
   - Apply professional mixing/mastering templates
   - Ensure broadcast-ready quality
   - Maintain production standards

3. **Kit Preparation**
   - Standardize before packaging
   - Ensure consistent quality in kits
   - Professional presentation

## Examples

### Example 1: Apply Mastering Template

```json
{
  "audio_asset_id": "asset_123",
  "template": "broadcast_standard",
  "target_loudness": -14.0
}
```

**Expected Output:**
- Mastered audio with standardized:
  - Loudness (-14 LUFS)
  - Dynamics (consistent range)
  - Spatial depth (template-based)

## Technical Details

**Mastering Process:**
- Analyzes current loudness, dynamics, spatial characteristics
- Applies template-based processing
- Standardizes to target specifications
- Validates output quality

**Template Types:**
- Broadcast standard
- Streaming optimized
- Lo-fi aesthetic
- Hi-fi professional

**Tool Dependencies:**
- `sonic_audio_analyzer` - Analyze audio characteristics
- `sonic_dsp_transform` - Apply mastering transformations

## Related Playbooks

- **sonic_dsp_transform** - Apply DSP transformations
- **sonic_kit_packaging** - Standardize before packaging
- **sonic_qa** - Quality check after mastering

## Reference

- **Spec File**: `playbooks/specs/sonic_master_template.json`
