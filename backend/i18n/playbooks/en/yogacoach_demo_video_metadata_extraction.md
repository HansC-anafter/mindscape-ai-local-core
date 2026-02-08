---
playbook_code: yogacoach_demo_video_metadata_extraction
version: 1.0.0
locale: en
name: "Demo Video Metadata Extraction"
description: "Extract video metadata (duration, fps, resolution, thumbnail)"
capability_code: yogacoach
tags:
  - yoga
  - video
  - metadata
---

# Playbook: Demo Video Metadata Extraction

**Playbook Code**: `yogacoach_demo_video_metadata_extraction`
**Version**: 1.0.0
**Purpose**: Extract video metadata (duration, fps, resolution, thumbnail)

---

## Input Data

```json
{
  "video_ref": {
    "type": "youtube",
    "url": "https://www.youtube.com/watch?v=VIDEO_ID"
  }
}
```

or

```json
{
  "video_ref": {
    "type": "internal",
    "asset_id": "asset-123"
  }
}
```

## Output Data

```json
{
  "duration_seconds": 120.5,
  "fps": 30,
  "resolution": "1920x1080",
  "thumbnail_url": "https://img.youtube.com/vi/VIDEO_ID/maxresdefault.jpg",
  "file_size_bytes": 12345678
}
```

## Process Flow

1. Determine video source (YouTube or Internal) based on `video_ref.type`
2. Call corresponding metadata extraction tool
3. Return extracted metadata

## Notes

- YouTube source: Uses YouTube Data API to fetch metadata (requires `YOUTUBE_DATA_API_KEY` environment variable)
- Internal source: Retrieves metadata from storage service
- Local file source (local-core): Uses `ffprobe` (from FFmpeg) to extract metadata from local video files
  - **System Requirement**: `ffmpeg` package must be installed on the system
  - If `ffprobe` is not available, only basic file size information will be returned
- `fps` and `resolution` may be `null` (depends on whether source provides them)

