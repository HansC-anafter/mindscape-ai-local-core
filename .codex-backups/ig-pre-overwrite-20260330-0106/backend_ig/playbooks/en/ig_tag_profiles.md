# Profile Tagging

## Overview

Compute classification tags for captured IG accounts from the `ig_accounts_flat` table and persist to `ig_account_profiles`. This tool analyzes account metadata to determine account type, influence tier, and extract bio keywords.

## Features

- ✅ Classify account type (KOL, Brand, Personal, Media, Unknown)
- ✅ Determine influence tier (Nano, Micro, Mid, Macro, Mega)
- ✅ Extract bio keywords using NLP
- ✅ Detect bio language
- ✅ Compute engagement metrics
- ✅ Upsert to PostgreSQL with conflict handling

## Inputs

### Required Parameters

- `workspace_id` (string): Mindscape workspace ID
- `seed` (string): Target seed account (the account whose following list was analyzed)

### Optional Parameters

- `force_recompute` (boolean): Force recompute existing tags (default: false)

## Outputs

- `processed`: Total profiles processed
- `created`: New profiles created
- `updated`: Existing profiles updated
- `skipped`: Profiles skipped (already exist, no force_recompute)

## Account Type Classification

| Type | Indicators |
|------|------------|
| **KOL** | Creator, influencer, blogger, collab, business inquiries |
| **Brand** | Official, ®, ™, shop, store, company |
| **Media** | News, magazine, journalist, podcast |
| **Personal** | Default for normal accounts |
| **Unknown** | Insufficient data |

## Influence Tier Thresholds

| Tier | Follower Range |
|------|----------------|
| Mega | 1M+ |
| Macro | 100K-1M |
| Mid | 10K-100K |
| Micro | 1K-10K |
| Nano | <1K |

## Usage Example

```json
{
  "workspace_id": "ws_abc123",
  "seed": "university.tw",
  "force_recompute": false
}
```

## Notes

1. **Prerequisites**: Requires `ig_analyze_following` to have been run first to populate `ig_accounts_flat`
2. **NLP Libraries**: Uses `jieba` for Chinese text and `langdetect` for language detection (optional)
3. **Database**: Writes to `ig_account_profiles` table in PostgreSQL

## Related Tools

- `ig.ig_analyze_following`: Extract following list (prerequisite)
- `ig.ig_profile_tagger`: Core tagging tool
