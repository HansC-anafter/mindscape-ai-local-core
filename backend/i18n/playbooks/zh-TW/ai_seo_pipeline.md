---
playbook_code: ai_seo_pipeline
version: 1.0.0
capability_code: openseo
name: AI SEO 完整優化流程
description: 端到端的 AI SEO 優化流程：語義優化 → 結構化數據 → E-E-A-T → 引擎特定優化 → 落盤。根據目標引擎自動選擇優化策略，支持單篇或多篇批次處理。
tags:
  - ai-seo
  - optimization
  - pipeline
  - semantic-search
  - structured-data
  - eeat

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - openseo.read_obsidian_vault
  - openseo.generate_claims_to_sources
  - openseo.generate_ai_seo_scorecard
  - openseo.save_to_markdown
  - core_llm.generate
  - core_llm.structured_extract

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: consultant
icon: 🤖
---

# AI SEO 完整優化流程

## 目標

提供端到端的 AI 搜尋引擎優化流程，自動根據目標引擎選擇優化策略，生成符合 AI SEO 通用契約的優化內容。

## 執行流程

### Phase 1: 解析內容來源

根據 `content_source` 格式自動識別並載入內容：
- `obsidian://vault/path/to/note.md` → 讀取 Obsidian vault
- `workspace://workspace_id/content_id` → 讀取 Mindscape workspace 內容
- `url://https://example.com/article` → 抓取網頁內容
- `pasted_text` → 使用直接貼上的文字

### Phase 2: 語義優化（semantic_optimization）

除非在 `skip_steps` 中指定跳過：
- 提取關鍵字和實體
- 建立 topic clusters
- 優化語義搜尋分數
- 改善內容的語義理解度

### Phase 3: 結構化數據優化（structured_data_optimization）

除非在 `skip_steps` 中指定跳過：
- 生成 Schema.org JSON-LD 結構化數據
- 根據 `content_type` 選擇適當的 schema（Article, FAQ, HowTo, Product 等）
- 確保結構化數據符合目標引擎要求

### Phase 4: E-E-A-T 優化（eeat_optimization）

除非在 `skip_steps` 中指定跳過：
- 驗證並優化作者資訊（`author_profile_id`）
- 驗證並優化品牌實體（`brand_entity_id`）
- 提升內容的專業性、權威性和可信度

### Phase 5: 引擎特定優化（根據 target_engines 自動選擇）

#### SGE 優化（sge_optimization）
- 當 `target_engines` 包含 `"sge"` 時執行
- 優化對話式結構
- 生成步驟式內容
- 強化 FAQ 和 HowTo schema

#### Perplexity 優化（perplexity_optimization）
- 當 `target_engines` 包含 `"perplexity"` 時執行
- 生成 `claims_to_sources` 映射（當 `citation_mode != "none"`）
- 強化引用和事實性
- 確保來源可追溯

#### Bing Chat / You.com 優化
- 當 `target_engines` 包含 `"bing_chat"` 或 `"you_com"` 時
- 目前 fallback 到 generic（只跑 semantic/structured/eeat）
- 未來可擴展專屬優化步驟

### Phase 6: 合併優化結果（merge_optimizations）

合併所有優化步驟的輸出：
- **content_md**：後跑的 playbook 覆蓋前者
- **schema_jsonld**：用 @type 去重後 union
- **claims_to_sources**：以 claim_id 合併；同 claim_id 的 sources 去重、保留最高 confidence

### Phase 7: 生成評分卡（generate_scorecard）

生成完整的 AI SEO 評分卡：
- semantic_score
- structured_data_score
- eeat_score
- citation_coverage（當 `citation_mode != "none"`）
- overall_score（pipeline 最終輸出必回）

### Phase 8: 準備元數據（prepare_metadata）

準備完整的 metadata 物件：
- continuity_graph（從 Obsidian 提取的 wikilink 關係）
- seo_scores（SEO 分數歷史）
- optimization_history（優化歷史）
- version（版本號）
- trace_id（追蹤 ID）

### Phase 9: 保存到 Markdown（save_to_markdown）

根據 `content_status` 保存到對應目錄：
- `draft` → `openseo/generated/draft/`
- `in_review` → `openseo/generated/in_review/`
- `published` → `openseo/generated/published/`
- `archived` → `openseo/generated/archived/`

同時保存 metadata 到 `openseo/metadata/` 目錄。

## 批次處理模式

當 `run_mode=batch` 時：
- 處理多個 `content_source`
- 為每個項目生成獨立的輸出
- 返回批次摘要（`batch_summary`）包含：
  - total, success, failed, skipped
  - avg_score
  - errors[]

## 輸出格式

符合 AI SEO 通用契約：
- `content_md`：優化後的 Markdown 內容（包含 frontmatter）
- `title`：文章標題
- `meta_description`：Meta 描述
- `claims_to_sources`：主張到來源的映射（當 `citation_mode != "none"`）
- `schema_jsonld`：Schema.org JSON-LD 結構化數據
- `scorecard`：SEO 評分卡
- `metadata`：完整元數據（當 `save_metadata=true`）
- `trace_id`：追蹤 ID
- `result_status`：處理結果狀態（success/error/skipped）

## Mindscape 事件治理對齊

輸出標記：
- `is_artifact=true`：可再利用、可比較的穩定產物
- `has_structured_output=true`：包含結構化輸出
- `should_embed=true`：只有 `content_status=published` 才為 true
- `is_final=true`：`content_status=published` 或 `archived` 時為 true

## 使用範例

### 單篇處理

```yaml
content_source: "obsidian://vault/path/to/note.md"
content_type: "article"
target_engines: ["sge", "perplexity"]
citation_mode: "strict"
content_status: "draft"
output_path: "openseo/generated"
```

### 批次處理

```yaml
run_mode: "batch"
content_sources:
  - "obsidian://vault/path/to/note1.md"
  - "obsidian://vault/path/to/note2.md"
content_type: "article"
target_engines: ["generic"]
citation_mode: "light"
content_status: "draft"
```

## 注意事項

1. **內容來源格式**：必須符合 `obsidian://`, `workspace://`, `url://`, 或 `pasted_text` 格式
2. **跳過步驟**：使用 `skip_steps` 可以跳過特定優化步驟（用於調試或部分優化）
3. **引用模式**：`citation_mode=strict` 時，`claims_to_sources` 必須包含 `anchor` 資訊
4. **批次處理**：批次模式下，每個項目都有獨立的 `trace_id` 和 `result_status`

