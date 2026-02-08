---
playbook_code: sonic_export_gate
version: 1.0.0
locale: zh-TW
name: "Export Compliance Gate"
description: "Final compliance check before export (license/watermark/tracking)"
kind: user_workflow
capability_code: sonic_space
---

# Export Compliance Gate

Final compliance check before export (license/watermark/tracking)

## 概述

匯出合規閘門 playbook 是音訊資產離開 Sonic Space 系統前的最終檢查點。它執行全面的合規檢查，包括授權驗證、浮水印應用和追蹤設定。

**主要功能：**
- 多層合規檢查
- 風險等級評估
- 高風險資產的自動浮水印應用
- 所有匯出的審計日誌
- 授權驗證
- 使用範圍驗證

**目的：**
此 playbook 確保所有匯出的音訊資產符合法律要求和使用限制。這是防止未授權或不合規匯出的最後防線。

**相關 Playbooks：**
- `sonic_license_governance` - 在匯出前驗證授權卡
- `sonic_kit_packaging` - 在匯出前打包資產
- `sonic_navigation` - 選擇要匯出的資產

詳細規格請參考：`playbooks/specs/sonic_export_gate.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Check License

Check license compliance

- **Action**: `check_license`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Apply Watermark

Apply watermark if needed

- **Action**: `apply_watermark`
- **Tool**: `sonic_space.sonic_export_gate`
  - ✅ Format: `capability.tool_name`

### Step 3: Final Check

Final compliance check before export

- **Action**: `final_check`
- **Tool**: `sonic_space.sonic_export_gate`
  - ✅ Format: `capability.tool_name`

## 安全檢查

No guardrails defined.

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **商業匯出驗證**
   - 驗證商業使用的授權合規性
   - 檢查使用範圍限制
   - 如需要，應用浮水印

2. **高風險資產保護**
   - 識別高/嚴重風險資產
   - 自動應用浮水印
   - 記錄匯出以供審計追蹤

3. **授權到期檢查**
   - 驗證授權未過期
   - 阻擋過期授權的匯出
   - 對即將到期的授權發出警示

4. **批量匯出合規**
   - 一次檢查多個資產
   - 匯總合規狀態
   - 產生合規報告

## 使用範例

### 範例 1：標準匯出檢查

```json
{
  "asset_ids": ["asset_123", "asset_456"],
  "target_usage": "commercial",
  "apply_watermark": false
}
```

**預期輸出：**
- 每個資產的合規狀態
- 授權驗證結果
- 匯出批准或拒絕

### 範例 2：高風險資產匯出

```json
{
  "asset_ids": ["asset_789"],
  "target_usage": "commercial",
  "apply_watermark": true
}
```

**預期輸出：**
- 合規檢查通過
- 對資產應用浮水印
- 建立審計日誌條目
- 批准帶浮水印的匯出

## 技術細節

**合規檢查：**
1. 授權驗證（有效、未過期）
2. 使用範圍驗證（符合目標使用）
3. 風險等級評估（低/中/高/嚴重）
4. 署名要求檢查

**浮水印應用：**
- 自動應用於高/嚴重風險資產
- 不可聽的浮水印用於追蹤
- 檔案標頭中的元數據浮水印
- 提供浮水印預覽

**風險等級：**
- **低**：自有、適當授權
- **中**：有限制的 CC 授權
- **高**：授權不明確、客戶提供
- **嚴重**：潛在版權問題

**審計日誌：**
- 記錄所有匯出嘗試
- 包含資產 ID、使用者、時間戳記
- 記錄合規狀態
- 追蹤浮水印應用

**工具依賴：**
- `sonic_export_gate` - 合規檢查和浮水印

**匯出請求結構：**
匯出請求包括：
- 要匯出的資產 ID
- 目標使用場景
- 浮水印偏好
- 匯出格式要求

## 相關 Playbooks

- **sonic_license_governance** - 在匯出前驗證授權卡
- **sonic_kit_packaging** - 在匯出前打包資產
- **sonic_navigation** - 選擇要匯出的資產
- **sonic_asset_import** - 匯入可能被匯出的資產

## 參考資料

- **規格文件**: `playbooks/specs/sonic_export_gate.json`
