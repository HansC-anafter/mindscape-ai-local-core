---
playbook_code: seo_content_generation
version: 1.0.0
capability_code: openseo
name: SEO 內容生成
description: |
  使用 Lens Composition 生成 SEO 優化的內容，支持多種內容類型（blog, product, landing_page）。
  完整流程：選擇 Composition → 融合 Lens → 生成內容 → SEO 優化 → 可選發布到 WordPress。
tags:
  - seo
  - content-generation
  - lens-composition
  - wordpress

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - openseo.generate_seo_content
  - openseo.optimize_content_for_seo
  - openseo.publish_to_wordpress
  - openseo.create_wordpress_draft
  - openseo.fuse_lens_composition

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: ✍️
---

# SEO 內容生成 - SOP

## 目標

使用 Lens Composition 生成 SEO 優化的內容，支持多種內容類型，並可選發布到 WordPress。

**核心價值**：
- 基於 Lens Composition 生成品牌一致的內容
- 自動 SEO 優化（關鍵詞、標題、meta description）
- 計算 SEO 分數和可讀性分數
- 可選發布到 WordPress（draft 或 publish）

## 執行步驟

### Phase 0: 準備輸入資料

**執行順序**：
1. 步驟 0.0: 收集內容需求
   - 內容類型（blog, product, landing_page）
   - 目標關鍵詞
   - 目標受眾
   - 內容長度要求

2. 步驟 0.1: 選擇或創建 Composition
   - 使用現有的 Composition ID
   - 或從 Preset 快速創建 Composition

### Phase 1: 融合 Lens Composition

**執行順序**：
1. 步驟 1.0: 融合 Composition
   - 調用 `fuse_lens_composition`
   - 獲取融合後的統一上下文（constraints + syntax）

### Phase 2: 生成 SEO 內容

**執行順序**：
1. 步驟 2.0: 生成內容
   - 調用 `generate_seo_content`
   - 使用融合後的 Lens 上下文
   - 生成標題、內容、meta description

2. 步驟 2.1: SEO 優化
   - 自動優化關鍵詞布局
   - 優化標題和 meta description
   - 計算 SEO 分數

3. 步驟 2.2: 可讀性評估
   - 計算可讀性分數
   - 生成改進建議

### Phase 3: 審查與調整（可選）

**執行順序**：
1. 步驟 3.0: 展示生成結果
   - 顯示內容、標題、meta description
   - 顯示 SEO 分數和可讀性分數
   - 顯示改進建議

2. 步驟 3.1: 用戶調整（如需要）
   - 用戶可以修改內容
   - 重新生成或優化

### Phase 4: 發布到 WordPress（可選）

**執行順序**：
1. 步驟 4.0: 選擇發布方式
   - Draft：創建草稿供審查
   - Publish：直接發布

2. 步驟 4.1: 發布內容
   - 調用 `create_wordpress_draft` 或 `publish_to_wordpress`
   - 包含 composition_id 用於追溯
   - 返回 post_id 和 revision_id

## 輸入參數

- `composition_id` (string, required): Lens Composition ID
- `content_type` (string, required): 內容類型（blog, product, landing_page）
- `target_keywords` (array, required): 目標關鍵詞列表
- `target_audience` (string, optional): 目標受眾描述
- `tone` (string, optional): 內容語調
- `word_count` (integer, optional): 目標字數
- `workspace_id` (string, required): Workspace ID
- `publish_to_wordpress` (boolean, optional): 是否發布到 WordPress
- `wordpress_site_id` (string, optional): WordPress 站點 ID
- `publish_status` (string, optional): 發布狀態（draft, publish）

## 輸出結果

- `content` (string): 生成的內容
- `title` (string): SEO 優化的標題
- `meta_description` (string): SEO 優化的 meta description
- `seo_score` (object): SEO 分數詳情
- `readability_score` (float): 可讀性分數
- `keywords_used` (array): 使用的關鍵詞
- `suggestions` (array): 改進建議
- `wordpress_post_id` (integer, optional): WordPress 文章 ID
- `wordpress_post_url` (string, optional): WordPress 文章 URL
- `revision_id` (string, optional): Revision ID

## 注意事項

1. **Composition 必須存在**：確保 composition_id 有效
2. **關鍵詞必須提供**：至少需要一個目標關鍵詞
3. **WordPress 發布可選**：如果不提供 wordpress_site_id，則只生成內容不發布
4. **SEO 分數建議**：SEO 分數低於 70 時，建議調整內容或關鍵詞









