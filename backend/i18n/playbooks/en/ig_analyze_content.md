# Content Analysis

## Overview

Extract and analyze Instagram posts from accounts, classify content topics using LLM, and persist results to `ig_posts` table.

## Features

- ✅ Extract recent posts from target accounts
- ✅ Capture captions, hashtags, mentions, engagement
- ✅ LLM-powered topic classification
- ✅ PostgreSQL persistence with upsert

## Inputs

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `workspace_id` | string | Yes | Workspace ID |
| `seed` | string | Yes | Seed account being analyzed |
| `target_handles` | array | No | Target accounts (auto from ig_accounts_flat if empty) |
| `posts_per_account` | integer | No | Posts per account (default: 9) |
| `user_data_dir` | string | No | Browser profile path |

## 3-Step LLM Flow

1. **extract_posts** - Crawl posts, return captions
2. **classify_topics** - LLM classifies each caption into topic
3. **persist_with_topics** - Write posts + topics to database

## Topic Categories

lifestyle, fashion, beauty, food, travel, fitness, tech, business, education, entertainment, other

## Usage Example

```json
{
  "workspace_id": "ws_abc123",
  "seed": "university.tw",
  "posts_per_account": 9
}
```

## Notes

1. **Prerequisites**: Requires `ig_analyze_following` to populate `ig_accounts_flat`
2. **Browser**: Uses Playwright with persistent profile
3. **Rate Limiting**: Built-in delays between requests

## Related Tools

- `ig.ig_content_analyzer`: Core extraction tool
- `core_llm.structured_extract`: Topic classification
