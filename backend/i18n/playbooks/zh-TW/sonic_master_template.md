---
playbook_code: sonic_master_template
version: 1.0.0
locale: zh-TW
name: "Mixing/Mastering Template"
description: "Standardize loudness/dynamics/spatial depth"
kind: user_workflow
capability_code: sonic_space
---

# Mixing/Mastering Template

Standardize loudness/dynamics/spatial depth

## 概述

混音/母帶處理模板 playbook 使用預定義模板將音訊資產標準化為一致的響度、動態和空間深度。它確保集合中的所有音訊都符合相同的製作標準。

**主要功能：**
- 標準化響度等級
- 標準化動態
- 一致的空間深度
- 基於模板的處理

**目的：**
此 playbook 通過應用標準化的混音和母帶處理模板確保音訊在集合中的一致性。對於建立具有一致製作品質的專業聲音庫至關重要。

**相關 Playbooks：**
- `sonic_dsp_transform` - 應用 DSP 變形
- `sonic_kit_packaging` - 在打包前標準化
- `sonic_qa` - 母帶處理後品質檢查

詳細規格請參考：`playbooks/specs/sonic_master_template.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Analyze Audio

Analyze loudness/dynamics/spatial depth

- **Action**: `analyze_audio`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Apply Template

Apply mixing/mastering template

- **Action**: `apply_template`
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

1. **集合標準化**
   - 在集合中標準化響度
   - 為一致性標準化動態
   - 應用一致的空間處理

2. **專業製作**
   - 應用專業混音/母帶處理模板
   - 確保廣播就緒品質
   - 維護製作標準

3. **套件準備**
   - 在打包前標準化
   - 確保套件中的一致品質
   - 專業呈現

## 使用範例

### 範例 1：應用母帶處理模板

```json
{
  "audio_asset_id": "asset_123",
  "template": "broadcast_standard",
  "target_loudness": -14.0
}
```

**預期輸出：**
- 已母帶處理的音訊，標準化為：
  - 響度（-14 LUFS）
  - 動態（一致範圍）
  - 空間深度（基於模板）

## 技術細節

**母帶處理流程：**
- 分析當前響度、動態、空間特性
- 應用基於模板的處理
- 標準化至目標規格
- 驗證輸出品質

**模板類型：**
- 廣播標準
- 串流優化
- Lo-fi 美學
- Hi-fi 專業

**工具依賴：**
- `sonic_audio_analyzer` - 分析音訊特性
- `sonic_dsp_transform` - 應用母帶處理變形

## 相關 Playbooks

- **sonic_dsp_transform** - 應用 DSP 變形
- **sonic_kit_packaging** - 在打包前標準化
- **sonic_qa** - 母帶處理後品質檢查

## 參考資料

- **規格文件**: `playbooks/specs/sonic_master_template.json`
