---
playbook_code: sonic_delivery
version: 1.0.0
locale: en
name: "Delivery & License Shipping"
description: "B2B contract/packaging/certificates"
kind: user_workflow
capability_code: sonic_space
---

# Delivery & License Shipping

B2B contract/packaging/certificates

## Overview

The Delivery & License Shipping playbook handles B2B delivery of sound assets, including contract preparation, packaging, and certificate generation. It ensures professional delivery of sound kits and assets to business clients.

**Key Features:**
- Prepare B2B contracts
- Package assets for delivery
- Generate delivery certificates
- Handle licensing documentation

**Purpose:**
This playbook enables professional B2B delivery of sound assets, ensuring all legal, licensing, and documentation requirements are met before assets are delivered to clients.

**Related Playbooks:**
- `sonic_kit_packaging` - Package assets before delivery
- `sonic_license_governance` - Verify licenses before delivery
- `sonic_export_gate` - Final compliance check

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_delivery.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Prepare Delivery

Prepare B2B contract and packaging

- **Action**: `prepare_delivery`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Generate Certificates

Generate delivery certificates

- **Action**: `generate_certificates`
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

1. **B2B Asset Delivery**
   - Prepare contracts for asset delivery
   - Package assets professionally
   - Generate delivery documentation

2. **License Shipping**
   - Include license documentation
   - Generate license certificates
   - Ensure legal compliance

3. **Professional Packaging**
   - Create professional delivery packages
   - Include all required documentation
   - Ensure client-ready delivery

## Examples

### Example 1: Prepare Delivery

```json
{
  "kit_id": "kit_123",
  "client_info": {...},
  "delivery_method": "digital_download",
  "include_certificates": true
}
```

**Expected Output:**
- Packaged assets with contracts
- Delivery certificates
- License documentation
- Professional delivery package

## Technical Details

**Delivery Preparation:**
- Prepares B2B contracts
- Packages assets for delivery
- Generates certificates
- Includes all documentation

**Tool Dependencies:**
- Delivery and packaging system

## Related Playbooks

- **sonic_kit_packaging** - Package assets before delivery
- **sonic_license_governance** - Verify licenses before delivery
- **sonic_export_gate** - Final compliance check

## Reference

- **Spec File**: `playbooks/specs/sonic_delivery.json`
