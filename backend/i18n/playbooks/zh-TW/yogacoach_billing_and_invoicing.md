---
playbook_code: yogacoach_billing_and_invoicing
version: 1.0.0
locale: zh-TW
name: "計費與發票管理"
description: "方案狀態管理、使用量統計、發票生成、收據下載、對賬報表"
capability_code: yogacoach
tags:
  - yoga
  - billing
  - invoice
---

# Playbook: 計費與發票管理

**Playbook Code**: `yogacoach_billing_and_invoicing`
**版本**: 1.0.0
**用途**: 方案狀態管理、使用量統計、發票生成、收據下載、對賬報表

---

## 輸入資料

**注意**：`tenant_id`、`subscription_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "action": "generate_invoice",
  "billing_period": {
    "start_date": "2025-12-01",
    "end_date": "2025-12-31"
  }
}
```

## 輸出資料

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
    "plan_name": "專業方案",
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

## 執行步驟

1. **獲取使用量統計**
   - 從 D1 (Plan & Quota Guard) 獲取使用量數據
   - 統計分鐘數、會話數、學員數

2. **生成發票**
   - 計算基礎價格和超量費用
   - 計算稅費
   - 生成發票 ID 和 PDF

3. **台灣發票特殊處理**
   - 支援二聯式/三聯式發票
   - 支援載具（手機條碼/自然人憑證/會員載具）

4. **發送發票**
   - 生成發票 PDF
   - 發送 Email 通知（可選）

## 能力依賴

- `yogacoach.billing_manager`: 計費管理
- `yogacoach.payment_gateway`: 支付網關

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 錯誤處理

- 使用量統計失敗：返回錯誤，記錄日誌
- 發票生成失敗：返回錯誤，記錄日誌

