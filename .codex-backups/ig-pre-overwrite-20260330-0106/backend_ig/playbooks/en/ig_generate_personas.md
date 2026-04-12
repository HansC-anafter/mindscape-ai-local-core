# AI Persona Generation

## Overview

Synthesize data from account profiles, posts, and network relationships to generate AI-driven user personas using LLM.

## Features

- ✅ Aggregate data from ig_account_profiles, ig_posts, ig_follow_edges
- ✅ LLM-powered persona synthesis
- ✅ Structured persona output with traits, themes, demographics
- ✅ Brand collaboration scoring

## Inputs

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `workspace_id` | string | Yes | Workspace ID |
| `target_handles` | array | Yes | Target accounts |
| `model` | string | No | LLM model (default: gpt-4o-mini) |
| `batch_size` | integer | No | Accounts per batch (default: 10) |

## 3-Step LLM Flow

1. **collect_data** - Aggregate data from all tables
2. **generate_personas** - LLM generates structured personas
3. **persist_personas** - Write results to ig_generated_personas

## Persona Output Schema

```json
{
  "persona_summary": "2-3 sentence summary",
  "key_traits": ["trait1", "trait2"],
  "content_themes": ["theme1", "theme2"],
  "demographics": {
    "age_range": "25-34",
    "gender": "female",
    "location_type": "urban"
  },
  "collaboration_potential": 0.8,
  "recommended_approach": "Product seeding..."
}
```

## Prerequisites

- Phase 1: `ig_tag_profiles` executed
- Phase 2: `ig_analyze_content` executed (optional but recommended)

## Cost Control

- Batch processing with configurable size
- Result caching via cache_key
