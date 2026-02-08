---
playbook_code: yogacoach_payment_link_generator
version: 1.0.0
locale: en
name: "Payment Link Generator & Management"
description: "Generate course payment links (single/package/subscription), payment status tracking, refund processing, receipt generation, Taiwan payment integration"
capability_code: yogacoach
tags:
  - yoga
  - payment
  - link
---

# Playbook: Payment Link Generator & Management

**Playbook Code**: `yogacoach_payment_link_generator`
**Version**: 1.0.0
**Purpose": Generate course payment links (single/package/subscription), payment status tracking, refund processing, receipt generation, Taiwan payment integration

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `teacher_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "action": "generate_link",
  "payment_item": {
    "item_type": "single_class",
    "class_id": "class-abc123",
    "price": {
      "amount": 500,
      "currency": "TWD",
      "tax_included": true
    },
    "payment_methods": ["line_pay", "credit_card"],
    "expiry_hours": 24
  },
  "buyer_info": {
    "user_id": "user-123",
    "email": "user@example.com"
  }
}
```

## Output Data

```json
{
  "payment_link": {
    "url": "https://yogacoach.app/pay/abc12345",
    "short_code": "abc12345",
    "qr_code_url": "https://yogacoach.app/qr/abc12345",
    "expires_at": "2025-12-26T10:00:00Z"
  },
  "payment_status": {
    "payment_id": "payment-xyz789",
    "status": "pending",
    "payment_method": "line_pay"
  }
}
```

## Execution Steps

1. **Generate Payment Link" (action: generate_link)
   - Generate short code and URL
   - Generate QR Code
   - Set expiration time

2. **Check Payment Status" (action: check_status)
   - Query payment status
   - Return payment details

3. **Refund Processing" (action: refund)
   - Process refund request
   - Update payment status

4. **Generate Receipt"
   - Generate receipt PDF
   - Support Taiwan electronic invoice

## Capability Dependencies

- `yogacoach.payment_link_generator": Payment link generation
- `yogacoach.payment_gateway": Payment gateway (LINE Pay/JKOPay/Credit Card)
- `yogacoach.taiwan_invoice_service": Taiwan electronic invoice service

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Taiwan Payment Integration

- LINE Pay
- JKOPay
- Credit Card (TapPay/Stripe)
- Electronic Invoice (ezPay/ECPay)

## Error Handling

- Link generation failed: Return error, log details
- Payment status query failed: Return error, log details
- Refund processing failed: Return error, log details

