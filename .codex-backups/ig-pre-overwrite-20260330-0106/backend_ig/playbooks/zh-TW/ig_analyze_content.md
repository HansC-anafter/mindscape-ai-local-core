# 內容分析

## 概述

擷取並分析 Instagram 帳號的貼文內容，透過 LLM 分類主題標籤，並將結果寫入 `ig_posts` 資料表。

## 功能

- ✅ 擷取目標帳號的近期貼文
- ✅ 抓取標題、hashtag、@提及、互動數據
- ✅ LLM 驅動的主題分類
- ✅ PostgreSQL 持久化（upsert）

## 輸入參數

| 參數 | 類型 | 必需 | 說明 |
| --- | --- | --- | --- |
| `workspace_id` | string | 是 | 工作區 ID |
| `seed` | string | 是 | 正在分析的種子帳號 |
| `target_handles` | array | 否 | 目標帳號（空白則自動從 ig_accounts_flat 取得） |
| `posts_per_account` | integer | 否 | 每帳號貼文數（預設：9） |
| `user_data_dir` | string | 否 | 瀏覽器 profile 路徑 |

## 3 步驟 LLM 流程

1. **extract_posts** - 爬取貼文，返回 captions
2. **classify_topics** - LLM 分類每則 caption 的主題
3. **persist_with_topics** - 寫入貼文 + 主題到資料庫

## 主題類別

lifestyle, fashion, beauty, food, travel, fitness, tech, business, education, entertainment, other

## 使用範例

```json
{
  "workspace_id": "ws_abc123",
  "seed": "university.tw",
  "posts_per_account": 9
}
```

## 注意事項

1. **前置條件**：需先執行 `ig_analyze_following` 以產生 `ig_accounts_flat` 資料
2. **瀏覽器**：使用 Playwright 與持久化 profile
3. **速率限制**：內建請求間隔延遲

## 相關工具

- `ig.ig_content_analyzer`: 核心擷取工具
- `core_llm.structured_extract`: 主題分類
