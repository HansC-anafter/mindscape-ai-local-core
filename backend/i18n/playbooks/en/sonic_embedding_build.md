---
playbook_code: sonic_embedding_build
version: 1.0.0
locale: en
name: "Embedding Build"
description: "Audio → Vector vectorization"
kind: user_workflow
capability_code: sonic_space
---

# Embedding Build

Audio → Vector vectorization

## Overview

The Embedding Build playbook converts audio segments into vector embeddings that enable semantic search in the latent space. It's the foundation for vector-based sound navigation and discovery.

**Key Features:**
- Support for multiple embedding models (CLAP, AudioCLIP, Wav2Vec2)
- Batch embedding generation
- Vector indexing for fast similarity search
- Embedding statistics and quality metrics

**Purpose:**
This playbook builds the embedding index that powers vector search in `sonic_navigation`. Without embeddings, semantic search is not possible.

**Related Playbooks:**
- `sonic_segment_extract` - Extract segments before embedding
- `sonic_navigation` - Use embeddings for vector search
- `sonic_quick_calibration` - Calibrate perceptual axes using embeddings

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_embedding_build.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Load Segments

Load audio segments for embedding

- **Action**: `load_segments`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Generate Embeddings

Generate audio embeddings using CLAP/AudioCLIP

- **Action**: `generate_embeddings`
- **Tool**: `sonic_space.sonic_embedding_generator`
  - ✅ Format: `capability.tool_name`

### Step 3: Index Embeddings

Index embeddings for vector search

- **Action**: `index_embeddings`
- **Tool**: `sonic_space.sonic_vector_search`
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

1. **Initial Index Building**
   - Build embedding index for new audio collection
   - Process all segments in batch
   - Create searchable vector database

2. **Incremental Updates**
   - Add new segments to existing index
   - Update embeddings for modified segments
   - Maintain index consistency

3. **Model Comparison**
   - Generate embeddings with different models
   - Compare search quality
   - Select best model for use case

## Examples

### Example 1: Build CLAP Embeddings

```json
{
  "segment_ids": ["seg_001", "seg_002", "seg_003", ...],
  "embedding_model": "clap"
}
```

**Expected Output:**
- Embedding vectors (512 dimensions for CLAP)
- Indexed in vector database
- Ready for similarity search

## Technical Details

**Embedding Models:**
- **CLAP**: 512 dimensions, text-audio joint embedding
- **AudioCLIP**: 1024 dimensions, audio-visual-text embedding
- **Wav2Vec2**: 768 dimensions, self-supervised audio representation

**Processing Flow:**
1. Load audio segments
2. Generate embeddings using selected model
3. Index embeddings in vector database (pgvector)
4. Generate index statistics

**Vector Indexing:**
- Stored in PostgreSQL with pgvector extension
- Cosine similarity for search
- IVFFlat or HNSW index for performance
- Batch insertion supported

**Tool Dependencies:**
- `sonic_audio_analyzer` - Load segments
- `sonic_embedding_generator` - Generate embeddings
- `sonic_vector_search` - Index embeddings

**Performance:**
- CLAP: ~0.1 seconds per segment
- AudioCLIP: ~0.2 seconds per segment
- Wav2Vec2: ~0.15 seconds per segment
- Batch processing recommended for large collections

## Related Playbooks

- **sonic_segment_extract** - Extract segments before embedding
- **sonic_navigation** - Use embeddings for vector search
- **sonic_quick_calibration** - Calibrate perceptual axes using embeddings
- **sonic_prospecting_lite** - Explore latent space using embeddings

## Reference

- **Spec File**: `playbooks/specs/sonic_embedding_build.json`
