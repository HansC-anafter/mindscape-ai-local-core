---
playbook_code: sonic_dsp_transform
version: 1.0.0
locale: en
name: "DSP Transformation Engine"
description: "Low-risk DSP transformations (time stretch/EQ/reverb/granular)"
kind: user_workflow
capability_code: sonic_space
---

# DSP Transformation Engine

Low-risk DSP transformations (time stretch/EQ/reverb/granular)

## Overview

The DSP Transformation Engine playbook applies low-risk digital signal processing transformations to audio segments. It supports time stretching, pitch shifting, EQ, reverb, granular effects, and more.

**Key Features:**
- 9 transformation types (time_stretch, pitch_shift, eq_profile, filter_sweep, convolution_reverb, stereo_width, granular, glitch, bitcrush)
- 10+ built-in presets
- Parameter validation and constraints
- Safety level classification
- Real-time preview support

**Purpose:**
This playbook enables users to modify audio segments while preserving core characteristics. It's used for sound variation generation, mixing, and creative exploration.

**Related Playbooks:**
- `sonic_prospecting_lite` - Use DSP transformations for sound generation
- `sonic_variation` - Generate variations using DSP
- `sonic_master_template` - Apply mixing/mastering templates

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_dsp_transform.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Load Audio

Load audio segment for transformation

- **Action**: `load_audio`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Apply Transform

Apply DSP transformation (time stretch/EQ/reverb/granular)

- **Action**: `apply_transform`
- **Tool**: `sonic_space.sonic_dsp_transform`
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

1. **Time Stretching**
   - Adjust tempo without changing pitch
   - Sync loops to project tempo
   - Create time-based variations

2. **Pitch Shifting**
   - Transpose sounds to different keys
   - Create harmonic variations
   - Match pitch to project

3. **EQ and Filtering**
   - Shape frequency response
   - Remove unwanted frequencies
   - Enhance specific frequency bands

4. **Spatial Effects**
   - Apply reverb for spatial depth
   - Adjust stereo width
   - Create immersive soundscapes

5. **Creative Effects**
   - Granular synthesis
   - Glitch effects
   - Bitcrush for lo-fi character

## Examples

### Example 1: Time Stretch

```json
{
  "segment_id": "seg_123",
  "transform_type": "time_stretch",
  "params": {
    "stretch_factor": 1.2
  }
}
```

**Expected Output:**
- Transformed audio segment (20% slower)
- Pitch unchanged
- Quality validated

### Example 2: EQ Profile

```json
{
  "segment_id": "seg_456",
  "transform_type": "eq_profile",
  "params": {
    "profile": "warm",
    "boost_freq": 200,
    "cut_freq": 5000
  }
}
```

**Expected Output:**
- EQ-applied segment
- Warmer frequency response
- High frequencies reduced

## Technical Details

**Transformation Types:**
- `time_stretch`: Tempo change without pitch change
- `pitch_shift`: Pitch transposition
- `eq_profile`: Frequency shaping
- `filter_sweep`: Dynamic filtering
- `convolution_reverb`: Spatial reverb
- `stereo_width`: Stereo field adjustment
- `granular`: Granular synthesis
- `glitch`: Glitch effects
- `bitcrush`: Bit reduction

**Built-in Presets:**
- Warm, Bright, Dark, Spacious
- Lo-fi, Hi-fi
- Vintage, Modern
- And more...

**Safety Levels:**
- **Low**: Subtle changes, preserves character
- **Medium**: Moderate changes, some character shift
- **High**: Significant changes, character may change

**Parameter Validation:**
- Range constraints for all parameters
- Safety level checks
- Quality preservation rules

**Tool Dependencies:**
- `sonic_audio_analyzer` - Load audio segments
- `sonic_dsp_transform` - Apply transformations

**Service Dependencies:**
- `dsp_processing` - DSP processing pipeline (librosa, ffmpeg)

**Performance:**
- Real-time preview for short segments
- Batch processing for multiple segments
- Asynchronous processing for long files

## Related Playbooks

- **sonic_prospecting_lite** - Use DSP transformations for sound generation
- **sonic_variation** - Generate variations using DSP
- **sonic_master_template** - Apply mixing/mastering templates
- **sonic_kit_packaging** - Create variations for sound kits

## Reference

- **Spec File**: `playbooks/specs/sonic_dsp_transform.json`
