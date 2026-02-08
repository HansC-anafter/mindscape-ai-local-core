# Process Chapters

Generate assets for all chapters in a video project.

## Objective

Process chapters in a Video Chapter Studio project to generate thumbnails, analyze quality, and run domain-specific extension analysis.

## Input Requirements

- **project_id**: Project ID to process
- **chapter_ids** (optional): Specific chapter IDs (defaults to all)
- **options** (optional): Processing options
  - `extract_thumbnails`: Generate thumbnails (default: true)
  - `analyze_quality`: Run quality analysis (default: true)
  - `run_extensions`: Run domain extension analysis (default: true)

## Process Flow

1. **Load Project**: Retrieve project and chapter data
2. **Extract Thumbnails**: Generate start/middle/end thumbnails for each chapter
3. **Analyze Quality**: Check video quality metrics (resolution, lighting, motion)
4. **Run Extensions**: Execute domain-specific analysis (e.g., pose estimation)
5. **Aggregate Results**: Compile processing results

## Output

- **processed_chapters**: Array of processed chapter results
- **overall_status**: Processing completion status

## Notes

- Processing is performed per-chapter and can be parallelized
- Extension analysis depends on installed domain extensions
- Quality analysis requires `ffprobe` for full metrics


