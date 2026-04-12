# Pin Post Detail

## Goal
Navigate to single or multiple IG posts and pin all images (including carousel slides) with full metadata (caption, likes, comments, timestamp).

## Prerequisites
- Playwright browser automation available
- Valid shortcode(s) for target post(s)

## Steps

### Step 1: Fetch Post Detail
Navigate to the post page using browser automation. Extract caption, engagement stats, and all carousel images.

Tool: `ig.ig_fetch_post_detail`

### Step 2: Pin All Images
Pin each extracted image as a reference. Carousel slides are linked via `carousel_parent_id`. Post metadata (caption, likes, comments) is attached to all references.

Tool: `ig.ig_pin_post_detail`

## Output
- One reference per image (carousel posts produce multiple linked references)
- Each reference has: `post_caption`, `post_like_count`, `post_comment_count`, `post_timestamp`
- Carousel references linked via `carousel_parent_id` and `carousel_index`
- Background vision analysis automatically enqueued for each new reference
