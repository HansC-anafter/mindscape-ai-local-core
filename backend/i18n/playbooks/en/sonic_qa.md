---
playbook_code: sonic_qa
version: 1.0.0
locale: en
name: "Quality Assurance & Consistency QA"
description: "Volume/frequency/compression detection"
kind: user_workflow
capability_code: sonic_space
---

# Quality Assurance & Consistency QA

Volume/frequency/compression detection

## Overview

The Quality Assurance & Consistency QA playbook performs comprehensive quality checks on audio assets, detecting issues with volume, frequency distribution, and compression consistency. It ensures audio assets meet quality standards before use.

**Key Features:**
- Volume level detection and validation
- Frequency band analysis
- Compression consistency checking
- Quality report generation

**Purpose:**
This playbook ensures all audio assets meet quality standards before they are used in production. It detects common audio issues and provides detailed quality reports.

**Related Playbooks:**
- `sonic_asset_import` - Perform QA after import
- `sonic_segment_extract` - QA segments after extraction
- `sonic_kit_packaging` - QA before packaging

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_qa.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Check Volume

Check volume levels

- **Action**: `check_volume`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Check Frequency

Check frequency bands

- **Action**: `check_frequency`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 3: Check Compression

Check compression consistency

- **Action**: `check_compression`
- **Tool**: `sonic_space.sonic_audio_analyzer`
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

1. **Import Quality Check**
   - Validate audio quality after import
   - Detect volume, frequency, compression issues
   - Generate quality reports

2. **Batch Quality Validation**
   - Check multiple assets at once
   - Ensure consistency across collection
   - Identify problematic files

3. **Pre-Packaging QA**
   - Validate assets before packaging
   - Ensure kit quality standards
   - Generate QA reports for distribution

## Examples

### Example 1: Standard QA Check

```json
{
  "audio_asset_id": "asset_123",
  "checks": ["volume", "frequency", "compression"]
}
```

**Expected Output:**
- QA report with:
  - Volume level analysis
  - Frequency distribution
  - Compression consistency
  - Quality score and recommendations

## Technical Details

**Quality Checks:**
- **Volume**: Detects clipping, excessive loudness, level consistency
- **Frequency**: Analyzes frequency distribution, detects missing bands
- **Compression**: Checks compression consistency, detects artifacts

**Tool Dependencies:**
- `sonic_audio_analyzer` - Audio analysis and quality detection

## Related Playbooks

- **sonic_asset_import** - Perform QA after import
- **sonic_segment_extract** - QA segments after extraction
- **sonic_kit_packaging** - QA before packaging

## Reference

- **Spec File**: `playbooks/specs/sonic_qa.json`
