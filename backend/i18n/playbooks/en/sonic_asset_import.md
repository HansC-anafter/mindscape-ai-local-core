---
playbook_code: sonic_asset_import
version: 1.1.0
locale: en
name: "Audio Asset Import & Normalization"
description: "Import, normalize, and QA-check audio assets from various sources"
kind: user_workflow
capability_code: sonic_space
---

# Audio Asset Import & Normalization

Import, normalize, and QA-check audio assets from various sources

## Overview

The Audio Asset Import & Normalization playbook is the entry point for bringing audio assets into the Sonic Space system. It handles importing audio files from various sources (local files, cloud storage, or video files), normalizes them to a standard format, and performs basic quality assurance checks.

**Key Features:**
- Supports multiple audio formats (WAV, MP3, FLAC, AAC, M4A) and video formats (MP4, MOV) for audio extraction
- Automatic format normalization to 44.1kHz sample rate and -14 LUFS loudness
- Minimal QA checks to ensure audio quality (no clipping, reasonable loudness range, valid duration)
- Automatic metadata extraction (duration, peak level, dynamic range, frequency profile)
- Asynchronous processing for large files

**Purpose:**
This playbook prepares audio assets for further processing in the Sonic Space pipeline. All imported assets must pass this playbook before they can be used in other playbooks like `sonic_segment_extract`, `sonic_embedding_build`, or `sonic_navigation`.

**Related Playbooks:**
- `sonic_license_governance` - Register license information for imported assets
- `sonic_segment_extract` - Segment normalized audio into searchable chunks
- `sonic_embedding_build` - Build embeddings from imported assets

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_asset_import.json`

## Inputs

### Required Inputs

- **source_files** (`array[file]`)
  - Audio files (wav/mp3/flac) or video files (for audio extraction)
  - Accepted formats: wav, mp3, flac, aac, m4a, mp4, mov

### Optional Inputs

- **source_url** (`string`)
  - Cloud link (Google Drive / Dropbox)

- **target_sample_rate** (`integer`)
  - Target sample rate
  - Default: `44100`

- **target_loudness** (`float`)
  - Target loudness (LUFS)
  - Default: `-14.0`

- **channel_mode** (`enum`)
  - Default: `stereo`
  - Options: mono, stereo

## Outputs

**Artifacts:**

- `audio_asset`
  - Schema defined in spec file

## Steps

### Step 1: Validate Input Format

Check file format and size

- **Action**: `validate`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Extract Audio from Video

Extract audio track from video files

- **Action**: `extract_audio_from_video`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.source_files contains video format

### Step 3: Format Normalization

- **Action**: `normalize`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Generate Metadata

- **Action**: `analyze_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: duration, peak_level, dynamic_range, frequency_profile

### Step 5: Minimal QA Check

Basic quality checks (merged from F02 to avoid P0/P1 dependency)

- **Action**: `qa_gate`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Create Asset Record

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **format_validation**
  - Rule: Only accept supported audio/video formats
  - Action: `reject_with_message`

- **file_size_limit**
  - Rule: Single file < 500MB
  - Action: `reject_with_message`

- **duration_limit**
  - Rule: Single file duration < 60 minutes
  - Action: `warn_and_proceed`

- **qa_gate**
  - Rule: Must pass minimal QA checks
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

1. **Bulk Audio Import**
   - Import multiple audio files from local storage or cloud links
   - Automatically normalize all files to consistent format
   - Batch process large collections of audio assets

2. **Video Audio Extraction**
   - Extract audio tracks from video files (MP4, MOV)
   - Convert video audio to standard audio format
   - Prepare extracted audio for further processing

3. **Quality Assurance**
   - Validate audio files meet minimum quality standards
   - Detect clipping, excessive loudness, or format issues
   - Generate QA reports for problematic files

4. **Asset Preparation**
   - Prepare audio assets for embedding generation
   - Normalize format for consistent processing
   - Extract metadata for cataloging and search

## Examples

### Example 1: Import Single Audio File

```json
{
  "source_files": ["/path/to/audio.wav"],
  "target_sample_rate": 44100,
  "target_loudness": -14.0,
  "channel_mode": "stereo"
}
```

**Expected Output:**
- `audio_asset` artifact with normalized audio file
- Metadata including duration, peak level, dynamic range
- QA check results

### Example 2: Import from Cloud Storage

```json
{
  "source_url": "https://drive.google.com/file/d/xxx",
  "target_sample_rate": 44100,
  "target_loudness": -14.0
}
```

**Expected Output:**
- `audio_asset` artifact with downloaded and normalized audio
- Source tracking information

### Example 3: Extract Audio from Video

```json
{
  "source_files": ["/path/to/video.mp4"],
  "target_sample_rate": 44100,
  "target_loudness": -14.0
}
```

**Expected Output:**
- `audio_asset` artifact with extracted and normalized audio track
- Original video metadata preserved

## Technical Details

**Tool Dependencies:**
- `sonic_audio_analyzer` - Audio analysis and metadata extraction

**Service Dependencies:**
- `ffmpeg` - Audio/video processing and format conversion

**Processing Flow:**
1. File validation (format, size checks)
2. Audio extraction (if video file)
3. Format normalization (sample rate, loudness, channels)
4. Metadata extraction (duration, peak, dynamic range, frequency profile)
5. QA checks (clipping, loudness range, duration, sample rate)
6. Asset record creation

**Performance:**
- Estimated time: ~5 seconds per file
- Asynchronous processing for large files
- Supports files up to 500MB
- Maximum duration: 60 minutes (with warning)

**Output Schema:**
The `audio_asset` artifact contains:
- Asset ID and workspace/tenant information
- Original and normalized file paths
- Format information (sample rate, bit depth, channels)
- Metadata (duration, peak level, LUFS, dynamic range)
- QA results (passed checks, failed checks with values)
- Import timestamp and status

## Related Playbooks

- **sonic_license_governance** - Register license information for imported assets
- **sonic_segment_extract** - Segment normalized audio into searchable chunks
- **sonic_embedding_build** - Build embeddings from imported assets
- **sonic_navigation** - Search and navigate imported assets

## Reference

- **Spec File**: `playbooks/specs/sonic_asset_import.json`
- **API Endpoint**: `POST /api/v1/sonic-space/assets/import`
