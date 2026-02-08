---
playbook_code: sonic_quick_calibration
version: 1.0.0
locale: en
name: "Perceptual Axes Quick Calibration"
description: "Calibrate 3 core perceptual axes (warmth/brightness/spatiality) with small annotation set"
kind: user_workflow
capability_code: sonic_space
---

# Perceptual Axes Quick Calibration

Calibrate 3 core perceptual axes (warmth/brightness/spatiality) with small annotation set

## Overview

The Perceptual Axes Quick Calibration playbook calibrates the three core perceptual axes (warmth, brightness, spatiality) using a small annotation set. This enables stable steering in the latent space and precise dimension-based navigation.

**Key Features:**
- Calibrate 3 core axes with minimal annotations (30 pairs per axis)
- Pairwise comparison annotation collection
- Inter-annotator agreement validation
- Direction vector computation from annotations
- Steer consistency validation

**Purpose:**
This playbook establishes the perceptual axes that enable dimension-based sound navigation. Without calibration, dimension steering is unreliable and navigation results are inconsistent.

**Related Playbooks:**
- `sonic_embedding_build` - Build embeddings before calibration
- `sonic_navigation` - Use calibrated axes for dimension-based search
- `sonic_prospecting_lite` - Use calibrated axes for sound generation

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_quick_calibration.json`

## Inputs

### Required Inputs

- **target_axes** (`array[string]`)
  - Target axes to calibrate
  - Default: `['warmth', 'brightness', 'spatiality']`

### Optional Inputs

- **pairs_per_axis** (`integer`)
  - Minimum number of annotation pairs per axis
  - Default: `30`

- **annotators** (`integer`)
  - Number of annotators for cross-validation
  - Default: `2`

- **agreement_threshold** (`float`)
  - Inter-annotator agreement threshold
  - Default: `0.7`

- **embedding_model** (`string`)
  - Embedding model to use for vector calculation
  - Default: `clap`

## Outputs

**Artifacts:**

- `perceptual_axes_model`
  - Schema defined in spec file

## Steps

### Step 1: Load Candidate Segments

Load audio segments for pairwise comparison

- **Action**: `load_segments`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Generate Pairwise Comparisons

Generate audio pairs with large differences for each axis

- **Action**: `generate_pairs`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Collect Annotations

Collect pairwise comparison annotations from annotators

- **Action**: `collect_annotations`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Calculate Inter-Annotator Agreement

Calculate agreement between annotators

- **Action**: `calculate_agreement`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: agreement_score

### Step 5: Compute Axis Direction Vectors

Calculate direction vectors from annotations and embeddings

- **Action**: `compute_directions`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Validate Calibration

Validate steer consistency along calibrated axes

- **Action**: `validate_calibration`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 7: Save Calibration Model

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **insufficient_annotations**
  - Rule: Must have at least pairs_per_axis annotations per axis
  - Action: `require_more_annotations`

- **low_agreement**
  - Rule: Inter-annotator agreement below threshold
  - Action: `require_review_and_reannotation`

- **invalid_direction**
  - Rule: Direction vector must be non-zero and normalized
  - Action: `recalculate_or_fail`

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **Initial System Calibration**
   - Calibrate axes when setting up new Sonic Space instance
   - Establish baseline perceptual dimensions
   - Enable dimension-based navigation

2. **Axis Refinement**
   - Recalibrate axes with more annotations
   - Improve steer consistency
   - Adjust for specific use cases

3. **Custom Axis Calibration**
   - Calibrate custom axes beyond core 3
   - Domain-specific dimensions
   - Specialized navigation needs

## Examples

### Example 1: Standard 3-Axis Calibration

```json
{
  "target_axes": ["warmth", "brightness", "spatiality"],
  "pairs_per_axis": 30,
  "annotators": 2,
  "agreement_threshold": 0.7,
  "embedding_model": "clap"
}
```

**Expected Output:**
- `perceptual_axes_model` artifact with:
  - Direction vectors for each axis
  - Calibration statistics
  - Steer consistency scores (> 80% target)

## Technical Details

**Calibration Process:**
1. Load candidate segments with large differences
2. Generate pairwise comparisons for each axis
3. Collect annotations from multiple annotators
4. Calculate inter-annotator agreement
5. Compute direction vectors from annotations and embeddings
6. Validate calibration (steer consistency > 80%)
7. Save calibration model

**Core Axes:**
- **Warmth**: Warm/Cold perceptual axis
- **Brightness**: Bright/Dark perceptual axis
- **Spatiality**: Spacious/Intimate perceptual axis

**Annotation Requirements:**
- Minimum 30 pairs per axis
- Multiple annotators for cross-validation
- Agreement threshold: 0.7 (70% agreement)
- Large differences between pairs for clear axis definition

**Direction Vector Computation:**
- Uses embedding differences between annotation pairs
- Computes principal direction in embedding space
- Normalizes to unit vector
- Validates non-zero and normalized

**Steer Consistency:**
- Tests calibration by steering along axis
- Measures consistency of perceptual changes
- Target: > 80% consistency
- Validates calibration quality

**Tool Dependencies:**
- `sonic_audio_analyzer` - Load segments
- `embedding_tool` - Generate embeddings for computation

**Service Dependencies:**
- `embedding_service` - Embedding generation
- `calibration_service` - Calibration computation

**Performance:**
- Estimated time: ~3600 seconds (1 hour) for full calibration
- Annotation collection is the bottleneck
- Batch processing of pairs supported

**Responsibility Distribution:**
- AI Auto: 40% (automatic pair generation and computation)
- AI Propose: 30% (annotation suggestions)
- Human Only: 30% (annotation collection and validation)

## Related Playbooks

- **sonic_embedding_build** - Build embeddings before calibration
- **sonic_navigation** - Use calibrated axes for dimension-based search
- **sonic_prospecting_lite** - Use calibrated axes for sound generation
- **sonic_perceptual_axes** - Full calibration with more axes

## Reference

- **Spec File**: `playbooks/specs/sonic_quick_calibration.json`
- **API Endpoint**: `POST /api/v1/sonic-space/perceptual/calibrate`
