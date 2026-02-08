---
playbook_code: sonic_bookmark
version: 1.0.0
locale: en
name: "Vector Bookmark & Reuse"
description: "Create reusable sonic coordinate bookmarks"
kind: user_workflow
capability_code: sonic_space
---

# Vector Bookmark & Reuse

Create reusable sonic coordinate bookmarks

## Overview

The Vector Bookmark & Reuse playbook creates reusable sonic coordinate bookmarks that allow users to save and revisit specific positions in the latent space. Bookmarks serve as reference points for navigation, interpolation, and sound generation.

**Key Features:**
- Create bookmarks from reference audio or embeddings
- Store bookmark coordinates in latent space
- Reuse bookmarks for navigation and prospecting
- Link bookmarks to representative segments

**Purpose:**
This playbook enables users to save interesting sound positions for later use. Bookmarks are essential for `sonic_prospecting_lite` (interpolation/extrapolation) and `sonic_navigation` (bookmark-based search).

**Related Playbooks:**
- `sonic_navigation` - Use bookmarks for navigation
- `sonic_prospecting_lite` - Use bookmarks for interpolation/extrapolation
- `sonic_decision_trace` - Track bookmark creation decisions

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_bookmark.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Load Reference

Load reference audio or embedding

- **Action**: `load_reference`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 2: Create Bookmark

Create reusable sonic coordinate bookmark

- **Action**: `create_bookmark`
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

1. **Save Interesting Sounds**
   - Save sounds discovered during navigation
   - Create reference points for future exploration
   - Build a personal sound library

2. **Interpolation Points**
   - Create bookmarks for interpolation between sounds
   - Define start and end points for sound generation
   - Explore intermediate positions

3. **Extrapolation Base**
   - Create bookmarks as starting points for extrapolation
   - Explore dimension extremes from known positions
   - Generate variations along axes

## Examples

### Example 1: Create Bookmark from Audio

```json
{
  "reference_audio_id": "audio_123",
  "bookmark_name": "Warm Ambient Reference"
}
```

**Expected Output:**
- `sonic_bookmark` artifact with:
  - Bookmark ID and name
  - Embedding coordinates in latent space
  - Link to reference audio segment

## Technical Details

**Bookmark Creation:**
- Extracts embedding from reference audio
- Stores coordinates in latent space
- Links to representative segment
- Creates reusable reference point

**Bookmark Usage:**
- Used in `sonic_navigation` for bookmark-based search
- Used in `sonic_prospecting_lite` for interpolation/extrapolation
- Enables exploration from saved positions

**Tool Dependencies:**
- `sonic_vector_search` - Load reference and extract coordinates

## Related Playbooks

- **sonic_navigation** - Use bookmarks for navigation
- **sonic_prospecting_lite** - Use bookmarks for interpolation/extrapolation
- **sonic_decision_trace** - Track bookmark creation decisions

## Reference

- **Spec File**: `playbooks/specs/sonic_bookmark.json`
