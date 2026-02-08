# 渲染影片

## 目的

使用 ffmpeg 將 scene_edit_manifest 渲染為最終影片輸出。此 playbook 完成從 MMS 時間線到可播放影片的端到端流程。

## 使用時機

- 在 Multi-Media Studio 完成時間線編輯後
- 從專案匯出最終影片時
- 批量渲染多個版本（不同解析度/格式）

## 輸入

- **manifest_ref**（必填）：scene_edit_manifest 的引用
  - 可以是 storage_key、file_path、url 或內嵌 manifest
- **output_options**（選填）：
  - `format`：輸出格式（mp4、webm、mov）- 預設：mp4
  - `resolution`：目標解析度 {width, height}
  - `frame_rate`：目標幀率 - 預設：30
  - `quality`：品質預設（low、medium、high、lossless）- 預設：medium

## 流程

1. **驗證 Manifest**：檢查結構和素材可存取性
2. **建構 FFmpeg 指令**：根據片段和選項生成指令
3. **執行渲染**：執行 ffmpeg 產生輸出影片
4. **匯出工作報告**：生成包含輸出引用的渲染工作報告

## 輸出

- **output_ref**：渲染影片檔案的引用（artifact_ref 格式）
- **report_ref**：渲染工作報告的引用
- **render_stats**：渲染統計（時長、檔案大小等）

## 使用範例

```yaml
inputs:
  manifest_ref:
    storage_key: "multi_media_studio/projects/proj_123/scene_edit_manifest.json"
  output_options:
    format: mp4
    resolution:
      width: 1920
      height: 1080
    frame_rate: 30
    quality: high
```

## 資料邊界

- **local_only**：video_raw_files、audio_raw_files、rendered_video
- **cloud_allowed**：render_job_report、manifest_json

本地專屬素材永不上傳；渲染在本地執行。

## 系統需求

- **ffmpeg**：影片渲染必須
  - 安裝：`brew install ffmpeg`（macOS）或 `apt-get install ffmpeg`（Linux）

## 相關 Playbook

- `mms_export_scene_edit_manifest`：從 MMS 匯出 manifest
- `vr_validate_only`：僅驗證 manifest 不渲染
