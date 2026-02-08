---
playbook_code: sonic_dsp_transform
version: 1.0.0
locale: zh-TW
name: "DSP Transformation Engine"
description: "Low-risk DSP transformations (time stretch/EQ/reverb/granular)"
kind: user_workflow
capability_code: sonic_space
---

# DSP Transformation Engine

Low-risk DSP transformations (time stretch/EQ/reverb/granular)

## 概述

DSP 變形引擎 playbook 對音訊段應用低風險的數位訊號處理變形。它支援時間拉伸、音高偏移、EQ、混響、顆粒效果等。

**主要功能：**
- 9 種變形類型（time_stretch、pitch_shift、eq_profile、filter_sweep、convolution_reverb、stereo_width、granular、glitch、bitcrush）
- 10+ 內建預設
- 參數驗證和約束
- 安全等級分類
- 即時預覽支援

**目的：**
此 playbook 讓使用者能夠修改音訊段，同時保留核心特性。它用於聲音變化生成、混音和創意探索。

**相關 Playbooks：**
- `sonic_prospecting_lite` - 使用 DSP 變形進行聲音生成
- `sonic_variation` - 使用 DSP 產生變化
- `sonic_master_template` - 應用混音/母帶處理模板

詳細規格請參考：`playbooks/specs/sonic_dsp_transform.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Load Audio

Load audio segment for transformation

- **Action**: `load_audio`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Apply Transform

Apply DSP transformation (time stretch/EQ/reverb/granular)

- **Action**: `apply_transform`
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

1. **時間拉伸**
   - 在不改變音高的情況下調整節奏
   - 將循環同步到專案節奏
   - 建立基於時間的變化

2. **音高偏移**
   - 將聲音轉調到不同調性
   - 建立和聲變化
   - 匹配專案音高

3. **EQ 和濾波**
   - 塑形頻率響應
   - 移除不需要的頻率
   - 增強特定頻段

4. **空間效果**
   - 應用混響以增加空間深度
   - 調整立體聲寬度
   - 建立沉浸式音景

5. **創意效果**
   - 顆粒合成
   - 故障效果
   - 位元壓縮以獲得 lo-fi 特性

## 使用範例

### 範例 1：時間拉伸

```json
{
  "segment_id": "seg_123",
  "transform_type": "time_stretch",
  "params": {
    "stretch_factor": 1.2
  }
}
```

**預期輸出：**
- 變形後的音訊段（慢 20%）
- 音高不變
- 品質驗證

### 範例 2：EQ 設定檔

```json
{
  "segment_id": "seg_456",
  "transform_type": "eq_profile",
  "params": {
    "profile": "warm",
    "boost_freq": 200,
    "cut_freq": 5000
  }
}
```

**預期輸出：**
- 應用 EQ 的段
- 更溫暖的頻率響應
- 高頻降低

## 技術細節

**變形類型：**
- `time_stretch`：不改變音高的節奏變化
- `pitch_shift`：音高轉調
- `eq_profile`：頻率塑形
- `filter_sweep`：動態濾波
- `convolution_reverb`：空間混響
- `stereo_width`：立體聲場調整
- `granular`：顆粒合成
- `glitch`：故障效果
- `bitcrush`：位元減少

**內建預設：**
- 溫暖、明亮、暗調、寬敞
- Lo-fi、Hi-fi
- 復古、現代
- 以及更多...

**安全等級：**
- **低**：細微變化，保留特性
- **中**：適度變化，特性可能改變
- **高**：顯著變化，特性可能改變

**參數驗證：**
- 所有參數的範圍約束
- 安全等級檢查
- 品質保留規則

**工具依賴：**
- `sonic_audio_analyzer` - 載入音訊段
- `sonic_dsp_transform` - 應用變形

**服務依賴：**
- `dsp_processing` - DSP 處理流程（librosa、ffmpeg）

**效能：**
- 短段的即時預覽
- 多個段的批次處理
- 長檔案的異步處理

## 相關 Playbooks

- **sonic_prospecting_lite** - 使用 DSP 變形進行聲音生成
- **sonic_variation** - 使用 DSP 產生變化
- **sonic_master_template** - 應用混音/母帶處理模板
- **sonic_kit_packaging** - 為 sound kits 建立變化

## 參考資料

- **規格文件**: `playbooks/specs/sonic_dsp_transform.json`
