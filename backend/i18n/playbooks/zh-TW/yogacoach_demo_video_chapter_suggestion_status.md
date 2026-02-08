---
playbook_code: yogacoach_demo_video_chapter_suggestion_status
version: 1.0.0
locale: zh-TW
name: "示範視頻章節建議狀態查詢"
description: "查詢章節建議 job 的執行狀態和結果"
capability_code: yogacoach
tags:
  - yoga
  - video
  - chapter
  - status
---

# Playbook: 示範視頻章節建議狀態查詢

**Playbook Code**: `yogacoach_demo_video_chapter_suggestion_status`
**版本**: 1.0.0
**用途**: 查詢章節建議 job 的執行狀態和結果

---

## 輸入資料

```json
{
  "job_id": "job-123"
}
```

## 輸出資料

### 狀態: queued/running

```json
{
  "job_id": "job-123",
  "status": "running",
  "progress": {
    "current_step": "chapter_suggestion",
    "progress_percentage": 50
  }
}
```

### 狀態: completed

```json
{
  "job_id": "job-123",
  "status": "completed",
  "result": {
    "suggested_chapters": [
      {
        "chapter_id": "suggested_chapter_1",
        "title": "進入動作",
        "start_time": 0,
        "end_time": 20.5,
        "confidence": 0.85,
        "reasons": ["動作變化大", "停留時間長"],
        "detection_method": "motion_change"
      }
    ],
    "detection_metadata": {
      "total_segments_detected": 3,
      "average_confidence": 0.82,
      "detection_method": "motion_segmentation"
    }
  }
}
```

### 狀態: failed

```json
{
  "job_id": "job-123",
  "status": "failed",
  "error": "Failed to extract keypoints from video"
}
```

## 處理流程

1. 接收 `job_id`
2. 調用 `job_dispatcher` 查詢模式（只傳 `job_id`）
3. 返回 job 狀態和結果（如果完成）

## 注意事項

- 使用 `job_dispatcher` 的查詢模式（只傳 `job_id`，無 `job_type`）
- 工具內部根據是否有 `job_id` 自動判斷模式
- 前端應輪詢此 playbook 直到狀態為 `completed` 或 `failed`

