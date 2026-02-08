# Send Campaign

## Purpose

Send a newsletter campaign to subscribers via configured ESP (Email Service Provider).

## When to Use

- Ready to send a campaign
- Testing campaign before full send
- Triggered by content_scheduler

## Inputs

- **campaign_id** (required): Campaign to send
- **subscriber_list_id** (optional): Target subscriber list
- **test_mode** (optional): Send only to test emails
- **test_emails** (optional): Test email addresses

## Outputs

- **sent_count**: Number of emails sent
- **failed_count**: Number of failed sends
- **status**: Campaign status after send

## ESP Integration

Supported providers (set via `NEWSLETTER_ESP_PROVIDER`):
- `simulation`: Local testing (no actual sends)
- `resend`: Resend.com API
- `sendgrid`: SendGrid API

## Example Usage

```yaml
# Test send
inputs:
  campaign_id: "abc123"
  test_mode: true
  test_emails:
    - "test@example.com"

# Production send
inputs:
  campaign_id: "abc123"
  subscriber_list_id: "main_list"
```

## Related Playbooks

- `nl_create_campaign`: Create campaign
- `nl_analyze_metrics`: Analyze results
