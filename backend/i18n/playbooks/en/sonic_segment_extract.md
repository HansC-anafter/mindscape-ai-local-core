---
playbook_code: sonic_segment_extract
version: 1.0.0
locale: en
name: "Audio Segmentation & Feature Extraction"
description: "Segment audio into searchable chunks and extract features for C02 rerank"
kind: user_workflow
capability_code: sonic_space
---

# Audio Segmentation & Feature Extraction

Segment audio into searchable chunks and extract features for C02 rerank

## Overview

The Audio Segmentation & Feature Extraction playbook processes normalized audio assets into searchable segments and extracts audio features for reranking in the navigation pipeline. It's a critical preprocessing step that enables vector search and feature-based filtering.

**Key Features:**
- Multiple segmentation strategies (fixed-length, onset-based, silence-based, beat-aligned)
- Audio feature extraction (spectral centroid, flux, low-mid ratio, RMS, dynamic range, tempo stability, reverb ratio)
- Feature normalization to 0-100 scale for consistent reranking
- Silent segment detection and filtering
- Fade in/out application for smooth playback

**Purpose:**
This playbook prepares audio assets for embedding generation and vector search. Segments are the atomic units for search and navigation, and features are used for precise reranking in the navigation pipeline.

**Related Playbooks:**
- `sonic_asset_import` - Import assets before segmentation
- `sonic_embedding_build` - Build embeddings from segments
- `sonic_navigation` - Use segment features for reranking

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_segment_extract.json`

## Inputs

### Required Inputs

- **audio_asset_id** (`string`)
  - Audio asset ID from A01

## Outputs

**Artifacts:**

- `segment`
  - Schema defined in spec file

- `segment_index`
  - Schema defined in spec file

## Steps

### Step 1: Load Audio Asset

Load normalized audio from A01

- **Action**: `load_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Resample to Standard Rate

- **Action**: `resample`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Mix to Mono

- **Action**: `mix_channels`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Segment Audio

- **Action**: `segment_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Apply Fade In/Out

- **Action**: `apply_fades`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Detect Silent Segments

- **Action**: `detect_silence`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 7: Extract Audio Features

- **Action**: `extract_features`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 8: Normalize Features to 0-100

Scale features to 0-100 for rerank consistency

- **Action**: `normalize_features`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 9: Create Segment Index

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **min_segments**
  - Rule: Audio must produce at least 1 non-silent segment
  - Action: `reject_with_message`

- **feature_nan_check**
  - Rule: No NaN values in extracted features
  - Action: `retry_or_fail`

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **Fixed-Length Segmentation**
   - Segment long-form audio into fixed-length chunks
   - Useful for ambient sounds and background music
   - Consistent segment duration for search

2. **Onset-Based Segmentation**
   - Segment at musical onsets
   - Preserves musical structure
   - Useful for loops and rhythmic content

3. **Silence-Based Segmentation**
   - Segment at silence boundaries
   - Natural break points
   - Useful for speech and dialogue

4. **Beat-Aligned Segmentation**
   - Segment aligned to beat grid
   - Preserves musical timing
   - Useful for music production

## Examples

### Example 1: Standard Segmentation

```json
{
  "audio_asset_id": "asset_123"
}
```

**Expected Output:**
- `segment` artifacts for each extracted segment
- `segment_index` artifact with all segments
- Features normalized to 0-100 scale
- Silent segments filtered out

## Technical Details

**Segmentation Strategies:**
- `fixed_length`: Fixed-duration segments (e.g., 5 seconds)
- `onset_based`: Segment at onset detection points
- `silence_based`: Segment at silence boundaries
- `beat_aligned`: Segment aligned to beat grid

**Extracted Features:**
- `spectral_centroid`: Brightness indicator
- `spectral_flux`: Timbre change rate
- `low_mid_ratio`: Frequency balance
- `rms`: Energy level
- `dynamic_range`: Loudness variation
- `tempo_stability`: Rhythmic consistency
- `reverb_ratio`: Spatial characteristics

**Feature Normalization:**
- All features scaled to 0-100 range
- Ensures consistent reranking across different audio types
- Enables dimension-based filtering

**Processing Flow:**
1. Load normalized audio asset
2. Resample to standard rate (if needed)
3. Mix to mono (for analysis)
4. Segment audio using selected strategy
5. Apply fade in/out to segments
6. Detect and filter silent segments
7. Extract audio features for each segment
8. Normalize features to 0-100 scale
9. Create segment index

**Tool Dependencies:**
- `sonic_audio_analyzer` - Audio analysis and feature extraction

**Service Dependencies:**
- `librosa` - Audio processing and analysis
- `numpy` - Numerical computations

**Performance:**
- Estimated time: ~5 seconds per minute of audio
- Asynchronous processing for long files
- Batch processing supported

**Responsibility Distribution:**
- AI Auto: 95% (fully automated processing)
- AI Propose: 5% (strategy selection suggestions)
- Human Only: 0% (no human intervention required)

## Related Playbooks

- **sonic_asset_import** - Import assets before segmentation
- **sonic_embedding_build** - Build embeddings from segments
- **sonic_navigation** - Use segment features for reranking
- **sonic_kit_packaging** - Package segments into sound kits

## Reference

- **Spec File**: `playbooks/specs/sonic_segment_extract.json`
- **API Endpoint**: `POST /api/v1/sonic-space/segments/extract`
