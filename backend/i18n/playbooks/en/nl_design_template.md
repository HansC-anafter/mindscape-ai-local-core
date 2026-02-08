# Design Template

## Purpose

Design or preview email templates with variable substitution.

## When to Use

- Previewing template with sample data
- Testing template rendering
- Selecting template for campaign

## Inputs

- **template_id** (required): Template to render
- **variables** (optional): Variables to substitute
- **preview_mode** (optional): Use sample data

## Available Templates

- `default_digest`: Weekly digest with sections
- `default_announcement`: Single topic announcement
- `default_promotion`: Promotional with CTA
- `default_update`: Product/service update

## Example Usage

```yaml
inputs:
  template_id: "default_digest"
  preview_mode: true
  variables:
    brand_name: "My Company"
    headline: "Weekly Update"
```

## Related Playbooks

- `nl_create_campaign`: Use template in campaign
- `nl_generate_content`: Generate content for template
