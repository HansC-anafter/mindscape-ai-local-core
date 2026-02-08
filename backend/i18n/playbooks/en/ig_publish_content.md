# IG Content Publish

## Overview

Publish content to Instagram (supports photo, reel, carousel).

## ⚠️ Prerequisites

**You must complete the following steps in site-hub first**:

1. **OAuth Authorization**: Complete Instagram OAuth authorization in site-hub UI
2. **Channel Binding**: Bind Instagram Business Account to ChannelConfig
3. **Get channel_config_id**: Obtain the corresponding `channel_config_id` from site-hub

**Important**:
- Token and authorization are managed by site-hub
- This playbook only publishes content, does not perform OAuth authorization
- If channel_config_id is invalid or token expired, an error will be returned

## Features

- ✅ Support publishing photo (supports scheduled publishing, up to 6 months later)
- ✅ Support publishing reel (does not support scheduled publishing, must publish immediately)
- ✅ Support publishing carousel (multiple images)
- ❌ **Does not support publishing Stories** (Graph API limitation, can only sync)

## Media Limitations

### Photo

- **Format**: JPEG, PNG
- **Max Size**: 8192x8192 pixels
- **File Size**: Max 30MB
- **Scheduled Publishing**: Supports `scheduled_publish_time` (up to 6 months later)

### Reel

- **Format**: MP4, MOV
- **Video Length**: 3 seconds - 90 seconds
- **Video Size**: Min 500x500 pixels, Max 1920x1920 pixels
- **File Size**: Max 100MB
- **Scheduled Publishing**: ❌ Not supported (must publish immediately)

### Carousel

- **Format**: Supports multiple images, each with same limits as Photo
- **Scheduled Publishing**: Supports `scheduled_publish_time` (up to 6 months later)

## Input Parameters

### Required Parameters

- `channel_config_id` (integer): Channel Config ID (managed by site-hub)
- `workspace_id` (string): Mindscape workspace ID
- `media_type` (string): Media type
  - `photo`: Publish photo
  - `reel`: Publish reel
  - `carousel`: Publish carousel
  - ⚠️ **Does not support `story`** (Graph API limitation)
- `media_path` (string): Media file path (relative or absolute path in workspace)
- `caption` (string): Post title/description

### Optional Parameters

- `hashtags` (array): List of hashtags (will be automatically added to caption)
- `scheduled_publish_time` (string): Scheduled publish time (ISO 8601 format, only for photo, up to 6 months later)
- `location_id` (string): Location ID
- `user_tags` (array): List of user tags
- `cover_url` (string): Reel cover URL (for reel only)
- `share_to_feed` (boolean): Whether to share to Feed (for reel only, default: true)

## Output

- `published_post`: Published post information (photo)
- `published_reel`: Published reel information
- `published_carousel`: Published carousel information
- `media_id`: Published media ID
- `permalink`: Permanent link to published content
- `validation_result`: Media validation result

## Usage Examples

### Publish Photo

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "media_type": "photo",
  "media_path": "posts/photo_001.jpg",
  "caption": "This is a beautiful photo",
  "hashtags": ["photography", "nature", "beautiful"]
}
```

### Publish Photo (Scheduled)

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "media_type": "photo",
  "media_path": "posts/photo_002.jpg",
  "caption": "This photo will be published tomorrow",
  "scheduled_publish_time": "2024-12-31T12:00:00Z"
}
```

### Publish Reel

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "media_type": "reel",
  "media_path": "reels/reel_001.mp4",
  "caption": "This is an amazing reel",
  "hashtags": ["reel", "video", "fun"],
  "share_to_feed": true
}
```

### Publish Carousel

```json
{
  "channel_config_id": 123,
  "workspace_id": "ws_abc123",
  "media_type": "carousel",
  "media_path": "carousels/carousel_001/",
  "caption": "This is a carousel post",
  "hashtags": ["carousel", "multiple", "images"]
}
```

## Notes

1. **Stories Not Supported**: Graph API does not support publishing Stories, can only sync
2. **Reel Must Publish Immediately**: Does not support scheduled publishing
3. **Media Validation**: Media format and size limits are automatically validated before publishing
4. **API Quota**: Be aware of Instagram Graph API quota limits (10 requests/second per app)
5. **Token Management**: If token expires, you need to re-authorize in site-hub
6. **Permission Requirements**: Requires `instagram_content_publish` permission

## Related Documentation

- [IG Channel Implementation Plan](../../openseo/docs/IG_CHANNEL_IMPLEMENTATION_PLAN_2026-01-05.md)
- [Site-Hub Channel Binding API](../../../site-hub/site-hub-api/v1/channel_binding.py)

