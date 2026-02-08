---
playbook_code: sonic_latent_prospecting
version: 1.0.0
locale: en
name: "Latent Space Sparse Region Exploration"
description: "Explore new sounds in low-density regions, form new bookmarks"
kind: user_workflow
capability_code: sonic_space
---

# Latent Space Sparse Region Exploration

Explore new sounds in low-density regions, form new bookmarks

## Overview

The Latent Space Sparse Region Exploration playbook explores new sounds in low-density regions of the latent space, enabling discovery of unique and unexplored sound characteristics. It forms new bookmarks from these explorations.

**Key Features:**
- Identify sparse (low-density) regions in latent space
- Explore new sounds in unexplored areas
- Create bookmarks from discoveries
- Expand sound library coverage

**Purpose:**
This playbook enables users to discover new and unique sounds by exploring underutilized regions of the latent space. It's the advanced version of `sonic_prospecting_lite` that focuses on sparse region exploration.

**Related Playbooks:**
- `sonic_prospecting_lite` - Basic prospecting (P0 version)
- `sonic_bookmark` - Create bookmarks from exploration
- `sonic_navigation` - Navigate to sparse regions
- `sonic_quick_calibration` - Calibrate axes for exploration

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_latent_prospecting.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Identify Sparse Regions

Identify low-density regions in latent space

- **Action**: `identify_sparse_regions`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 2: Explore Region

Explore new sounds in sparse regions

- **Action**: `explore_region`
- **Tool**: `sonic_space.sonic_axes_steer`
  - ✅ Format: `capability.tool_name`

### Step 3: Create Bookmark

Form new bookmarks from exploration

- **Action**: `create_bookmark`
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

1. **Sparse Region Discovery**
   - Identify unexplored areas in latent space
   - Discover unique sound characteristics
   - Expand sound library diversity

2. **Novel Sound Generation**
   - Generate sounds in low-density regions
   - Create unique sound variations
   - Explore creative possibilities

3. **Library Expansion**
   - Fill gaps in sound library coverage
   - Add diverse sound characteristics
   - Improve search result variety

## Examples

### Example 1: Explore Sparse Region

```json
{
  "region_type": "sparse",
  "exploration_strategy": "density_based"
}
```

**Expected Output:**
- New sounds discovered in sparse regions
- Bookmarks created for interesting discoveries
- Expanded sound library coverage

## Technical Details

**Sparse Region Identification:**
- Analyzes embedding density in latent space
- Identifies low-density regions
- Maps unexplored areas

**Exploration Process:**
1. Identify sparse regions using density analysis
2. Explore regions using axis steering
3. Generate or discover new sounds
4. Create bookmarks for interesting discoveries

**Tool Dependencies:**
- `sonic_vector_search` - Analyze latent space density
- `sonic_axes_steer` - Navigate and explore regions

## Related Playbooks

- **sonic_prospecting_lite** - Basic prospecting (P0 version)
- **sonic_bookmark** - Create bookmarks from exploration
- **sonic_navigation** - Navigate to sparse regions
- **sonic_quick_calibration** - Calibrate axes for exploration

## Reference

- **Spec File**: `playbooks/specs/sonic_latent_prospecting.json`
