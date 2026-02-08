---
playbook_code: sonic_asset_sourcing
version: 1.0.0
locale: en
name: "Asset Sourcing & Licensing Pipeline"
description: "Establish stable commercial asset sources (self-recorded/purchased/CC0)"
kind: user_workflow
capability_code: sonic_space
---

# Asset Sourcing & Licensing Pipeline

Establish stable commercial asset sources (self-recorded/purchased/CC0)

## Overview

The Asset Sourcing & Licensing Pipeline playbook establishes stable commercial asset sources for the Sonic Space system. It handles the registration and verification of audio assets from various sources including self-recorded content, purchased licenses, CC0/public domain materials, and partnership agreements.

**Key Features:**
- Support for multiple source types (self-produced, licensed purchase, CC0/public domain, partnership)
- Automatic license document parsing and verification
- Risk level assessment based on source type and license terms
- Usage scope and restriction tracking
- Source record creation for asset provenance

**Purpose:**
This playbook is the foundation for risk mitigation in the Sonic Space system. It ensures all audio assets have proper source documentation and risk assessment before they enter the system. It's a critical pre-processing step that protects against legal issues and ensures compliance.

**Related Playbooks:**
- `sonic_asset_import` - Import assets after sourcing is established
- `sonic_license_governance` - Register detailed license information
- `sonic_export_gate` - Use source records for export compliance

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_asset_sourcing.json`

## Inputs

### Required Inputs

- **source_type** (`enum`)
  - Asset source type
  - Options: self_produced, licensed_purchase, cc0_public_domain, partnership

### Optional Inputs

- **source_url** (`string`)
  - Source URL or receipt link

- **license_document** (`file`)
  - License document or receipt

- **purchase_date** (`date`)
  - Purchase or acquisition date

- **provider_name** (`string`)
  - Provider or platform name (e.g., Artlist, Epidemic Sound)

- **target_count** (`integer`)
  - Target number of assets to acquire
  - Default: `1`

## Outputs

**Artifacts:**

- `asset_source`
  - Schema defined in spec file

## Steps

### Step 1: Validate Source Type

Verify source type is valid and supported

- **Action**: `validate`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Collect Source Information

Gather source URL, receipt, license document, etc.

- **Action**: `collect_metadata`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Verify License

Parse and verify license document

- **Action**: `verify_license`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.license_document exists

### Step 4: Assess Risk Level

Evaluate risk level based on source type and license

- **Action**: `risk_assessment`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: risk_level, risk_factors

### Step 5: Create Source Record

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **unknown_source_block**
  - Rule: Unknown source type must be manually reviewed
  - Action: `require_human_approval`

- **high_risk_alert**
  - Rule: High/Critical risk sources require explicit approval
  - Action: `require_human_approval`

- **license_verification**
  - Rule: Commercial use requires verified license document
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

1. **Self-Produced Asset Registration**
   - Register self-recorded or self-composed audio assets
   - Document creation date and ownership
   - Mark as low-risk for internal use

2. **Licensed Purchase Registration**
   - Register assets purchased from stock libraries (Artlist, Epidemic Sound, etc.)
   - Parse purchase receipts and license documents
   - Extract usage terms and restrictions

3. **CC0/Public Domain Registration**
   - Register Creative Commons Zero or public domain assets
   - Verify public domain status
   - Document attribution requirements (if any)

4. **Partnership Asset Registration**
   - Register assets from partnership agreements
   - Document partnership terms
   - Track usage restrictions and obligations

## Examples

### Example 1: Register Purchased Asset

```json
{
  "source_type": "licensed_purchase",
  "provider_name": "Artlist",
  "source_url": "https://artlist.io/receipt/xxx",
  "license_document": "/path/to/license.pdf",
  "purchase_date": "2026-01-01",
  "target_count": 50
}
```

**Expected Output:**
- `asset_source` artifact with:
  - Source type: licensed_purchase
  - Provider: Artlist
  - Risk level: low (typically for purchased assets)
  - Usage scope extracted from license document
  - Source record created

### Example 2: Register Self-Produced Asset

```json
{
  "source_type": "self_produced",
  "purchase_date": "2026-01-01",
  "target_count": 1
}
```

**Expected Output:**
- `asset_source` artifact with:
  - Source type: self_produced
  - Risk level: low
  - Full usage rights (commercial, broadcast, streaming, etc.)
  - No restrictions

## Technical Details

**Source Types:**
- `self_produced`: Self-recorded or self-composed assets (lowest risk)
- `licensed_purchase`: Purchased from stock libraries (low risk, with usage restrictions)
- `cc0_public_domain`: CC0 or public domain assets (low risk, may require attribution)
- `partnership`: Assets from partnership agreements (variable risk, depends on terms)

**Risk Assessment:**
- **Low**: Self-produced, properly licensed purchases, verified CC0
- **Medium**: Partnership assets with unclear terms, limited license scope
- **High**: Unclear licensing, missing documentation, expired licenses
- **Critical**: Potential copyright issues, unverified sources

**License Verification:**
- Parses license documents (PDF, text, etc.)
- Extracts usage scope (commercial, broadcast, streaming, derivative, redistribution)
- Identifies restrictions (territories, platforms, duration limits)
- Validates license expiration dates

**Source Record Structure:**
`asset_source` artifact contains:
- Source type and provider information
- License document path and verification status
- Risk level and risk factors
- Allowed usage scope
- Restrictions (territories, platforms, duration)
- Purchase/acquisition date
- Creation metadata

**Responsibility Distribution:**
- AI Auto: 10% (automatic validation and parsing)
- AI Propose: 30% (risk assessment suggestions)
- Human Only: 60% (final approval, especially for high-risk sources)

**Tool Dependencies:**
- License document parser
- Risk assessment engine

**Performance:**
- Estimated time: ~30 seconds per source
- Supports batch registration
- Asynchronous processing for large batches

## Related Playbooks

- **sonic_asset_import** - Import assets after sourcing is established
- **sonic_license_governance** - Register detailed license information
- **sonic_export_gate** - Use source records for export compliance
- **sonic_kit_packaging** - Aggregate source information for kits

## Reference

- **Spec File**: `playbooks/specs/sonic_asset_sourcing.json`
- **API Endpoint**: `POST /api/v1/sonic-space/sources`
