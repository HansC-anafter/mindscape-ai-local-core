## 匯出 Scene Edit Manifest

從 Multi-Media Studio 的 timeline（tracks + timeline items）匯出一份最小可用的 `scene_edit_manifest.json`，
提供給下游 `video_renderer` 做 ffmpeg 渲染。

### 輸入

- `project_id`（必填）
- `include_all_tracks`（選填；預設 true）
- `output_storage_key`（選填；預設 `multi_media_studio/projects/{project_id}/scene_edit_manifest.json`）

