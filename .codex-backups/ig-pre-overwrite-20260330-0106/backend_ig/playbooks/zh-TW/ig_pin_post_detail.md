# 釘選貼文詳情

## 目標
瀏覽單一或多則 IG 貼文，釘選所有圖片（包含輪播圖片）並附帶完整 metadata（文案、按讚數、留言數、時間戳）。

## 前置條件
- Playwright 瀏覽器自動化可用
- 有效的貼文 shortcode

## 步驟

### 步驟一：擷取貼文詳情
透過瀏覽器自動化導航至貼文頁面，提取文案、互動數據及所有輪播圖片。

工具：`ig.ig_fetch_post_detail`

### 步驟二：釘選所有圖片
將每張提取的圖片釘選為 reference。輪播圖片透過 `carousel_parent_id` 串聯。貼文 metadata（文案、按讚、留言）附加到所有 reference 上。

工具：`ig.ig_pin_post_detail`

## 輸出
- 每張圖片一個 reference（輪播貼文會產生多個關聯的 reference）
- 每個 reference 包含：`post_caption`、`post_like_count`、`post_comment_count`、`post_timestamp`
- 輪播 reference 透過 `carousel_parent_id` 和 `carousel_index` 關聯
- 自動為每個新 reference 排入背景視覺分析
