---
playbook_code: sonic_license_governance
version: 1.0.0
locale: en
name: "License & Provenance Governance"
description: "Register source, assess risk, and generate license cards"
kind: user_workflow
capability_code: sonic_space
---

# License & Provenance Governance

Register source, assess risk, and generate license cards

## Overview

The License & Provenance Governance playbook is essential for managing legal compliance and risk assessment of audio assets. It registers the source of audio assets, assesses legal and compliance risks, and generates license cards that govern how assets can be used.

**Key Features:**
- Source type classification (self-owned, CC-licensed, purchased, client-provided, AI-generated)
- Automatic license document parsing and term extraction
- Risk level assessment (low, medium, high, critical)
- Usage rules generation (allowed/prohibited usage scenarios)
- License card creation with complete provenance information

**Purpose:**
This playbook ensures all audio assets have proper license documentation and risk assessment before they can be used in commercial contexts. It's a critical step in the asset ingestion pipeline that protects against legal issues.

**Related Playbooks:**
- `sonic_asset_import` - Import assets before registering licenses
- `sonic_export_gate` - Use license cards for export compliance checking
- `sonic_kit_packaging` - Aggregate licenses for sound kit distribution

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_license_governance.json`

## Inputs

### Required Inputs

- **audio_asset_id** (`string`)
  - Audio asset ID

- **source_type** (`enum`)
  - Asset source type
  - Options: self_owned, cc_licensed, purchased, client_provided, ai_generated

### Optional Inputs

- **license_document** (`file`)
  - License document file

- **usage_scope** (`object`)

- **attribution_required** (`boolean`)
  - Default: `False`

- **attribution_text** (`string`)

- **expiry_date** (`date`)

## Outputs

**Artifacts:**

- `license_card`
  - Schema defined in spec file

## Steps

### Step 1: Classify Source Type

Categorize the audio source

- **Action**: `classify`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Extract License Information

Parse license document for terms

- **Action**: `parse_license_document`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.license_document exists

### Step 3: Assess Risk Level

Evaluate legal and compliance risk

- **Action**: `risk_assessment`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: risk_level, risk_factors

### Step 4: Generate Usage Rules

Create allowed/prohibited usage rules

- **Action**: `generate_rules`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Create License Card

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **unknown_source_block**
  - Rule: Unknown source type must be manually reviewed
  - Action: `require_human_approval`

- **high_risk_alert**
  - Rule: High/Critical risk assets require explicit approval
  - Action: `require_human_approval`

- **commercial_use_check**
  - Rule: Commercial use requires verified license
  - Action: `reject_if_unverified`

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **Commercial Asset Registration**
   - Register purchased audio assets from stock libraries (Artlist, Epidemic Sound)
   - Parse license documents and extract usage terms
   - Assess risk level for commercial use

2. **CC-Licensed Asset Management**
   - Register Creative Commons licensed assets
   - Extract attribution requirements
   - Set usage scope restrictions

3. **Client-Provided Asset Governance**
   - Register assets provided by clients
   - Assess risk for client-provided content
   - Generate usage rules based on client agreements

4. **Self-Owned Asset Documentation**
   - Document self-recorded or self-composed assets
   - Mark as low-risk for internal use
   - Set appropriate usage scopes

5. **AI-Generated Asset Compliance**
   - Register AI-generated audio assets
   - Assess compliance with AI generation policies
   - Set usage restrictions if needed

## Examples

### Example 1: Register Purchased Asset

```json
{
  "audio_asset_id": "asset_123",
  "source_type": "purchased",
  "license_document": "/path/to/license.pdf",
  "usage_scope": {
    "commercial": true,
    "broadcast": true,
    "streaming": true,
    "derivative": false,
    "redistribution": false
  },
  "expiry_date": "2026-12-31"
}
```

**Expected Output:**
- `license_card` artifact with parsed license terms
- Risk level assessment (typically low for purchased assets)
- Usage rules based on license document

### Example 2: Register CC-Licensed Asset

```json
{
  "audio_asset_id": "asset_456",
  "source_type": "cc_licensed",
  "attribution_required": true,
  "attribution_text": "Music by Artist Name, CC BY 4.0",
  "usage_scope": {
    "commercial": true,
    "derivative": true,
    "redistribution": true
  }
}
```

**Expected Output:**
- `license_card` artifact with CC license information
- Attribution requirements documented
- Usage rules allowing commercial use with attribution

### Example 3: Register Self-Owned Asset

```json
{
  "audio_asset_id": "asset_789",
  "source_type": "self_owned",
  "usage_scope": {
    "commercial": true,
    "broadcast": true,
    "streaming": true,
    "derivative": true,
    "redistribution": true
  }
}
```

**Expected Output:**
- `license_card` artifact marked as self-owned
- Low risk level assessment
- Full usage rights documented

## Technical Details

**Risk Assessment Levels:**
- **Low**: Self-owned, properly licensed purchased assets
- **Medium**: CC-licensed with restrictions, client-provided with documentation
- **High**: Unclear licensing, expired licenses, missing documentation
- **Critical**: Potential copyright violations, unverified sources

**Source Type Classifications:**
- `self_owned`: Self-recorded or self-composed assets
- `cc_licensed`: Creative Commons licensed assets
- `purchased`: Purchased from stock libraries or marketplaces
- `client_provided`: Assets provided by clients
- `ai_generated`: AI-generated audio assets

**Usage Scope Fields:**
- `commercial`: Commercial use allowed
- `broadcast`: Broadcast use allowed
- `streaming`: Streaming use allowed
- `derivative`: Derivative works allowed
- `redistribution`: Redistribution allowed

**License Card Schema:**
The `license_card` artifact contains:
- Asset ID and source type
- Risk level and risk factors
- Usage scope (allowed/prohibited scenarios)
- Attribution requirements
- License expiry date
- License document reference

**Responsibility Distribution:**
- AI Auto: 30% (automatic classification and parsing)
- AI Propose: 40% (risk assessment suggestions)
- Human Only: 30% (final approval for high-risk assets)

## Related Playbooks

- **sonic_asset_import** - Import assets before registering licenses
- **sonic_export_gate** - Use license cards for export compliance checking
- **sonic_kit_packaging** - Aggregate licenses for sound kit distribution
- **sonic_navigation** - Filter assets by license compliance in search results

## Reference

- **Spec File**: `playbooks/specs/sonic_license_governance.json`
