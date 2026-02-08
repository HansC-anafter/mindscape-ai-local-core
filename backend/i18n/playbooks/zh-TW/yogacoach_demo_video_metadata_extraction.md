---
playbook_code: yogacoach_demo_video_metadata_extraction
version: 1.0.0
locale: zh-TW
name: "示範視頻 Metadata 提取"
description: "提取視頻 metadata（時長、fps、分辨率、縮圖）"
capability_code: yogacoach
tags:
  - yoga
  - video
  - metadata
---

# Playbook: 示範視頻 Metadata 提取

**Playbook Code**: `yogacoach_demo_video_metadata_extraction`
**版本**: 1.0.0
**用途**: 提取視頻 metadata（時長、fps、分辨率、縮圖）

---

## 輸入資料

```json
{
  "video_ref": {
    "type": "youtube",
    "url": "https://www.youtube.com/watch?v=VIDEO_ID"
  }
}
```

或

```json
{
  "video_ref": {
    "type": "internal",
    "asset_id": "asset-123"
  }
}
```

## 輸出資料

```json
{
  "duration_seconds": 120.5,
  "fps": 30,
  "resolution": "1920x1080",
  "thumbnail_url": "https://img.youtube.com/vi/VIDEO_ID/maxresdefault.jpg",
  "file_size_bytes": 12345678
}
```

## 處理流程

1. 根據 `video_ref.type` 判斷視頻來源（YouTube 或 Internal）
2. 調用對應的 metadata 提取工具
3. 返回提取的 metadata

## 注意事項

- YouTube 來源：使用 YouTube Data API 獲取 metadata（需要 `YOUTUBE_DATA_API_KEY` 環境變數）
- Internal 來源：從存儲服務獲取 metadata
- 本地文件來源（local-core）：使用 `ffprobe`（FFmpeg 的一部分）從本地視頻文件提取 metadata
  - **系統要求**：系統必須安裝 `ffmpeg` 套件
  - 如果 `ffprobe` 不可用，將只返回基本的文件大小資訊
- `fps` 和 `resolution` 可能為 `null`（取決於來源是否提供）

