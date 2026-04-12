# Network Analysis

## Overview

Analyze follow relationships across multiple seed accounts to find common following patterns and community clusters.

## Features

- ✅ Find accounts followed by multiple seeds
- ✅ Community detection using Louvain algorithm
- ✅ Cross-seed relationship analysis

## Inputs

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `workspace_id` | string | Yes | Workspace ID |
| `seeds` | array | Yes | Seed accounts (minimum 2) |
| `analysis_type` | string | No | "common_following" or "community" |
| `min_overlap` | integer | No | Minimum seeds following (default: 2) |
| `resolution` | number | No | Louvain resolution (default: 1.0) |

## Analysis Types

### common_following
Find accounts that are followed by multiple seeds. Useful for identifying:
- Shared interests
- Industry influencers
- Potential collaboration targets

### community
Detect communities using Louvain clustering algorithm. Useful for:
- Understanding follower network structure
- Identifying distinct audience segments
- Finding cluster patterns

## Usage Example

```json
{
  "workspace_id": "ws_abc123",
  "seeds": ["account_a", "account_b", "account_c"],
  "analysis_type": "common_following",
  "min_overlap": 2
}
```

## Prerequisites

- `ig_analyze_following` executed for all seeds
- Data in `ig_follow_edges` table

## Dependencies

- `networkx>=3.0`
- `python-louvain>=0.16`
