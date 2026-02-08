---
playbook_code: sonic_logo_gen
version: 1.0.0
locale: zh-TW
name: "Brand Sonic Logo Generation"
description: "Generate Sonic Logo main version + contextual versions"
kind: user_workflow
capability_code: sonic_space
---

# Brand Sonic Logo Generation

Generate Sonic Logo main version + contextual versions

## 概述

品牌聲音標誌生成 playbook 為品牌生成聲音標誌，建立主版本和情境變化。聲音標誌是代表品牌識別的短而難忘的音訊簽名。

**主要功能：**
- 生成主聲音標誌版本
- 建立情境變化
- 維護品牌識別一致性
- 支援多種使用情境

**目的：**
此 playbook 建立作為音視覺識別元素的品牌聲音標誌。聲音標誌用於品牌、行銷和使用者體驗，以建立難忘的品牌關聯。

**相關 Playbooks：**
- `sonic_fingerprint_extract` - 提取品牌音訊指紋
- `sonic_intent_parser` - 定義品牌識別
- `sonic_dsp_transform` - 建立情境變化

詳細規格請參考：`playbooks/specs/sonic_logo_gen.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Define Brand

Define brand identity for sonic logo

- **Action**: `define_brand`
- **Tool**: `sonic_space.sonic_intent_parser`
  - ✅ Format: `capability.tool_name`

### Step 2: Generate Main

Generate Sonic Logo main version

- **Action**: `generate_main`
- **Tool**: `sonic_space.sonic_fingerprint_extractor`
  - ✅ Format: `capability.tool_name`

### Step 3: Generate Contextual

Generate contextual versions

- **Action**: `generate_contextual`
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

1. **品牌識別建立**
   - 為品牌生成主聲音標誌
   - 建立難忘的音訊簽名
   - 建立品牌音訊識別

2. **情境變化**
   - 為不同情境生成變化
   - 適應各種使用場景的標誌
   - 在變化中維護品牌一致性

3. **音視覺品牌**
   - 建立符合視覺識別的聲音標誌
   - 支援跨媒體品牌一致性
   - 增強品牌識別度

## 使用範例

### 範例 1：生成品牌標誌

```json
{
  "brand_identity": "modern_tech",
  "duration": 3.0,
  "contexts": ["app_startup", "notification", "advertisement"]
}
```

**預期輸出：**
- 主聲音標誌版本
- 指定情境的情境變化
- 所有變化都維護品牌識別

## 技術細節

**標誌生成：**
- 從描述或參考定義品牌識別
- 生成主標誌版本
- 建立情境變化
- 維護品牌指紋一致性

**工具依賴：**
- `sonic_intent_parser` - 定義品牌識別
- `sonic_fingerprint_extractor` - 提取品牌指紋
- `sonic_dsp_transform` - 建立變化

## 相關 Playbooks

- **sonic_fingerprint_extract** - 提取品牌音訊指紋
- **sonic_intent_parser** - 定義品牌識別
- **sonic_dsp_transform** - 建立情境變化

## 參考資料

- **規格文件**: `playbooks/specs/sonic_logo_gen.json`
