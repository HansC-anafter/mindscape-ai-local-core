# Content Gap Analysis

## Purpose

Identify content gaps by comparing your content features against following/competitor content. This playbook helps discover topics, formats, and visual styles that competitors use but you haven't explored yet.

## When to Use

- After syncing competitor/following content via ig.sync_content
- During content calendar planning
- When looking for new content ideas
- Before launching a new content series

## Inputs

- **own_content_ref** (required): Reference to your content analysis data
  - Can include topics, formats, visual_tokens, tags
- **following_content_ref** (required): Reference to competitor/following content analysis
- **dimensions** (optional): Dimensions to analyze
  - `topic`: Compare content topics/themes
  - `format`: Compare content formats (carousel, reel, story, etc.)
  - `visual_style`: Compare visual elements and styles
  - `timing`: Compare posting patterns (not yet implemented)
  - `engagement_pattern`: Compare engagement metrics (not yet implemented)

## Process

1. **Load Content Data**: Retrieve analysis data from both references
2. **Detect Gaps**: Compare across selected dimensions
3. **Generate Insights**: Create actionable recommendations with suggested playbooks

## Outputs

- **gaps**: Content areas where competitors are active but you are not
- **opportunities**: Trending elements worth exploring
- **strengths**: Your distinctive content elements
- **insights**: Actionable insights for content generation

## Example Usage

```yaml
inputs:
  own_content_ref:
    topics: ["ai", "productivity", "tools"]
    formats: ["carousel", "image"]
    visual_tokens: ["minimalist", "gradient"]
  following_content_ref:
    topics: ["ai", "productivity", "automation", "workflow", "tutorials"]
    formats: ["carousel", "reel", "story"]
    visual_tokens: ["minimalist", "gradient", "3d", "neon"]
  dimensions:
    - topic
    - format
    - visual_style
```

## Related Playbooks

- `ig_generate_post`: Use gap insights to create new content
- `content_drafting`: Generate content for identified topic gaps
- `ana_competitor_style`: Deep dive into visual style differences
