---
playbook_code: sonic_version_control
version: 1.0.0
locale: en
name: "Asset Version Control & Rollback"
description: "Audio Git / Asset Registry"
kind: user_workflow
capability_code: sonic_space
---

# Asset Version Control & Rollback

Audio Git / Asset Registry

## Overview

The Asset Version Control & Rollback playbook provides version control for audio assets, similar to Git for code. It tracks changes, creates version snapshots, and enables rollback to previous versions.

**Key Features:**
- Create version snapshots
- Track changes (Audio Git)
- Register assets in Asset Registry
- Enable rollback to previous versions

**Purpose:**
This playbook enables version control for audio assets, allowing users to track changes, maintain history, and rollback to previous versions when needed. It's essential for iterative sound design workflows.

**Related Playbooks:**
- `sonic_decision_trace` - Track decision history
- `sonic_asset_import` - Import assets for version control
- `sonic_dsp_transform` - Track transformations as versions

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_version_control.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Create Version

Create new version snapshot

- **Action**: `create_version`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Track Changes

Track changes (Audio Git)

- **Action**: `track_changes`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Register Asset

Register in Asset Registry

- **Action**: `register_asset`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

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

1. **Version Tracking**
   - Track changes to audio assets
   - Create version snapshots
   - Maintain asset history

2. **Rollback Capability**
   - Rollback to previous versions
   - Recover from unwanted changes
   - Maintain version history

3. **Asset Registry**
   - Register assets in central registry
   - Track asset versions
   - Enable asset discovery

## Examples

### Example 1: Create Version

```json
{
  "asset_id": "asset_123",
  "version_description": "Added reverb processing",
  "create_snapshot": true
}
```

**Expected Output:**
- New version snapshot created
- Changes tracked in version history
- Asset registered in Asset Registry

## Technical Details

**Version Control:**
- Creates version snapshots
- Tracks changes (similar to Git)
- Maintains version history
- Enables rollback

**Asset Registry:**
- Central registry for all assets
- Version tracking
- Asset discovery and management

**Tool Dependencies:**
- Version control system
- Asset registry

## Related Playbooks

- **sonic_decision_trace** - Track decision history
- **sonic_asset_import** - Import assets for version control
- **sonic_dsp_transform** - Track transformations as versions

## Reference

- **Spec File**: `playbooks/specs/sonic_version_control.json`
