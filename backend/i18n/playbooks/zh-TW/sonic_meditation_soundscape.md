---
playbook_code: sonic_meditation_soundscape
version: 1.0.0
locale: zh-TW
name: "Meditation Soundscape & Guided Audio System"
description: "Soundscape layer + cue sounds + transition rules"
kind: user_workflow
capability_code: sonic_space
---

# Meditation Soundscape & Guided Audio System

Soundscape layer + cue sounds + transition rules

## 概述

冥想音景與引導音訊系統 playbook 為冥想和引導音訊體驗建立分層音景。它結合環境音景層與提示聲音和過渡規則。

**主要功能：**
- 設計環境音景層
- 添加引導提示聲音
- 定義過渡規則
- 建立沉浸式冥想體驗

**目的：**
此 playbook 建立冥想音景和引導音訊系統，結合環境背景與結構化音訊提示，用於冥想、放鬆和引導體驗。

**相關 Playbooks：**
- `sonic_navigation` - 為音景層尋找聲音
- `sonic_dsp_transform` - 為音景處理聲音
- `sonic_intent_parser` - 定義音景需求

詳細規格請參考：`playbooks/specs/sonic_meditation_soundscape.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Design Soundscape

Design soundscape layer

- **Action**: `design_soundscape`
- **Tool**: `sonic_space.sonic_intent_parser`
  - ✅ Format: `capability.tool_name`

### Step 2: Add Cue Sounds

Add cue sounds and transition rules

- **Action**: `add_cue_sounds`
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

1. **冥想音景**
   - 為冥想建立環境背景
   - 設計沉浸式聲音環境
   - 支援冥想練習

2. **引導音訊體驗**
   - 添加引導提示聲音
   - 建立結構化音訊體驗
   - 支援引導冥想課程

3. **分層音訊系統**
   - 結合多個聲音層
   - 定義過渡規則
   - 建立動態音訊體驗

## 使用範例

### 範例 1：建立冥想音景

```json
{
  "soundscape_type": "nature_meditation",
  "layers": ["ambient_nature", "distant_birds", "gentle_water"],
  "cue_sounds": ["bell_start", "bell_end"],
  "duration": 1800
}
```

**預期輸出：**
- 帶環境背景的分層音景
- 冥想引導的提示聲音
- 平滑播放的過渡規則

## 技術細節

**音景設計：**
- 設計環境音景層
- 結合多個音訊來源
- 建立沉浸式音訊環境

**提示聲音整合：**
- 添加結構化提示聲音
- 定義過渡規則
- 支援引導音訊體驗

**工具依賴：**
- `sonic_intent_parser` - 定義音景需求
- `sonic_dsp_transform` - 為音景處理聲音

## 相關 Playbooks

- **sonic_navigation** - 為音景層尋找聲音
- **sonic_dsp_transform** - 為音景處理聲音
- **sonic_intent_parser** - 定義音景需求

## 參考資料

- **規格文件**: `playbooks/specs/sonic_meditation_soundscape.json`
