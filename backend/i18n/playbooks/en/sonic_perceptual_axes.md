---
playbook_code: sonic_perceptual_axes
version: 1.0.0
locale: en
name: "Perceptual Axes Calibration"
description: "Calibrate warm/cold, bright/dark, dry/wet perceptual axes for stable steering"
kind: user_workflow
capability_code: sonic_space
---

# Perceptual Axes Calibration

Calibrate warm/cold, bright/dark, dry/wet perceptual axes for stable steering

## Overview

The Perceptual Axes Calibration playbook calibrates perceptual axes (warm/cold, bright/dark, dry/wet) for stable steering in the latent space. It's the advanced version of `sonic_quick_calibration` that supports more axes and detailed calibration.

**Key Features:**
- Calibrate multiple perceptual axes
- Support for warm/cold, bright/dark, dry/wet axes
- Detailed calibration with more annotations
- Stable steering in latent space

**Purpose:**
This playbook establishes comprehensive perceptual axes that enable precise dimension-based sound navigation. It extends `sonic_quick_calibration` with support for more axes and detailed calibration processes.

**Related Playbooks:**
- `sonic_quick_calibration` - Quick 3-axis calibration (P0 version)
- `sonic_navigation` - Use calibrated axes for navigation
- `sonic_prospecting_lite` - Use axes for sound generation

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_perceptual_axes.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Load Calibration Data

Load calibration data for axes

- **Action**: `load_calibration_data`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Calibrate Axes

Calibrate warm/cold, bright/dark, dry/wet axes

- **Action**: `calibrate_axes`
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

1. **Comprehensive Axis Calibration**
   - Calibrate multiple perceptual axes
   - Support for warm/cold, bright/dark, dry/wet
   - Detailed calibration process

2. **Advanced Navigation**
   - Enable precise dimension-based navigation
   - Support complex multi-axis steering
   - Improve navigation accuracy

3. **Custom Axis Definition**
   - Define custom perceptual axes
   - Calibrate domain-specific dimensions
   - Support specialized use cases

## Examples

### Example 1: Calibrate Multiple Axes

```json
{
  "target_axes": ["warmth", "brightness", "spatiality", "dryness"],
  "pairs_per_axis": 50,
  "annotators": 3
}
```

**Expected Output:**
- Calibrated perceptual axes model
- Direction vectors for all axes
- Calibration statistics and validation

## Technical Details

**Calibration Process:**
- Loads calibration data for multiple axes
- Performs pairwise comparison annotation
- Computes direction vectors
- Validates calibration quality

**Supported Axes:**
- Warmth (warm/cold)
- Brightness (bright/dark)
- Spatiality (spacious/intimate)
- Dryness (dry/wet)
- Custom axes

**Tool Dependencies:**
- `sonic_axes_steer` - Axis calibration and steering

## Related Playbooks

- **sonic_quick_calibration** - Quick 3-axis calibration (P0 version)
- **sonic_navigation** - Use calibrated axes for navigation
- **sonic_prospecting_lite** - Use axes for sound generation

## Reference

- **Spec File**: `playbooks/specs/sonic_perceptual_axes.json`
