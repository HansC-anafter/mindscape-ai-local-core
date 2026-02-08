# Create Chapter Studio Project

Create a new video chapter project from a video source.

## Objective

Initialize a new project in Video Chapter Studio by ingesting a video from various sources (local file, URL, or YouTube) and preparing it for chapter segmentation.

## Input Requirements

- **video_source**: Source type (`file`, `url`, `youtube`)
- **video_ref**: Reference to the video (file path, URL, or YouTube ID)
- **project_name** (optional): Name for the project
- **metadata** (optional): Additional project metadata including domain extension

## Process Flow

1. **Validate Input**: Verify video source and reference are valid
2. **Ingest Video**: Download/copy video and extract metadata
3. **Create Project Record**: Store project in database
4. **Return Result**: Return created project information

## Output

- **project_id**: Unique identifier for the created project
- **video_metadata**: Extracted video information (duration, resolution, fps)
- **status**: Project creation status

## Notes

- For YouTube videos, the video will be downloaded if permitted
- Video metadata extraction requires `ffprobe` system tool
- Large videos may take longer to ingest


