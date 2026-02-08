# Render Video

## Purpose

Render scene_edit_manifest into final video output using ffmpeg. This playbook completes the end-to-end pipeline from MMS timeline to playable video.

## When to Use

- After completing timeline editing in Multi-Media Studio
- When exporting final video from a project
- For batch rendering multiple versions (different resolutions/formats)

## Inputs

- **manifest_ref** (required): Reference to scene_edit_manifest
  - Can be storage_key, file_path, url, or inline manifest
- **output_options** (optional):
  - `format`: Output format (mp4, webm, mov) - default: mp4
  - `resolution`: Target resolution {width, height}
  - `frame_rate`: Target frame rate - default: 30
  - `quality`: Quality preset (low, medium, high, lossless) - default: medium

## Process

1. **Validate Manifest**: Check structure and asset accessibility
2. **Build FFmpeg Command**: Generate command based on clips and options
3. **Execute Render**: Run ffmpeg to produce output video
4. **Export Job Report**: Generate render job report with output references

## Outputs

- **output_ref**: Reference to rendered video file (artifact_ref format)
- **report_ref**: Reference to render job report
- **render_stats**: Render statistics (duration, file size, etc.)

## Example Usage

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

## Data Locality

- **local_only**: video_raw_files, audio_raw_files, rendered_video
- **cloud_allowed**: render_job_report, manifest_json

Local-only assets are never uploaded; rendering happens locally.

## System Requirements

- **ffmpeg**: Required for video rendering
  - Install: `brew install ffmpeg` (macOS) or `apt-get install ffmpeg` (Linux)

## Related Playbooks

- `mms_export_scene_edit_manifest`: Export manifest from MMS
- `vr_validate_only`: Validate manifest without rendering
