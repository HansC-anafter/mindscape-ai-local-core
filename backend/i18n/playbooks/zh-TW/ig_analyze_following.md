# IG 追蹤帳號分析

## 概述

使用瀏覽器自動化提取 Instagram 追蹤列表並分析帳號頁面。工具使用 Playwright 自動化瀏覽器，提取追蹤列表，並訪問每個帳號頁面進行統計和數據提取。

## 功能

- ✅ 提取指定帳號的追蹤列表
- ✅ 自動滾動載入所有追蹤帳號
- ✅ 提取帳號資訊（用戶名、顯示名稱、簡介、頭像、驗證狀態）
- ✅ 訪問每個帳號頁面進行統計分析（可選）
- ✅ 生成分析摘要報告

## 輸入參數

### 必需參數

- `target_username` (string): 要提取追蹤列表的目標 Instagram 用戶名
- `workspace_id` (string): Mindscape workspace ID

### 可選參數

- `max_accounts` (integer): 要處理的最大帳號數量（None = 全部）
- `visit_account_pages` (boolean): 是否訪問每個帳號頁面進行統計分析（預設：true）
- `run_mode` (string): 執行模式（`full` / `list` / `visit`，預設：`full`）
  - `full`：先滾動抓取清單；若 `visit_account_pages=true`，在滿足前置條件後繼續訪問頁面
  - `list`：只抓清單（會強制 `visit_account_pages=false`）
  - `visit`：只訪問頁面（會強制 `visit_account_pages=true`，並嘗試復用已保存清單；若沒有可用清單會報錯提示先跑 `list`）
- `allow_partial_resume` (boolean): 是否允許在清單未達 expected 時仍進行 `run_mode=visit`（預設：false）
  - 預設只允許在清單 `full` 或 `exhausted_incomplete`（已證據化 UI 無法再載入）時進行 visit

## 輸出

- `summary`: 分析摘要統計
  - `total_accounts`: 總帳號數
  - `verified_accounts`: 已驗證帳號數
  - `accounts_with_bio`: 有簡介的帳號數
  - `accounts_with_page_stats`: 有頁面統計的帳號數
  - `verified_percentage`: 已驗證帳號百分比
  - `bio_percentage`: 有簡介帳號百分比

- `accounts`: 帳號數據列表
  - `username`: 用戶名
  - `display_name`: 顯示名稱
  - `bio`: 簡介
  - `is_verified`: 是否已驗證
  - `avatar_url`: 頭像 URL
  - `account_link`: 帳號連結
  - `follower_count_text`: 追蹤者數量文字（如果訪問了頁面）
  - `following_count_text`: 追蹤中數量文字（如果訪問了頁面）
  - `post_count_text`: 貼文數量文字（如果訪問了頁面）
  - `profile_bio`: 個人檔案簡介（如果訪問了頁面）
  - `profile_image_url`: 個人檔案圖片 URL（如果訪問了頁面）
  - `page_analyzed_at`: 頁面分析時間（如果訪問了頁面）

- `metadata`: 分析元數據
  - `target_username`: 目標用戶名
  - `workspace_id`: Workspace ID
  - `analyzed_at`: 分析時間
  - `total_accounts`: 總帳號數
  - `visit_account_pages`: 是否訪問了頁面
  - `list_capture_status`: 清單捕獲狀態（`full` / `exhausted_incomplete` / `interrupted_incomplete` / `blocked` / `unknown_incomplete`）

## 使用範例

### 基本使用（提取追蹤列表並訪問頁面）

```json
{
  "target_username": "university.tw",
  "workspace_id": "ws_abc123",
  "run_mode": "full",
  "visit_account_pages": true
}
```

### 只提取列表，不訪問頁面

```json
{
  "target_username": "university.tw",
  "workspace_id": "ws_abc123",
  "run_mode": "list",
  "visit_account_pages": false
}
```

### 只訪問頁面（復用既有清單，跳過滾動）

```json
{
  "target_username": "university.tw",
  "workspace_id": "ws_abc123",
  "run_mode": "visit",
  "visit_account_pages": true
}
```

### 限制處理數量

```json
{
  "target_username": "university.tw",
  "workspace_id": "ws_abc123",
  "max_accounts": 100,
  "run_mode": "full",
  "visit_account_pages": true
}
```

## 注意事項

1. **瀏覽器自動化**：此工具使用 Playwright 進行瀏覽器自動化，需要安裝 Playwright 瀏覽器
2. **登入要求**：必須已登入 Instagram 帳號才能訪問追蹤列表
3. **執行時間**：如果啟用 `visit_account_pages`，處理大量帳號可能需要較長時間
4. **Rate Limiting**：訪問帳號頁面時會自動添加延遲以避免觸發 Instagram 的速率限制
5. **跑滿與 exhausted**：若有 `expected_following_count`（IG UI 顯示的追蹤中數量），系統會嘗試「嚴格跑滿」；若 UI 已證據化無法再載入，會以 `list_capture_status=exhausted_incomplete` 結束清單階段，並在 `visit_account_pages=true` 時允許直接接著 visit（因為這是 UI 能提供的完整結果）

## 相關工具

- `ig.ig_analyze_following`: 核心分析工具
