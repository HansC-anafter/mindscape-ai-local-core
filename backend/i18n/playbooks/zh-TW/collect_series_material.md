---
playbook_code: collect_series_material
version: 1.0.0
capability_code: mindscape_book
---
# 收集系列素材

## 概述
根據系列配置的 `tracking_sources.yaml`，收集相關前沿研究並自動對應到各篇文章。

## 輸入
- `series_code`: 系列代碼（例如: human_factors_governance）
- `article_filter`: 只收集特定文章的素材（可選，預設收集全部）
- `date_range`: 日期範圍（可選，預設最近 7 天）

## 工作流程

```
1. 讀取 series/{series_code}/config.yaml
       ↓
2. 讀取 series/{series_code}/tracking_sources.yaml
       ↓
3. 對每個追蹤來源：
   - 調用 frontier_research.track_repo_updates（如果是 GitHub）
   - 調用 frontier_research.research_digest（如果是論文/博客）
   - 調用 frontier_research.translate_article（如果需要翻譯）
       ↓
4. 根據 tracking_sources.yaml 中的 blog_mappings
   自動將素材對應到文章
       ↓
5. 輸出到 materials/{series_code}/{article_code}/ 目錄
```

## 輸出結構

```
materials/human_factors_governance/
├── 01-multi-agent-needs-governance/
│   ├── 2026-01-01_langgraph_0.3.0_release.yaml
│   ├── 2026-01-02_autogen_paper_digest.yaml
│   └── collected_index.yaml
├── 02-dual-pipeline/
│   └── ...
└── collection_summary.yaml
```

## 素材檔案格式

```yaml
# 2026-01-01_langgraph_0.3.0_release.yaml
source_id: langgraph
source_name: LangGraph
collected_at: "2026-01-01T10:00:00Z"
content_type: release
mapped_to_articles:
  - "01-multi-agent-needs-governance"
  - "02-dual-pipeline"

digest:
  title: "LangGraph 0.3.0 Release"
  summary: "新增 hierarchical agent 支援..."
  highlights:
    - "..."
  relevance_to_series: "與我們的 Intent 治理架構相關..."

original_url: "https://github.com/langchain-ai/langgraph/releases/tag/v0.3.0"
```

## 執行步驟

1. **載入配置** - 讀取系列和追蹤來源配置
2. **批次收集** - 對每個來源呼叫對應的 frontier_research playbook
3. **自動對應** - 根據 blog_mappings 分類素材
4. **翻譯處理** - 將英文素材翻譯成中文
5. **儲存輸出** - 按文章分類存放素材檔案

