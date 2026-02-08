# 帳號標籤化

## 概述

對已擷取的 IG 帳號（`ig_accounts_flat` 資料表）計算分類標籤並寫入 `ig_account_profiles`。此工具分析帳號資訊以判斷帳號類型、影響力層級，並萃取 Bio 關鍵字。

## 功能

- ✅ 分類帳號類型（KOL、品牌、個人、媒體、未知）
- ✅ 判斷影響力層級（Nano、Micro、Mid、Macro、Mega）
- ✅ 使用 NLP 萃取 Bio 關鍵字
- ✅ 偵測 Bio 語言
- ✅ 計算互動指標
- ✅ Upsert 至 PostgreSQL（衝突處理）

## 輸入參數

### 必需參數

- `workspace_id` (string): Mindscape workspace ID
- `seed` (string): 目標種子帳號（已分析的帳號）

### 可選參數

- `force_recompute` (boolean): 強制重新計算已存在的標籤（預設：false）

## 輸出

- `processed`: 處理的帳號總數
- `created`: 新建立的標籤數
- `updated`: 更新的標籤數
- `skipped`: 跳過的帳號數（已存在且未強制重算）

## 帳號類型分類

| 類型 | 判斷指標 |
|------|----------|
| **KOL** | creator、influencer、blogger、合作、業配、邀約 |
| **Brand** | official、®、™、shop、store、品牌、官方 |
| **Media** | news、magazine、journalist、新聞、媒體 |
| **Personal** | 一般帳號預設 |
| **Unknown** | 資料不足 |

## 影響力層級門檻

| 層級 | 粉絲數範圍 |
|------|------------|
| Mega | 100萬+ |
| Macro | 10萬-100萬 |
| Mid | 1萬-10萬 |
| Micro | 1千-1萬 |
| Nano | <1千 |

## 使用範例

```json
{
  "workspace_id": "ws_abc123",
  "seed": "university.tw",
  "force_recompute": false
}
```

## 注意事項

1. **前置條件**：需先執行 `ig_analyze_following` 以產生 `ig_accounts_flat` 資料
2. **NLP 套件**：使用 `jieba` 處理中文、`langdetect` 偵測語言（可選）
3. **資料庫**：寫入 PostgreSQL `ig_account_profiles` 資料表

## 相關工具

- `ig.ig_analyze_following`: 擷取追蹤列表（前置）
- `ig.ig_profile_tagger`: 核心標籤工具
