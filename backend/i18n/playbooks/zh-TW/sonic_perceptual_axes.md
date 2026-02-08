---
playbook_code: sonic_perceptual_axes
version: 1.0.0
locale: zh-TW
name: "Perceptual Axes Calibration"
description: "Calibrate warm/cold, bright/dark, dry/wet perceptual axes for stable steering"
kind: user_workflow
capability_code: sonic_space
---

# Perceptual Axes Calibration

Calibrate warm/cold, bright/dark, dry/wet perceptual axes for stable steering

## 概述

感知軸校準 playbook 校準感知軸（溫暖/冷調、明亮/暗調、乾燥/濕潤），以在潛在空間中實現穩定導航。這是 `sonic_quick_calibration` 的進階版本，支援更多軸和詳細校準。

**主要功能：**
- 校準多個感知軸
- 支援溫暖/冷調、明亮/暗調、乾燥/濕潤軸
- 使用更多註釋進行詳細校準
- 在潛在空間中穩定導航

**目的：**
此 playbook 建立全面的感知軸，以啟用精確的基於維度的聲音導航。它擴展 `sonic_quick_calibration`，支援更多軸和詳細校準流程。

**相關 Playbooks：**
- `sonic_quick_calibration` - 快速 3 軸校準（P0 版本）
- `sonic_navigation` - 使用校準的軸進行導航
- `sonic_prospecting_lite` - 使用軸進行聲音生成

詳細規格請參考：`playbooks/specs/sonic_perceptual_axes.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Load Calibration Data

Load calibration data for axes

- **Action**: `load_calibration_data`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Calibrate Axes

Calibrate warm/cold, bright/dark, dry/wet axes

- **Action**: `calibrate_axes`
- **Tool**: `sonic_space.sonic_axes_steer`
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

1. **全面軸校準**
   - 校準多個感知軸
   - 支援溫暖/冷調、明亮/暗調、乾燥/濕潤
   - 詳細校準流程

2. **進階導航**
   - 啟用精確的基於維度的導航
   - 支援複雜的多軸導航
   - 改善導航準確性

3. **自訂軸定義**
   - 定義自訂感知軸
   - 校準領域特定維度
   - 支援專業化使用案例

## 使用範例

### 範例 1：校準多個軸

```json
{
  "target_axes": ["warmth", "brightness", "spatiality", "dryness"],
  "pairs_per_axis": 50,
  "annotators": 3
}
```

**預期輸出：**
- 校準的感知軸模型
- 所有軸的方向向量
- 校準統計和驗證

## 技術細節

**校準流程：**
- 載入多個軸的校準數據
- 執行成對比較註釋
- 計算方向向量
- 驗證校準品質

**支援的軸：**
- 溫暖（溫暖/冷調）
- 亮度（明亮/暗調）
- 空間感（寬敞/親密）
- 乾燥度（乾燥/濕潤）
- 自訂軸

**工具依賴：**
- `sonic_axes_steer` - 軸校準和導航

## 相關 Playbooks

- **sonic_quick_calibration** - 快速 3 軸校準（P0 版本）
- **sonic_navigation** - 使用校準的軸進行導航
- **sonic_prospecting_lite** - 使用軸進行聲音生成

## 參考資料

- **規格文件**: `playbooks/specs/sonic_perceptual_axes.json`
