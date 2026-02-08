---
playbook_code: yogacoach_billing_and_invoicing
version: 1.0.0
locale: en
name: "Billing & Invoicing"
description: "Subscription status management, usage statistics, invoice generation, receipt download, reconciliation reports"
capability_code: yogacoach
tags:
  - yoga
  - billing
  - invoice
---

# Playbook: Billing & Invoicing

**Playbook Code**: `yogacoach_billing_and_invoicing`
**Version**: 1.0.0
**Purpose": Subscription status management, usage statistics, invoice generation, receipt download, reconciliation reports

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `subscription_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "action": "generate_invoice",
  "billing_period": {
    "start_date": "2025-12-01",
    "end_date": "2025-12-31"
  }
}
```

## Output Data

```json
{
  "invoice_id": "INV-202512-xxxx",
  "subscription_id": "sub-abc123",
  "billing_period": {
    "start_date": "2025-12-01",
    "end_date": "2025-12-31"
  },
  "billing_period_usage": {
    "minutes_used": 240,
    "sessions_count": 48,
    "students_count": 15
  },
  "invoice_details": {
    "plan_name": "Pro Plan",
    "base_price_usd": 99.00,
    "overage_charges_usd": 0.00,
    "tax_usd": 4.95,
    "total_usd": 103.95,
    "currency": "USD"
  },
  "payment_status": "pending",
  "invoice_url": "https://yogacoach.app/invoices/INV-202512-xxxx.pdf",
  "due_date": "2026-01-07"
}
```

## Execution Steps

1. **Get Usage Statistics"
   - Get usage data from D1 (Plan & Quota Guard)
   - Statistics: minutes, sessions, students

2. **Generate Invoice"
   - Calculate base price and overage charges
   - Calculate tax
   - Generate invoice ID and PDF

3. **Taiwan Invoice Special Handling"
   - Support 2-invoice / 3-invoice format
   - Support carrier (mobile barcode / citizen digital certificate / member carrier)

4. **Send Invoice"
   - Generate invoice PDF
   - Send Email notification (optional)

## Capability Dependencies

- `yogacoach.billing_manager`: Billing management
- `yogacoach.payment_gateway`: Payment gateway

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Error Handling

- Usage statistics failed: Return error, log details
- Invoice generation failed: Return error, log details

