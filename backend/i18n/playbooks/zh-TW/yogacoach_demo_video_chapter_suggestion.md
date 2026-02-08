---
playbook_code: yogacoach_demo_video_chapter_suggestion
version: 1.0.0
locale: zh-TW
name: "示範視頻章節建議"
description: "自動偵測視頻章節並提供建議（切段建議），包含置信度和原因"
capability_code: yogacoach
tags:
  - yoga
  - video
  - chapter
  - suggestion
---

# Playbook: 示範視頻章節建議

**Playbook Code**: `yogacoach_demo_video_chapter_suggestion`
**版本**: 1.0.0
**用途**: 自動偵測視頻章節並提供建議（切段建議），包含置信度和原因

---

## 輸入資料

```json
{
  "video_ref": {
    "type": "youtube",
    "url": "https://www.youtube.com/watch?v=VIDEO_ID"
  },
  "teacher_id": "teacher_001",
  "asana_id": "downward_dog",
  "existing_chapters": [
    {
      "chapter_id": "chapter_1",
      "title": "進入動作",
      "start_time": 0,
      "end_time": 10
    }
  ]
}
```

## 輸出資料

```json
{
  "job_id": "job-123",
  "status": "queued",
  "status_url": "/api/v1/playbooks/yogacoach_demo_video_chapter_suggestion_status/execute",
  "estimated_completion_seconds": 60
}
```

## 處理流程

1. 接收視頻引用和老師 ID
2. 調用 `job_dispatcher` 派發非同步任務
3. 立即返回 `job_id` 和狀態（不等待結果）
4. 結果通過 `yogacoach_demo_video_chapter_suggestion_status` playbook 查詢

## 注意事項

- **非同步設計**：此 playbook 只負責派發 job，不等待結果
- **YouTube 來源**：僅做 metadata/chapter suggestion（不進行下載/完整分析，避免法務風險）
- **Internal 來源**：完整分析（提取 keypoints、分析動作變化、識別章節切點）
- 查詢結果時使用 `yogacoach_demo_video_chapter_suggestion_status` playbook

