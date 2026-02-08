---
playbook_code: sonic_cross_media
version: 1.0.0
locale: zh-TW
name: "Cross-Media Application"
description: "Apply same fingerprint across multiple media"
kind: user_workflow
capability_code: sonic_space
---

# Cross-Media Application

Apply same fingerprint across multiple media

## 概述

跨媒體應用 playbook 將相同的聲音指紋應用到多種媒體類型，在不同平台和格式中實現一致的品牌音訊識別。

**主要功能：**
- 從來源提取聲音指紋
- 應用到多種媒體類型
- 在媒體間維護品牌一致性
- 支援跨平台音訊識別

**目的：**
此 playbook 讓使用者能夠在不同媒體類型和平台間維護一致的品牌音訊識別。它確保品牌音訊特性在應用到不同情境時得到保留。

**相關 Playbooks：**
- `sonic_fingerprint_extract` - 從來源提取指紋
- `sonic_dsp_transform` - 將指紋應用到媒體
- `sonic_logo_gen` - 生成品牌聲音標誌

詳細規格請參考：`playbooks/specs/sonic_cross_media.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Extract Fingerprint

Extract sonic fingerprint from source

- **Action**: `extract_fingerprint`
- **Tool**: `sonic_space.sonic_fingerprint_extractor`
  - ✅ Format: `capability.tool_name`

### Step 2: Apply to Media

Apply fingerprint across multiple media

- **Action**: `apply_to_media`
- **Tool**: `sonic_space.sonic_dsp_transform`
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

1. **品牌一致性**
   - 在媒體間應用品牌指紋
   - 維護音訊識別一致性
   - 支援跨平台品牌

2. **多媒體專案**
   - 將相同指紋應用到影片、音訊、互動媒體
   - 維護一致的音訊特性
   - 支援統一的品牌體驗

## 使用範例

### 範例 1：應用指紋

```json
{
  "source_fingerprint_id": "fingerprint_123",
  "target_media": ["video_001", "audio_002", "interactive_003"]
}
```

**預期輸出：**
- 所有目標媒體都應用了指紋
- 一致的品牌音訊識別
- 維護跨媒體一致性

## 技術細節

**跨媒體應用：**
- 從來源提取指紋
- 應用到多種媒體類型
- 維護品牌一致性
- 支援各種媒體格式

**工具依賴：**
- `sonic_fingerprint_extractor` - 提取指紋
- `sonic_dsp_transform` - 應用到媒體

## 相關 Playbooks

- **sonic_fingerprint_extract** - 從來源提取指紋
- **sonic_dsp_transform** - 將指紋應用到媒體
- **sonic_logo_gen** - 生成品牌聲音標誌

## 參考資料

- **規格文件**: `playbooks/specs/sonic_cross_media.json`
