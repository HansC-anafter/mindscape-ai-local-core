---
playbook_code: sonic_navigation
version: 1.1.0
locale: en
name: "Sonic Navigation"
description: "Three-stage search: Query Vector → Recall → Feature Rerank + License Filter"
kind: user_workflow
capability_code: sonic_space
---

# Sonic Navigation

Three-stage search: Query Vector → Recall → Feature Rerank + License Filter

## Overview

Sonic Navigation is the core search and discovery playbook in the Sonic Space system. It implements a three-stage search pipeline that combines vector similarity search with feature-based reranking and license compliance filtering.

**Core Concept**: Vector search finds 'similar' sounds, but feature dimensions filter out 'similar but wrong' sounds. This two-stage approach ensures both semantic similarity and precise dimensional matching.

**Three-Stage Pipeline:**
1. **Stage 1: Query Vector Construction** - Convert intent card to query vector using selected strategy
2. **Stage 2: Vector Search Recall** - Recall 3x candidates using vector similarity search
3. **Stage 3: Feature Rerank + License Filter** - Rerank by dimension match score and filter by license compliance

**Key Features:**
- Multiple query strategies (text-based, audio reference, bookmark-based)
- Dual-space architecture (Search Space + Control Space)
- License compliance filtering based on target scene
- A/B comparison preparation for decision-making
- Fast response time (< 5 seconds P95)

**Purpose:**
This playbook enables users to find audio assets that match their sonic intent while ensuring legal compliance. It's the primary interface for exploring the sonic latent space.

**Related Playbooks:**
- `sonic_intent_card` - Create intent card before navigation
- `sonic_embedding_build` - Build embedding index for search
- `sonic_decision_trace` - Record navigation decisions
- `sonic_bookmark` - Save navigation results as bookmarks

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_navigation.json`

## Inputs

### Required Inputs

- **intent_card_id** (`string`)
  - Sonic Intent Card ID

- **embedding_index_id** (`string`)
  - Embedding Index ID

### Optional Inputs

- **top_k** (`integer`)
  - Number of candidates to return (final)
  - Default: `10`

- **recall_multiplier** (`integer`)
  - Recall 3x candidates for rerank
  - Default: `3`

- **diversity_factor** (`float`)
  - Diversity factor (0-1)
  - Default: `0.3`

- **query_strategy** (`enum`)
  - Query vector construction strategy
  - Default: `text`
  - Options: text, audio_reference, bookmark

- **reference_audio_id** (`string`)
  - Reference audio ID for strategy B

- **anti_reference_audio_id** (`string`)
  - Anti-reference audio ID for strategy B

- **bookmark_id** (`string`)
  - Bookmark ID for strategy C

## Outputs

**Artifacts:**

- `candidate_set`
  - Schema defined in spec file

## Steps

### Step 1: Load Intent Card

Load the sonic intent card with dimension_targets and target_scene

- **Action**: `load_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Construct Query Vector (Stage 1)

Convert intent to query vector using selected strategy

- **Action**: `intent_to_vector`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Vector Search Recall (Stage 2)

Recall 3x candidates for reranking

- **Action**: `similarity_search`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Feature Rerank (Stage 3a)

Rerank candidates by dimension_targets match score

- **Action**: `rerank_by_features`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: License Filter (Stage 3b)

Filter by target_scene → required_usage_scope mapping

- **Action**: `filter_by_license_compliance`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Generate Candidate Set

Create the final candidate set artifact

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 7: Prepare A/B Options

Present one dimension decision at a time

- **Action**: `prepare_comparison`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

- **license_compliance**
  - Rule: Only return assets with valid licenses for target_scene usage
  - Action: `filter_out`

- **high_risk_block**
  - Rule: Block high/critical risk assets from candidates
  - Action: `filter_out`

- **empty_result**
  - Rule: Handle zero results gracefully
  - Action: `suggest_relaxed_criteria`

- **response_time**
  - Rule: Search must complete in < 5 seconds
  - Action: `timeout_with_partial_results`

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **Text-Based Sound Search**
   - Search for sounds using natural language descriptions
   - Example: "Find warm, spacious ambient sounds for meditation"
   - Uses text-based query strategy

2. **Reference Audio Search**
   - Find similar sounds to a reference audio file
   - Can specify anti-reference (sounds to avoid)
   - Uses audio reference query strategy

3. **Bookmark-Based Navigation**
   - Navigate from a saved bookmark position
   - Explore nearby sounds in latent space
   - Uses bookmark-based query strategy

4. **Scene-Specific Search**
   - Filter results by usage scene (meditation, brand_audio, ui_sound, etc.)
   - Ensure license compliance for target scene
   - Return only commercially usable assets

## Examples

### Example 1: Text-Based Search

```json
{
  "intent_card_id": "intent_123",
  "embedding_index_id": "index_456",
  "query_strategy": "text",
  "top_k": 10,
  "recall_multiplier": 3,
  "diversity_factor": 0.3
}
```

**Expected Output:**
- `candidate_set` artifact with 10 ranked candidates
- All candidates have valid licenses for target scene
- A/B comparison options prepared

### Example 2: Audio Reference Search

```json
{
  "intent_card_id": "intent_123",
  "embedding_index_id": "index_456",
  "query_strategy": "audio_reference",
  "reference_audio_id": "audio_789",
  "anti_reference_audio_id": "audio_101",
  "top_k": 5
}
```

**Expected Output:**
- `candidate_set` artifact with sounds similar to reference
- Excludes sounds similar to anti-reference
- License-compliant results only

### Example 3: Bookmark Navigation

```json
{
  "intent_card_id": "intent_123",
  "embedding_index_id": "index_456",
  "query_strategy": "bookmark",
  "bookmark_id": "bookmark_456",
  "top_k": 15,
  "diversity_factor": 0.5
}
```

**Expected Output:**
- `candidate_set` artifact exploring from bookmark position
- Diverse results in latent space
- Ready for A/B comparison

## Technical Details

**Query Strategies:**
- `text`: Convert intent description to query vector using text embedding
- `audio_reference`: Use reference audio embedding as query vector
- `bookmark`: Use bookmark position as query vector

**Search Pipeline:**
1. Load intent card with dimension targets and target scene
2. Construct query vector using selected strategy
3. Vector search: Recall `top_k * recall_multiplier` candidates
4. Feature rerank: Score candidates by dimension match
5. License filter: Filter by target scene → usage scope mapping
6. Generate candidate set with top K results
7. Prepare A/B comparison options

**Performance Targets:**
- Response time: < 5 seconds (P95)
- Hit rate: > 70% (candidates match intent)
- License compliance: 100% (all results are commercially usable)

**Dual-Space Architecture:**
- **Search Space**: Vector similarity (finds semantically similar sounds)
- **Control Space**: Feature dimensions (filters by precise requirements)

**License Filtering:**
- Maps target scene to required usage scope
- Filters out assets without valid licenses
- Blocks high/critical risk assets

**Candidate Set Schema:**
The `candidate_set` artifact contains:
- List of candidate segments with scores
- Dimension match scores for each candidate
- License compliance status
- A/B comparison pairs prepared

## Related Playbooks

- **sonic_intent_card** - Create intent card before navigation
- **sonic_embedding_build** - Build embedding index for search
- **sonic_decision_trace** - Record navigation decisions
- **sonic_bookmark** - Save navigation results as bookmarks
- **sonic_segment_extract** - Extract segments for embedding

## Reference

- **Spec File**: `playbooks/specs/sonic_navigation.json`
- **API Endpoint**: `POST /api/v1/sonic-space/navigation/search`
