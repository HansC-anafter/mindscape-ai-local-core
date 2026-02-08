# Generate Content

## Purpose

Generate newsletter content using AI based on topic and style preferences.

## When to Use

- Creating content for new campaigns
- Generating digest from source content
- Drafting announcements or updates

## Inputs

- **topic** (required): Topic or theme for content
- **content_type** (optional): Type of content (digest, announcement, promotion, update)
- **tone** (optional): Writing tone (formal, casual, friendly, professional)
- **source_content_refs** (optional): References to source content from other packs

## Outputs

- **content**: Generated content structure with headline, intro, body, CTA

## Example Usage

```yaml
inputs:
  topic: "AI Product Updates"
  content_type: "digest"
  tone: "professional"
  source_content_refs:
    - pack: "content"
      asset_id: "blog_post_123"
```

## Related Playbooks

- `nl_create_campaign`: Use generated content
- `nl_design_template`: Preview with template
