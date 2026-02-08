---
playbook_code: sonic_kit_packaging
version: 1.0.0
locale: en
name: "Sound Kit Packaging"
description: "Package SFX/Loop/Ambience packs for commercial distribution"
kind: user_workflow
capability_code: sonic_space
---

# Sound Kit Packaging

Package SFX/Loop/Ambience packs for commercial distribution

## Overview

The Sound Kit Packaging playbook is the shortest path to monetization in the Sonic Space system. Instead of making complete songs, it packages curated sound segments into commercial sound kits (SFX, Loops, Ambience) that can be distributed and sold.

**Core Concept**: The shortest path to monetization: not making songs, but making 'sound kits' - curated collections of sound effects, loops, and ambience that content creators need.

**Key Features:**
- Automatic folder structure organization
- File naming convention application
- Batch audio normalization
- Preview file generation
- Metadata and license file compilation
- README generation with usage instructions
- ZIP archive creation

**Purpose:**
This playbook transforms individual sound segments into professional, distributable sound kits. It ensures all files are properly organized, normalized, licensed, and documented for commercial distribution.

**Related Playbooks:**
- `sonic_navigation` - Find segments to include in kit
- `sonic_license_governance` - Ensure all segments have valid licenses
- `sonic_export_gate` - Final compliance check before distribution
- `sonic_segment_extract` - Extract segments for packaging

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_kit_packaging.json`

## Inputs

### Required Inputs

- **kit_name** (`string`)
  - Kit name

- **kit_type** (`enum`)
  - Type of sound kit
  - Options: sfx, loop, ambience, ui_sound, mixed

- **segment_ids** (`array[string]`)
  - List of segment IDs to package

### Optional Inputs

- **naming_convention** (`enum`)
  - File naming convention
  - Default: `descriptive`
  - Options: category_number, descriptive, brand_prefix

- **include_variations** (`boolean`)
  - Default: `True`

- **target_format** (`object`)

## Outputs

**Artifacts:**

- `sound_kit`
  - Schema defined in spec file

## Steps

### Step 1: Collect Segments

Gather all segments for packaging

- **Action**: `gather_segments`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Verify Licenses

Ensure all segments have valid licenses

- **Action**: `check_all_licenses`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Organize Folder Structure

Create standardized folder structure

- **Action**: `create_folder_structure`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Apply Naming Convention

Rename files according to convention

- **Action**: `rename_files`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Normalize Audio

Normalize loudness and peaks

- **Action**: `batch_normalize`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Generate Preview Files

Create low-quality preview files

- **Action**: `create_previews`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 7: Generate Metadata

Create metadata.json with kit information

- **Action**: `create_metadata_file`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 8: Generate License File

Compile all licenses into LICENSE.md

- **Action**: `compile_licenses`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 9: Generate README

Generate README with usage instructions

- **Action**: `generate_readme`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 10: Package Kit

Create final ZIP archive

- **Action**: `create_archive`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **license_aggregation**
  - Rule: Most restrictive license applies to kit
  - Action: `warn_and_document`

- **quality_check**
  - Rule: All files must pass audio QA
  - Action: `reject_failing_files`

- **naming_conflict**
  - Rule: Detect naming conflicts
  - Action: `auto_rename_with_suffix`

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **SFX Pack Creation**
   - Package sound effects into themed packs
   - Organize by category (UI sounds, impacts, transitions)
   - Generate preview files for marketing

2. **Loop Pack Distribution**
   - Package audio loops for music production
   - Ensure consistent tempo and key
   - Generate mix guidelines

3. **Ambience Collection**
   - Package ambient sounds for content creation
   - Organize by environment (nature, urban, indoor)
   - Include usage instructions

4. **Mixed Kit Creation**
   - Combine SFX, loops, and ambience
   - Create comprehensive sound libraries
   - Generate complete documentation

## Examples

### Example 1: SFX Pack

```json
{
  "kit_name": "UI_Sound_Effects_Vol1",
  "kit_type": "sfx",
  "segment_ids": ["seg_001", "seg_002", "seg_003", ...],
  "naming_convention": "category_number",
  "include_variations": true
}
```

**Expected Output:**
- `sound_kit` artifact with ZIP archive
- Folder structure: `UI_Sound_Effects_Vol1/audio/ui/`, `previews/`, etc.
- `sound_tokens.json` with all segment metadata
- `LICENSE.md` with aggregated licenses
- `README.md` with usage instructions

### Example 2: Loop Pack

```json
{
  "kit_name": "LoFi_Beats_Collection",
  "kit_type": "loop",
  "segment_ids": ["seg_101", "seg_102", ...],
  "naming_convention": "descriptive",
  "target_format": {
    "sample_rate": 44100,
    "bit_depth": 24,
    "format": "wav"
  }
}
```

**Expected Output:**
- `sound_kit` artifact with normalized loops
- `mix_guideline.md` with mixing instructions
- BPM and key information in metadata
- Preview files for each loop

## Technical Details

**Kit Types:**
- `sfx`: Sound effects (short, one-shot sounds)
- `loop`: Audio loops (repeating patterns)
- `ambience`: Ambient sounds (long-form, atmospheric)
- `ui_sound`: UI interaction sounds
- `mixed`: Combination of multiple types

**Naming Conventions:**
- `category_number`: `ui_click_001.wav`
- `descriptive`: `warm_ambient_nature.wav`
- `brand_prefix`: `BrandName_UI_Click.wav`

**Package Structure:**
```
{kit_name}/
├── README.md
├── LICENSE.md
├── metadata.json
├── sound_tokens.json
├── mix_guideline.md (for loops)
├── previews/
│   └── *.mp3
└── audio/
    ├── {category}/
    │   └── *.{format}
```

**License Aggregation:**
- Most restrictive license applies to entire kit
- All licenses compiled into LICENSE.md
- License compatibility checked

**Quality Checks:**
- All files must pass audio QA
- Consistent loudness normalization
- Format validation
- Naming conflict resolution

**Tool Dependencies:**
- `sonic_kit_packager` - Package creation and organization
- `sonic_audio_analyzer` - Audio quality checks

**Responsibility Distribution:**
- AI Auto: 70% (automatic packaging and organization)
- AI Propose: 20% (naming and structure suggestions)
- Human Only: 10% (final review and approval)

## Related Playbooks

- **sonic_navigation** - Find segments to include in kit
- **sonic_license_governance** - Ensure all segments have valid licenses
- **sonic_export_gate** - Final compliance check before distribution
- **sonic_segment_extract** - Extract segments for packaging
- **sonic_dsp_transform** - Create variations for kit

## Reference

- **Spec File**: `playbooks/specs/sonic_kit_packaging.json`
