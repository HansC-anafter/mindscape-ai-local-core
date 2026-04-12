# IG Content Sync

## Overview

Sync posts/reels/stories content from Instagram to local workspace.

## ⚠️ Prerequisites

**You must complete the following steps in site-hub first**:

1. **OAuth Authorization**: Complete Instagram OAuth authorization in site-hub UI
2. **Channel Binding**: Bind Instagram Business Account to ChannelConfig
3. **Get channel_config_id**: Obtain the corresponding `channel_config_id` from site-hub

**Important**:
- Token and authorization are managed by site-hub
- This playbook only syncs content, does not perform OAuth authorization
- If channel_config_id is invalid or token expired, an error will be returned

## Features

- ✅ Support syncing posts, reels, stories
- ✅ Automatically download media files to workspace storage
- ✅ Generate and save metadata
- ✅ Optional: Trigger openseo pipeline to process content

## Input Parameters

### Required Parameters

- `channel_config_id` (integer): Channel Config ID (managed by site-hub)
- `workspace_id` (string): Mindscape workspace ID

### Optional Parameters

- `content_type` (string): Content type to sync
  - `posts`: Sync posts only
  - `reels`: Sync reels only
  - `stories`: Sync stories only (within 24 hours)
  - `all`: Sync all types (default)

- `media_type` (string): Media type filter (for posts only)
  - `IMAGE`: Sync images only
  - `VIDEO`: Sync videos only
  - `CAROUSEL_ALBUM`: Sync carousels only

- `limit` (integer): Limit for each sync (default: 25)

- `since` (string): Start time (ISO 8601 format)

- `until` (string): End time (ISO 8601 format)

- `trigger_openseo` (boolean): Whether to trigger openseo pipeline to process synced content (default: false)

## Output

- `posts`: List of synced posts
- `reels`: List of synced reels
- `stories`: List of synced stories
- `media_files`: List of downloaded media file paths
- `metadata`: Content metadata
- `seo_results`: SEO processing results (if trigger_openseo is enabled)

## Usage Examples

### Sync All Content

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "content_type": "all",
  "limit": 25
}
```

### Sync Posts Only

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "content_type": "posts",
  "media_type": "IMAGE",
  "limit": 50
}
```

### Sync and Trigger SEO Processing

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "content_type": "posts",
  "trigger_openseo": true
}
```

## Notes

1. **Stories Time Limit**: Stories are only available within 24 hours
2. **API Quota**: Be aware of Instagram Graph API quota limits (10 requests/second per app)
3. **Token Management**: If token expires, you need to re-authorize in site-hub
4. **Permission Requirements**: Requires `instagram_basic`, `instagram_manage_insights`, `pages_read_user_content` permissions

## Related Documentation

- [IG Channel Implementation Plan](../../openseo/docs/IG_CHANNEL_IMPLEMENTATION_PLAN_2026-01-05.md)
- [Site-Hub Channel Binding API](../../../site-hub/site-hub-api/v1/channel_binding.py)

