---
playbook_code: sonic_cross_media
version: 1.0.0
locale: en
name: "Cross-Media Application"
description: "Apply same fingerprint across multiple media"
kind: user_workflow
capability_code: sonic_space
---

# Cross-Media Application

Apply same fingerprint across multiple media

## Overview

The Cross-Media Application playbook applies the same sonic fingerprint across multiple media types, enabling consistent brand audio identity across different platforms and formats.

**Key Features:**
- Extract sonic fingerprint from source
- Apply fingerprint to multiple media types
- Maintain brand consistency across media
- Support cross-platform audio identity

**Purpose:**
This playbook enables users to maintain consistent brand audio identity across different media types and platforms. It ensures that brand audio characteristics are preserved when applied to different contexts.

**Related Playbooks:**
- `sonic_fingerprint_extract` - Extract fingerprint from source
- `sonic_dsp_transform` - Apply fingerprint to media
- `sonic_logo_gen` - Generate brand sonic logos

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_cross_media.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Extract Fingerprint

Extract sonic fingerprint from source

- **Action**: `extract_fingerprint`
- **Tool**: `sonic_space.sonic_fingerprint_extractor`
  - ✅ Format: `capability.tool_name`

### Step 2: Apply to Media

Apply fingerprint across multiple media

- **Action**: `apply_to_media`
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

1. **Brand Consistency**
   - Apply brand fingerprint across media
   - Maintain audio identity consistency
   - Support cross-platform branding

2. **Multi-Media Projects**
   - Apply same fingerprint to video, audio, interactive media
   - Maintain consistent audio character
   - Support unified brand experience

## Examples

### Example 1: Apply Fingerprint

```json
{
  "source_fingerprint_id": "fingerprint_123",
  "target_media": ["video_001", "audio_002", "interactive_003"]
}
```

**Expected Output:**
- All target media with applied fingerprint
- Consistent brand audio identity
- Cross-media consistency maintained

## Technical Details

**Cross-Media Application:**
- Extracts fingerprint from source
- Applies to multiple media types
- Maintains brand consistency
- Supports various media formats

**Tool Dependencies:**
- `sonic_fingerprint_extractor` - Extract fingerprint
- `sonic_dsp_transform` - Apply to media

## Related Playbooks

- **sonic_fingerprint_extract** - Extract fingerprint from source
- **sonic_dsp_transform** - Apply fingerprint to media
- **sonic_logo_gen** - Generate brand sonic logos

## Reference

- **Spec File**: `playbooks/specs/sonic_cross_media.json`
