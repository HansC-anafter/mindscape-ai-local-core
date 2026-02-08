---
playbook_code: yogacoach_result_packager
version: 1.0.0
locale: zh-TW
name: "結果包裝"
description: "從 Session Report 提取核心數據，生成主卡、播放清單和分享連結"
capability_code: yogacoach
tags:
  - yoga
  - result
  - packaging
---

# Playbook: 結果包裝

**Playbook Code**: `yogacoach_result_packager`
**版本**: 1.0.0
**用途**: 從 Session Report 提取核心數據，生成主卡、播放清單和分享連結

---

## 輸入資料

**注意**：`tenant_id`、`session_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "session_report": {
    "segments": [],
    "metrics": [],
    "safety_labels": [],
    "events": [],
    "narration": {}
  },
  "delivery_channel": "web",
  "share_config": {
    "enable_share": true,
    "ttl_hours": 72
  }
}
```

## 輸出資料

```json
{
  "delivery_bundle": {
    "main_card": {
      "session_id": "session-abc123",
      "summary": {
        "total_asanas": 3,
        "total_duration_minutes": 15,
        "overall_safety_label": "yellow",
        "key_metrics": {
          "alignment_score": 78,
          "stability_score": 85,
          "symmetry_score": 72
        },
        "top_suggestion": "注意右膝過度伸展，建議微屈以保護膝蓋"
      }
    },
    "playlists": [
      {
        "asana_id": "downward_dog",
        "chapters": [
          {
            "title": "正確示範 - 進入階段",
            "youtube_url": "https://youtu.be/xxx?t=5",
            "duration": 10
          }
        ]
      }
    ],
    "detailed_report_url": "/sessions/session-abc123/detailed",
    "expandable_sections": []
  },
  "render_hints": {
    "channel": "web",
    "layout": "card",
    "theme": "light"
  },
  "share_link": {
    "url": "https://yogacoach.app/s/abc12345",
    "short_code": "abc12345",
    "ttl_hours": 72,
    "expires_at": "2025-12-28T10:00:00Z"
  }
}
```

## 執行步驟

1. **提取核心數據**
   - 從 `session_report` 提取 segments、metrics、safety_labels、events
   - 計算關鍵指標（alignment_score, stability_score, symmetry_score）

2. **生成主卡**
   - 生成 3 指標 + 1 建議 + 安全標籤
   - 計算整體安全標籤（green/yellow/red）

3. **生成播放清單**
   - 為每個 asana 生成 teacher demo timecodes
   - 生成 YouTube 連結和時間戳

4. **生成自選深度入口**
   - 生成可展開的詳細指標區塊
   - 生成事件檢測區塊

5. **生成分享連結**
   - 生成帶 TTL 的分享連結
   - 設置訪問範圍（默認僅本人可看）

6. **生成渲染提示**
   - 根據 delivery_channel 生成對應的布局提示
   - Web: card 布局
   - LINE: flex_message 布局

## 能力依賴

- `yogacoach.result_packager`: 結果包裝
- `yogacoach.share_link_generator`: 分享連結生成

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 錯誤處理

- Session Report 格式錯誤：返回錯誤，記錄日誌
- 分享連結生成失敗：返回錯誤，記錄日誌

