---
playbook_code: sonic_latent_map
version: 1.0.0
locale: en
name: "Sonic Clustering & Map Generation"
description: "Generate Latent Map / Mood Map"
kind: user_workflow
capability_code: sonic_space
---

# Sonic Clustering & Map Generation

Generate Latent Map / Mood Map

## Overview

The Sonic Clustering & Map Generation playbook generates latent maps and mood maps by clustering audio embeddings. It creates visual representations of the sonic latent space for exploration and navigation.

**Key Features:**
- Cluster audio embeddings
- Generate latent space maps
- Create mood maps
- Visualize sonic space structure

**Purpose:**
This playbook enables users to visualize and understand the structure of the sonic latent space through clustering and map generation. Maps help users navigate and explore the sonic space more effectively.

**Related Playbooks:**
- `sonic_embedding_build` - Build embeddings for mapping
- `sonic_navigation` - Use maps for navigation
- `sonic_latent_prospecting` - Explore mapped regions

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_latent_map.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Load Embeddings

Load audio embeddings

- **Action**: `load_embeddings`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 2: Cluster Embeddings

Cluster embeddings for latent map

- **Action**: `cluster_embeddings`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Generate Map

Generate Latent Map / Mood Map

- **Action**: `generate_map`
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

1. **Latent Space Visualization**
   - Generate maps of latent space structure
   - Visualize sound distribution
   - Understand sonic space organization

2. **Mood Map Creation**
   - Create mood-based sound maps
   - Organize sounds by emotional characteristics
   - Support mood-based navigation

3. **Exploration Aid**
   - Use maps to guide exploration
   - Identify interesting regions
   - Plan navigation paths

## Examples

### Example 1: Generate Latent Map

```json
{
  "embedding_index_id": "index_123",
  "map_type": "latent",
  "clustering_method": "kmeans"
}
```

**Expected Output:**
- Latent space map with clusters
- Visual representation of sonic space
- Cluster assignments for all sounds

## Technical Details

**Map Generation:**
- Loads embeddings from index
- Clusters embeddings using selected method
- Generates map visualization
- Creates cluster assignments

**Map Types:**
- `latent`: Latent space structure map
- `mood`: Mood-based organization map

**Tool Dependencies:**
- `sonic_vector_search` - Load embeddings
- Clustering algorithms

## Related Playbooks

- **sonic_embedding_build** - Build embeddings for mapping
- **sonic_navigation** - Use maps for navigation
- **sonic_latent_prospecting** - Explore mapped regions

## Reference

- **Spec File**: `playbooks/specs/sonic_latent_map.json`
