# 關係網絡分析

## 概述

跨多個種子帳號分析追蹤關係，找出共同追蹤模式與社群聚類。

## 功能

- ✅ 找出被多個種子追蹤的帳號
- ✅ 使用 Louvain 演算法偵測社群
- ✅ 跨種子關係分析

## 輸入參數

| 參數 | 類型 | 必需 | 說明 |
| --- | --- | --- | --- |
| `workspace_id` | string | 是 | 工作區 ID |
| `seeds` | array | 是 | 種子帳號（至少 2 個） |
| `analysis_type` | string | 否 | "common_following" 或 "community" |
| `min_overlap` | integer | 否 | 最小種子數（預設：2） |
| `resolution` | number | 否 | Louvain resolution（預設：1.0） |

## 分析類型

### common_following
找出被多個種子追蹤的帳號，用於識別：
- 共同興趣
- 產業意見領袖
- 潛在合作對象

### community
使用 Louvain 聚類演算法偵測社群，用於：
- 了解追蹤者網絡結構
- 識別不同受眾群體
- 發現聚類模式

## 使用範例

```json
{
  "workspace_id": "ws_abc123",
  "seeds": ["account_a", "account_b", "account_c"],
  "analysis_type": "common_following",
  "min_overlap": 2
}
```

## 前置條件

- 已對所有種子執行 `ig_analyze_following`
- `ig_follow_edges` 資料表有資料

## 相依套件

- `networkx>=3.0`
- `python-louvain>=0.16`
