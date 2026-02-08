---
playbook_code: sonic_export_gate
version: 1.0.0
locale: en
name: "Export Compliance Gate"
description: "Final compliance check before export (license/watermark/tracking)"
kind: user_workflow
capability_code: sonic_space
---

# Export Compliance Gate

Final compliance check before export (license/watermark/tracking)

## Overview

The Export Compliance Gate playbook is the final checkpoint before audio assets leave the Sonic Space system. It performs comprehensive compliance checks including license verification, watermark application, and tracking setup.

**Key Features:**
- Multi-layer compliance checking
- Risk level assessment
- Automatic watermark application for high-risk assets
- Audit logging for all exports
- License verification
- Usage scope validation

**Purpose:**
This playbook ensures all exported audio assets comply with legal requirements and usage restrictions. It's the last line of defense against unauthorized or non-compliant exports.

**Related Playbooks:**
- `sonic_license_governance` - Verify license cards before export
- `sonic_kit_packaging` - Package assets before export
- `sonic_navigation` - Select assets for export

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_export_gate.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Check License

Check license compliance

- **Action**: `check_license`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Apply Watermark

Apply watermark if needed

- **Action**: `apply_watermark`
- **Tool**: `sonic_space.sonic_export_gate`
  - ✅ Format: `capability.tool_name`

### Step 3: Final Check

Final compliance check before export

- **Action**: `final_check`
- **Tool**: `sonic_space.sonic_export_gate`
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

1. **Commercial Export Verification**
   - Verify license compliance for commercial use
   - Check usage scope restrictions
   - Apply watermarks if required

2. **High-Risk Asset Protection**
   - Identify high/critical risk assets
   - Apply watermarks automatically
   - Log export for audit trail

3. **License Expiry Check**
   - Verify licenses haven't expired
   - Block exports of expired licenses
   - Alert on upcoming expirations

4. **Bulk Export Compliance**
   - Check multiple assets at once
   - Aggregate compliance status
   - Generate compliance report

## Examples

### Example 1: Standard Export Check

```json
{
  "asset_ids": ["asset_123", "asset_456"],
  "target_usage": "commercial",
  "apply_watermark": false
}
```

**Expected Output:**
- Compliance status for each asset
- License verification results
- Export approval or rejection

### Example 2: High-Risk Asset Export

```json
{
  "asset_ids": ["asset_789"],
  "target_usage": "commercial",
  "apply_watermark": true
}
```

**Expected Output:**
- Compliance check passed
- Watermark applied to asset
- Audit log entry created
- Export approved with watermark

## Technical Details

**Compliance Checks:**
1. License verification (valid, not expired)
2. Usage scope validation (matches target usage)
3. Risk level assessment (low/medium/high/critical)
4. Attribution requirements check

**Watermark Application:**
- Applied automatically for high/critical risk assets
- Inaudible watermark for tracking
- Metadata watermark in file headers
- Watermark preview available

**Risk Levels:**
- **Low**: Self-owned, properly licensed
- **Medium**: CC-licensed with restrictions
- **High**: Unclear licensing, client-provided
- **Critical**: Potential copyright issues

**Audit Logging:**
- All export attempts logged
- Includes asset IDs, user, timestamp
- Compliance status recorded
- Watermark application tracked

**Tool Dependencies:**
- `sonic_export_gate` - Compliance checking and watermarking

**Export Request Schema:**
The export request includes:
- Asset IDs to export
- Target usage scenario
- Watermark preferences
- Export format requirements

## Related Playbooks

- **sonic_license_governance** - Verify license cards before export
- **sonic_kit_packaging** - Package assets before export
- **sonic_navigation** - Select assets for export
- **sonic_asset_import** - Import assets that may be exported

## Reference

- **Spec File**: `playbooks/specs/sonic_export_gate.json`
