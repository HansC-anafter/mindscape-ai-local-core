# Analyze Pinned Reference

## Goal
Analyze a pinned IG reference image using 3-tier structured vision analysis (Scene/Object/Style) and auto-tag the result.

## Prerequisites
- At least one image pinned via the Pin-to-Assets feature
- Valid `reference_id` for the target image

## Steps

### Step 1: Preprocess
Read the pinned reference image, convert to Base64 format, and prepare the structured analysis prompt.

Tool: `ig.ig_analyze_reference` (mode: preprocess)

### Step 2: Vision Analysis
Send the preprocessed image to the multimodal vision model for 3-tier analysis:
- **Scene**: Composition, lighting, setting, mood
- **Object**: Detected objects, dominant subject
- **Style**: Color palette, typography, visual techniques, Instagram style

Tool: `core_llm.multimodal_analyze`

### Step 3: Backfill
Validate the vision analysis output (Pydantic schema validation), extract and normalize auto-tags, and write results back to the reference metadata.

Tool: `ig.ig_analyze_reference` (mode: backfill)

## Output
- Updated reference metadata with `vision_description`, `auto_tags`, `analysis_provenance`
- Analysis job status updated to `COMPLETED`
