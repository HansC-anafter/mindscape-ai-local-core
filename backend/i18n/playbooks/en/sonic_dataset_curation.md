---
playbook_code: sonic_dataset_curation
version: 1.0.0
locale: en
name: "Dataset Curation"
description: "Curate Theme/Brand/Project dataset packages"
kind: user_workflow
capability_code: sonic_space
---

# Dataset Curation

Curate Theme/Brand/Project dataset packages

## Overview

The Dataset Curation playbook curates Theme/Brand/Project dataset packages by selecting and organizing audio assets into cohesive collections. It enables users to create specialized sound libraries for specific themes, brands, or projects.

**Key Features:**
- Select assets using vector search
- Organize assets into themed collections
- Create dataset packages for specific use cases
- Support for Theme/Brand/Project categorization

**Purpose:**
This playbook enables users to create curated sound libraries for specific themes, brands, or projects. It's useful for building specialized collections that match specific aesthetic or functional requirements.

**Related Playbooks:**
- `sonic_navigation` - Find assets to include in dataset
- `sonic_kit_packaging` - Package curated datasets for distribution
- `sonic_license_governance` - Ensure all assets have valid licenses

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_dataset_curation.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Select Assets

Select assets for dataset

- **Action**: `select_assets`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 2: Curate Dataset

Curate Theme/Brand/Project dataset package

- **Action**: `curate_dataset`
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

1. **Theme-Based Curation**
   - Create collections for specific themes (nature, urban, fantasy)
   - Organize sounds by aesthetic or mood
   - Build themed sound libraries

2. **Brand-Specific Collections**
   - Curate sounds matching brand identity
   - Create brand-specific sound libraries
   - Maintain brand consistency

3. **Project Datasets**
   - Organize sounds for specific projects
   - Create project-specific sound libraries
   - Support project workflows

## Examples

### Example 1: Theme Dataset

```json
{
  "dataset_name": "Nature Ambience Collection",
  "dataset_type": "theme",
  "theme": "nature",
  "selection_criteria": {
    "dimensions": {
      "warmth": [60, 80],
      "spatiality": [70, 90]
    }
  }
}
```

**Expected Output:**
- Curated dataset with nature-themed sounds
- Organized by selection criteria
- Ready for packaging or distribution

## Technical Details

**Curation Process:**
1. Select assets using vector search
2. Filter by selection criteria (dimensions, themes, etc.)
3. Organize into dataset structure
4. Create dataset package

**Dataset Types:**
- `theme`: Themed collections (nature, urban, etc.)
- `brand`: Brand-specific collections
- `project`: Project-specific collections

**Tool Dependencies:**
- `sonic_vector_search` - Find assets for curation

## Related Playbooks

- **sonic_navigation** - Find assets to include in dataset
- **sonic_kit_packaging** - Package curated datasets for distribution
- **sonic_license_governance** - Ensure all assets have valid licenses

## Reference

- **Spec File**: `playbooks/specs/sonic_dataset_curation.json`
