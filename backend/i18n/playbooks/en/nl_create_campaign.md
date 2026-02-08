# Create Campaign

## Purpose

Create a new newsletter campaign with subject, content, and optional scheduling.

## When to Use

- Starting a new email campaign
- Setting up automated newsletters
- Creating scheduled announcements

## Inputs

- **name** (required): Campaign name for internal tracking
- **subject** (required): Email subject line
- **preview_text** (optional): Preview text shown in inbox
- **template_id** (optional): Template to use
- **content** (optional): Campaign content (headline, body, CTA)
- **schedule_time** (optional): Scheduled send time (ISO format)

## Outputs

- **campaign_id**: Unique identifier for the campaign
- **campaign**: Full campaign data

## Example Usage

```yaml
inputs:
  name: "January Weekly Digest"
  subject: "Your Weekly Update - Jan 21, 2026"
  preview_text: "This week's highlights and news"
  template_id: "default_digest"
  content:
    headline: "Welcome to This Week's Digest"
    intro: "Here's what you need to know..."
    cta_text: "Read More"
    cta_url: "https://example.com/blog"
```

## Related Playbooks

- `nl_design_template`: Design email template
- `nl_generate_content`: Generate content with AI
- `nl_send_campaign`: Send the campaign
