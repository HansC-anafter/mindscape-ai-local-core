---
playbook_code: yogacoach_channel_delivery
version: 1.0.0
locale: en
name: "Multi-Channel Result Delivery"
description: "Push analysis results to Web/LINE channels, support Flex Message and fallback strategy"
capability_code: yogacoach
tags:
  - yoga
  - channel
  - delivery
---

# Playbook: Multi-Channel Result Delivery

**Playbook Code**: `yogacoach_channel_delivery`
**Version**: 1.0.0
**Purpose**: Push analysis results to Web/LINE channels, support Flex Message and fallback strategy

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `user_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "channel": "line",
  "delivery_bundle": {
    "main_card": {},
    "playlists": [],
    "share_link": {}
  },
  "channel_config": {
    "line": {
      "user_line_id": "U1234567890abcdef",
      "push_enabled": true
    },
    "web": {
      "email": "user@example.com",
      "notification_enabled": true
    }
  }
}
```

## Output Data

```json
{
  "delivered": true,
  "channel": "line",
  "channel_receipt": {
    "receipt_id": "receipt-abc123",
    "delivered_at": "2025-12-25T10:30:00Z",
    "delivery_method": "line_flex",
    "status": "success"
  },
  "fallback_used": false,
  "result_url": "https://yogacoach.app/s/abc12345"
}
```

## Execution Steps

1. **Validate Channel Bind"
   - Check channel bind status
   - Check unsubscribe status
   - If not bound or unsubscribed, return error

2. **Generate Push Content"
   - Web: Generate result page URL
   - LINE: Generate Flex Message card

3. **Push Result"
   - Web: Send Email (optional) or generate notification
   - LINE: Push Flex Message via Push API

4. **Fallback Handling"
   - If Flex Message push fails, fallback to simple text + link
   - Record fallback reason

5. **Track Push Status"
   - Record push status (success/failed/fallback_used)
   - Record push time and method

6. **Retry Mechanism"
   - If push fails, log error and trigger retry

## Capability Dependencies

- `yogacoach.channel_delivery`: Multi-channel delivery
- `yogacoach.line_push_service`: LINE push service
- `yogacoach.channel_bind_validator`: Channel bind validation

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Error Handling

- Channel not bound: Return error, log details
- Unsubscribed: Return error, log details
- Push failed: Fallback handling or return error, log details

