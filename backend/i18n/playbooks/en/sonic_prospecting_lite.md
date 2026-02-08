---
playbook_code: sonic_prospecting_lite
version: 1.0.0
locale: en
name: "Latent Space Prospecting (Lite)"
description: "DSP interpolation/extrapolation to generate new sound candidates (P0 version)"
kind: user_workflow
capability_code: sonic_space
---

# Latent Space Prospecting (Lite)

DSP interpolation/extrapolation to generate new sound candidates (P0 version)

## Overview

The Latent Space Prospecting (Lite) playbook generates new sound candidates by interpolating between bookmarks or extrapolating along perceptual axes. It's the P0 version of sound generation that uses DSP transformations rather than AI generation.

**Key Features:**
- Interpolation between two bookmarks
- Extrapolation along perceptual axes
- DSP-based transformations (EQ, reverb, time stretch, etc.)
- Quality validation of generated candidates
- Multiple exploration strategies

**Purpose:**
This playbook enables users to explore the latent space and generate new sound variations without requiring AI generation models. It's a lightweight approach to sound generation that works with existing assets.

**Related Playbooks:**
- `sonic_bookmark` - Create bookmarks for interpolation/extrapolation
- `sonic_quick_calibration` - Calibrate axes for extrapolation
- `sonic_dsp_transform` - Apply DSP transformations
- `sonic_navigation` - Find sounds to use as bookmarks

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_prospecting_lite.json`

## Inputs

### Required Inputs

- **method** (`enum`)
  - Prospecting method: interpolate between bookmarks or extrapolate along axis
  - Options: interpolate, extrapolate

### Optional Inputs

- **bookmark_a_id** (`string`)
  - First bookmark ID (for interpolation)

- **bookmark_b_id** (`string`)
  - Second bookmark ID (for interpolation)

- **bookmark_id** (`string`)
  - Bookmark ID (for extrapolation)

- **axis** (`string`)
  - Axis name for extrapolation (warmth/brightness/spatiality)

- **direction** (`integer`)
  - Direction for extrapolation (+1 or -1)
  - Default: `1`

- **magnitude** (`float`)
  - Extrapolation magnitude (0-1)
  - Default: `0.3`

- **interpolation_steps** (`integer`)
  - Number of interpolation steps (for interpolation method)
  - Default: `3`

## Outputs

**Artifacts:**

- `prospecting_candidates`
  - Schema defined in spec file

## Steps

### Step 1: Load Bookmarks

Load bookmark(s) and representative segments

- **Action**: `load_bookmarks`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Load Audio Files

Load audio files for bookmarks

- **Action**: `load_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Generate Candidates

Generate new sound candidates using DSP

- **Action**: `generate_candidates`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Apply DSP Transformations

Apply EQ, reverb, saturation, etc. based on method and parameters

- **Action**: `apply_dsp`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Validate Candidates

Validate generated candidates (duration, quality, etc.)

- **Action**: `validate`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Create Candidate Set

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **bookmark_required**
  - Rule: At least one bookmark must be provided
  - Action: `reject_with_message`

- **interpolation_bookmarks**
  - Rule: Interpolation requires exactly 2 bookmarks
  - Action: `reject_with_message`

- **extrapolation_axis**
  - Rule: Extrapolation requires valid axis name
  - Action: `reject_with_message`

- **magnitude_range**
  - Rule: Extrapolation magnitude must be between 0 and 1
  - Action: `reject_with_message`

- **quality_check**
  - Rule: Generated candidates must pass minimal quality checks
  - Action: `reject_with_qa_report`

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **Interpolation Between Sounds**
   - Generate intermediate sounds between two bookmarks
   - Create smooth transitions
   - Explore middle ground in latent space

2. **Axis-Based Extrapolation**
   - Generate sounds by moving along perceptual axes
   - Example: Make a sound warmer, brighter, or more spacious
   - Explore dimension extremes

3. **Variation Generation**
   - Create variations of existing sounds
   - Preserve core characteristics
   - Generate multiple candidates for selection

## Examples

### Example 1: Interpolation

```json
{
  "method": "interpolate",
  "bookmark_a_id": "bookmark_123",
  "bookmark_b_id": "bookmark_456",
  "interpolation_steps": 5
}
```

**Expected Output:**
- `prospecting_candidates` artifact with 5 intermediate sounds
- Smooth transition between two bookmarks
- All candidates pass quality checks

### Example 2: Extrapolation

```json
{
  "method": "extrapolate",
  "bookmark_id": "bookmark_789",
  "axis": "warmth",
  "direction": 1,
  "magnitude": 0.5
}
```

**Expected Output:**
- `prospecting_candidates` artifact with warmer variations
- Generated by moving along warmth axis
- Quality validated

## Technical Details

**Prospecting Methods:**
- `interpolate`: Generate sounds between two bookmarks
- `extrapolate`: Generate sounds by moving along axis from bookmark

**DSP Transformations:**
- **EQ**: Frequency shaping
- **Reverb**: Spatial effects
- **Time Stretch**: Tempo changes
- **Pitch Shift**: Pitch modifications
- **Saturation**: Harmonic enhancement
- **Granular**: Granular synthesis effects

**Interpolation Process:**
1. Load two bookmarks and representative segments
2. Compute interpolation path in latent space
3. Generate intermediate positions
4. Apply DSP transformations to create sounds
5. Validate quality

**Extrapolation Process:**
1. Load bookmark and representative segment
2. Compute direction along specified axis
3. Move in direction by magnitude
4. Apply DSP transformations
5. Validate quality

**Quality Validation:**
- Duration checks
- Loudness validation
- Format verification
- Artifact detection

**Tool Dependencies:**
- `dsp_engine` - DSP transformations
- `sonic_audio_analyzer` - Audio analysis

**Service Dependencies:**
- `dsp_processing` - DSP processing pipeline
- `prospecting_lite` - Prospecting logic

**Performance:**
- Estimated time: ~60 seconds per candidate set
- Asynchronous processing
- Batch generation supported

**Responsibility Distribution:**
- AI Auto: 60% (automatic generation)
- AI Propose: 30% (parameter suggestions)
- Human Only: 10% (final selection)

## Related Playbooks

- **sonic_bookmark** - Create bookmarks for interpolation/extrapolation
- **sonic_quick_calibration** - Calibrate axes for extrapolation
- **sonic_dsp_transform** - Apply DSP transformations
- **sonic_navigation** - Find sounds to use as bookmarks
- **sonic_latent_prospecting** - Advanced prospecting (P1)

## Reference

- **Spec File**: `playbooks/specs/sonic_prospecting_lite.json`
- **API Endpoint**: `POST /api/v1/sonic-space/prospecting/generate`
