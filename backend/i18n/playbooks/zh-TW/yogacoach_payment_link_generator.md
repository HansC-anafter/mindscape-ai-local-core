---
playbook_code: yogacoach_payment_link_generator
version: 1.0.0
locale: zh-TW
name: "付費連結生成與管理"
description: "生成課程付費連結（單次/套餐/訂閱）、支付狀態追蹤、退款處理、收據生成、台灣支付整合"
capability_code: yogacoach
tags:
  - yoga
  - payment
  - link
---

# Playbook: 付費連結生成與管理

**Playbook Code**: `yogacoach_payment_link_generator`
**版本**: 1.0.0
**用途**: 生成課程付費連結（單次/套餐/訂閱）、支付狀態追蹤、退款處理、收據生成、台灣支付整合

---

## 輸入資料

**注意**：`tenant_id`、`teacher_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

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

## 輸出資料

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

## 執行步驟

1. **生成付費連結**（action: generate_link）
   - 生成短碼和 URL
   - 生成 QR Code
   - 設置過期時間

2. **檢查支付狀態**（action: check_status）
   - 查詢支付狀態
   - 返回支付詳情

3. **退款處理**（action: refund）
   - 處理退款請求
   - 更新支付狀態

4. **生成收據**
   - 生成收據 PDF
   - 支援台灣電子發票

## 能力依賴

- `yogacoach.payment_link_generator`: 付費連結生成
- `yogacoach.payment_gateway`: 支付網關（LINE Pay/街口/信用卡）
- `yogacoach.taiwan_invoice_service`: 台灣電子發票服務

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 台灣支付整合

- LINE Pay
- 街口支付
- 信用卡（TapPay/Stripe）
- 電子發票（ezPay/ECPay）

## 錯誤處理

- 連結生成失敗：返回錯誤，記錄日誌
- 支付狀態查詢失敗：返回錯誤，記錄日誌
- 退款處理失敗：返回錯誤，記錄日誌

