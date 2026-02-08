---
playbook_code: seo_batch_update
version: 1.0.0
capability_code: openseo
name: SEO 批量更新
description: |
  批量為多個 WordPress 站點生成並更新 SEO 內容。使用統一的 Composition 確保品牌一致性。
  支持批量生成、批量優化、批量發布。
tags:
  - seo
  - batch
  - multi-site
  - wordpress

kind: user_workflow
interaction_mode:
  - workflow
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

entry_agent_type: coordinator
icon: 📦
---

# SEO 批量更新 - SOP

## 目標

批量為多個 WordPress 站點生成並更新 SEO 內容，使用統一的 Composition 確保品牌一致性。

**核心價值**：
- 批量生成內容（使用統一 Composition）
- 批量 SEO 優化
- 批量發布到多個 WordPress 站點
- 確保品牌一致性（所有站點使用相同的 Lens Composition）

## 執行步驟

### Phase 0: 準備批量任務

**執行順序**：
1. 步驟 0.0: 收集批量任務需求
   - 站點列表
   - 內容類型
   - 目標關鍵詞（可選：每個站點不同）
   - 統一使用一個 Composition

### Phase 1: 批量生成內容

**執行順序**：
1. 步驟 1.0: 融合 Composition（一次）
   - 調用 `fuse_lens_composition`
   - 獲取融合後的統一上下文

2. 步驟 1.1: 批量生成內容
   - 為每個站點生成內容
   - 使用統一的 Composition
   - 支持每個站點不同的關鍵詞

### Phase 2: 批量 SEO 優化

**執行順序**：
1. 步驟 2.0: 批量優化內容
   - 為每個生成的內容進行 SEO 優化
   - 計算 SEO 分數
   - 生成改進建議

### Phase 3: 批量發布（可選）

**執行順序**：
1. 步驟 3.0: 批量發布到 WordPress
   - 為每個站點創建 draft 或直接發布
   - 包含 composition_id 用於追溯
   - 返回每個站點的發布結果

## 輸入參數

- `composition_id` (string, required): 統一的 Lens Composition ID
- `sites` (array, required): 站點列表，每個站點包含：
  - `site_id` (string): WordPress 站點 ID
  - `content_type` (string): 內容類型
  - `target_keywords` (array, optional): 站點特定的關鍵詞
  - `target_audience` (string, optional): 站點特定的受眾
  - `publish_status` (string, optional): 發布狀態（draft, publish）
- `workspace_id` (string, required): Workspace ID

## 輸出結果

- `batch_results` (array): 批量處理結果，每個結果包含：
  - `site_id` (string): 站點 ID
  - `content` (string): 生成的內容
  - `title` (string): SEO 優化的標題
  - `meta_description` (string): SEO 優化的 meta description
  - `seo_score` (object): SEO 分數
  - `wordpress_post_id` (integer, optional): WordPress 文章 ID
  - `wordpress_post_url` (string, optional): WordPress 文章 URL
  - `revision_id` (string, optional): Revision ID
  - `success` (boolean): 是否成功

## 注意事項

1. **統一 Composition**：所有站點使用同一個 Composition，確保品牌一致性
2. **批量處理**：支持並行處理多個站點
3. **錯誤處理**：單個站點失敗不影響其他站點
4. **追溯性**：所有生成的內容都包含 composition_id









