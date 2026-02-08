## Export Scene Edit Manifest

Export a minimal `scene_edit_manifest.json` from Multi-Media Studio timeline (tracks + timeline items),
so downstream `video_renderer` can render an output video via ffmpeg.

### Inputs

- `project_id` (required)
- `include_all_tracks` (optional; default true)
- `output_storage_key` (optional; default `multi_media_studio/projects/{project_id}/scene_edit_manifest.json`)

