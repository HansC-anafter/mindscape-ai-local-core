---
playbook_code: brand_monthly_review
version: 1.0.0
name: 品牌月度檢視
description: 定期檢視品牌產出覆蓋率、一致性，提出改進建議
tags:
  - brand
  - review
  - analytics
  - consistency
  - improvement

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file
  - core_llm.analyze
  - core_llm.structured_extract
  - core_export.markdown
  - core_export.json
  - artifact.list
  - execution.list
  - cloud_capability.call

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: analyst
icon: 📊
capability_code: brand_identity
---

# 📊 品牌月度檢視

> **定期檢視品牌產出，確保一致性，發現改進機會。**

## 目標

每月檢視品牌的：

- **產出覆蓋率**：哪些故事線有內容，哪些不足
- **一致性檢查**：內容是否符合品牌 MI/Persona
- **改進建議**：哪些地方可以優化
- **趨勢分析**：產出趨勢和模式

## 責任分配

| 步驟 | 責任 | AI 角色 | 人類角色 |
|------|------|---------|----------|
| 資料收集 | 🟢 AI自動 | 收集過去一個月的 Executions 和 Artifacts | - |
| 覆蓋率分析 | 🟢 AI自動 | 計算各故事線覆蓋率 | 品牌方檢視 |
| 一致性檢查 | 🟡 AI提案 | 檢查內容與品牌 MI 的一致性 | 品牌方確認 |
| 改進建議 | 🟡 AI提案 | 提出優化建議 | 品牌方決策 |
| 趨勢分析 | 🟢 AI自動 | 分析產出趨勢 | 品牌方檢視 |

---

## Step 1: 設定檢視參數

首先，我需要確認檢視的時間範圍和範圍。

### 時間範圍選擇

```decision_card
card_id: dc_time_range
type: selection
title: "選擇檢視時間範圍"
question: "要檢視哪個時間段的產出？"
options:
  - "過去 30 天（月度檢視）"
  - "過去 90 天（季度檢視）"
  - "過去 180 天（半年檢視）"
  - "自品牌建立以來（全部）"
default: "過去 30 天"
```

### 檢視範圍確認

```decision_card
card_id: dc_review_scope
type: multi_selection
title: "選擇檢視範圍"
question: "要檢視哪些方面？"
options:
  - "故事線覆蓋率"
  - "內容一致性"
  - "平台分布"
  - "產出趨勢"
  - "改進建議"
default: ["故事線覆蓋率", "內容一致性", "改進建議"]
```

---

## Step 2: 收集過去一個月的資料 🟢

我會收集指定時間範圍內的所有相關資料。

### 收集 Executions

```tool
list_executions
workspace_id: {workspace_id}
time_range_days: {選定的天數}
include_storyline_tags: true
include_playbook_code: true
limit: 200
```

### 收集 Artifacts

```tool
list_artifacts
workspace_id: {workspace_id}
kind: brand_*
created_after: {時間範圍開始日期}
limit: 500
```

同時收集所有內容類型的 Artifacts：

```tool
list_artifacts
workspace_id: {workspace_id}
metadata_filter:
  platform: [website, instagram, facebook, course, ebook, blog]
created_after: {時間範圍開始日期}
limit: 500
```

### 讀取品牌 MI 和 Persona

```tool
list_artifacts
workspace_id: {workspace_id}
kind: brand_mi
limit: 1
```

```tool
list_artifacts
workspace_id: {workspace_id}
kind: brand_persona
limit: 10
```

### 調用 Cloud Capability：Storyline Coverage

```tool
call_cloud_capability
capability: brand_identity/storyline_coverage
workspace_id: {workspace_id}
time_range_days: {選定的天數}
include_execution_details: true
```

---

## Step 3: 故事線覆蓋率分析 🟢

基於收集的資料，我會分析各故事線的覆蓋率。

### 數據處理

我會：

1. 從 Executions 中提取所有 `storyline_tags`
2. 統計每個故事線的 Execution 數量
3. 統計每個故事線的 Artifact 數量
4. 計算覆蓋率百分比
5. 識別覆蓋不足的故事線

### AI 產出：覆蓋率報告

```yaml
storyline_coverage_report:
  time_range: "{時間範圍}"
  total_storylines: 5
  total_executions: 15
  total_artifacts: 42

  storylines:
    - storyline_tag: "story-arc-1"
      execution_count: 8
      artifact_count: 24
      coverage_percentage: 53.3%
      platforms: ["website", "instagram", "course", "ebook"]
      status: "well_covered"
      last_activity: "2025-12-10"
      trend: "increasing"  # increasing, stable, decreasing

    - storyline_tag: "rebranding"
      execution_count: 3
      artifact_count: 8
      coverage_percentage: 20.0%
      platforms: ["website", "blog"]
      status: "under_covered"
      last_activity: "2025-11-15"
      trend: "stable"
      gap_analysis:
        - "缺少社群媒體內容"
        - "缺少課程內容"

    - storyline_tag: "product_launch"
      execution_count: 0
      artifact_count: 0
      coverage_percentage: 0.0%
      platforms: []
      status: "missing"
      last_activity: null
      trend: "none"
      recommendation: "建議啟動此故事線的內容生成"

    - storyline_tag: "customer_success"
      execution_count: 2
      artifact_count: 5
      coverage_percentage: 13.3%
      platforms: ["blog"]
      status: "under_covered"
      last_activity: "2025-11-20"
      trend: "decreasing"
      gap_analysis:
        - "僅有部落格內容，缺少其他平台"
        - "內容更新頻率低"

    - storyline_tag: "thought_leadership"
      execution_count: 2
      artifact_count: 5
      coverage_percentage: 13.3%
      platforms: ["blog", "linkedin"]
      status: "under_covered"
      last_activity: "2025-12-05"
      trend: "increasing"
      gap_analysis:
        - "可以擴展到 podcast"
        - "可以生成電子書章節"

  summary:
    well_covered_count: 1
    under_covered_count: 3
    missing_count: 1
    average_coverage: 20.0%
    recommended_focus: ["product_launch", "rebranding", "customer_success"]
```

### 視覺化報告

我會生成覆蓋率視覺化報告，標示：

- ✅ **覆蓋良好的故事線**（覆蓋率 > 40%）
- ⚠️ **覆蓋不足的故事線**（覆蓋率 10-40%）
- ❌ **完全缺失的故事線**（覆蓋率 < 10% 或為 0）

### 決策卡：覆蓋率檢視

```decision_card
card_id: dc_coverage_review
type: review
title: "故事線覆蓋率檢視"
question: "請檢視各故事線的覆蓋情況"
items:
  - item: "story-arc-1"
    status: "well_covered"
    coverage: "53.3%"
    action: "維持現狀或擴展"
  - item: "rebranding"
    status: "under_covered"
    coverage: "20.0%"
    action: "需要補充內容"
  - item: "product_launch"
    status: "missing"
    coverage: "0.0%"
    action: "建議啟動"
```

---

## Step 4: 平台分布分析 🟢

分析內容在不同平台的分布情況。

### AI 產出：平台分布報告

```yaml
platform_distribution:
  total_artifacts: 42

  platforms:
    - platform: website
      count: 8
      percentage: 19.0%
      storylines: ["story-arc-1", "rebranding"]

    - platform: instagram
      count: 15
      percentage: 35.7%
      storylines: ["story-arc-1", "thought_leadership"]

    - platform: blog
      count: 10
      percentage: 23.8%
      storylines: ["rebranding", "customer_success", "thought_leadership"]

    - platform: course
      count: 5
      percentage: 11.9%
      storylines: ["story-arc-1"]

    - platform: ebook
      count: 4
      percentage: 9.5%
      storylines: ["story-arc-1"]

  insights:
    - "Instagram 內容最多，但主要集中在 story-arc-1"
    - "Course 和 Ebook 內容較少，可以擴展"
    - "缺少 Podcast 和 Email 內容"
```

---

## Step 5: 一致性檢查 🟡

我會檢查所有產出是否與品牌 MI（Mind Identity）一致。

### 讀取品牌 MI 詳細內容

```tool
read_artifact
artifact_id: {brand_mi_artifact_id}
```

提取關鍵要素：

- 品牌世界觀（Worldview）
- 價值主張（Value Proposition）
- 品牌紅線（Redlines）
- 品牌人格（Personality）
- 語氣指南（Tone of Voice）

### AI 分析：一致性檢查

我會對每個 Artifact 進行一致性檢查：

```yaml
consistency_check_report:
  total_artifacts_checked: 42
  time_range: "{時間範圍}"

  overall_score: 0.85
  status: "good"

  results:
    - artifact_id: "art_001"
      title: "網站首頁 - story-arc-1"
      platform: website
      storyline_tag: "story-arc-1"
      consistency_score: 0.95
      worldview_alignment: 0.98
      tone_alignment: 0.92
      value_proposition_alignment: 0.96
      redline_compliance: 1.0
      issues: []
      status: "consistent"
      recommendation: "無需修改"

    - artifact_id: "art_002"
      title: "IG 貼文 #1 - story-arc-1"
      platform: instagram
      storyline_tag: "story-arc-1"
      consistency_score: 0.72
      worldview_alignment: 0.85
      tone_alignment: 0.65  # 語氣過於正式
      value_proposition_alignment: 0.75
      redline_compliance: 1.0
      issues:
        - type: "tone_mismatch"
          severity: "medium"
          description: "語氣過於正式，不符合品牌人格（應更友善）"
          suggestion: "調整為更友善、親切的語氣"
        - type: "value_proposition_weak"
          severity: "low"
          description: "缺少品牌價值主張的明確體現"
          suggestion: "在文案中更明確地體現品牌價值主張"
      status: "needs_review"
      recommendation: "建議修改"

    - artifact_id: "art_003"
      title: "部落格文章 - rebranding"
      platform: blog
      storyline_tag: "rebranding"
      consistency_score: 0.88
      worldview_alignment: 0.90
      tone_alignment: 0.85
      value_proposition_alignment: 0.90
      redline_compliance: 1.0
      issues: []
      status: "consistent"
      recommendation: "無需修改"

  summary:
    consistent_count: 35
    needs_review_count: 7
    average_score: 0.85
    critical_issues: 0
    medium_issues: 5
    low_issues: 2

  common_issues:
    - issue: "語氣不一致"
      count: 5
      severity: "medium"
      affected_storylines: ["story-arc-1", "thought_leadership"]
    - issue: "價值主張體現不足"
      count: 3
      severity: "low"
      affected_storylines: ["story-arc-1", "rebranding"]
```

### 決策卡：一致性問題審核

```decision_card
card_id: dc_consistency_review
type: review
title: "一致性檢查結果"
question: "以下內容與品牌 MI 不一致，需要修正嗎？"
items: [不一致的 artifacts 列表，包含問題描述和建議]
actions:
  - approve: "接受，不修改"
  - revise: "需要修改"
  - schedule_revision: "排程修改"
```

---

## Step 6: 產出趨勢分析 🟢

分析過去一段時間的產出趨勢。

### AI 產出：趨勢報告

```yaml
trend_analysis:
  time_range: "{時間範圍}"

  execution_trend:
    total_executions: 15
    monthly_breakdown:
      - month: "2025-10"
        count: 3
        storylines: ["story-arc-1", "rebranding"]
      - month: "2025-11"
        count: 5
        storylines: ["story-arc-1", "rebranding", "customer_success"]
      - month: "2025-12"
        count: 7
        storylines: ["story-arc-1", "thought_leadership"]
    trend: "increasing"
    growth_rate: "133%"

  artifact_trend:
    total_artifacts: 42
    monthly_breakdown:
      - month: "2025-10"
        count: 8
      - month: "2025-11"
        count: 15
      - month: "2025-12"
        count: 19
    trend: "increasing"
    growth_rate: "138%"

  storyline_trend:
    storylines:
      - storyline_tag: "story-arc-1"
        trend: "increasing"
        monthly_activity: [2, 3, 3]
      - storyline_tag: "rebranding"
        trend: "stable"
        monthly_activity: [1, 2, 0]
      - storyline_tag: "thought_leadership"
        trend: "increasing"
        monthly_activity: [0, 0, 2]

  platform_trend:
    platforms:
      - platform: instagram
        trend: "increasing"
        monthly_activity: [3, 5, 7]
      - platform: blog
        trend: "stable"
        monthly_activity: [2, 4, 4]
      - platform: course
        trend: "decreasing"
        monthly_activity: [2, 2, 1]

  insights:
    - "整體產出呈上升趨勢"
    - "story-arc-1 是最活躍的故事線"
    - "Instagram 內容增長最快"
    - "Course 內容需要加強"
```

---

## Step 7: 改進建議 🟡

基於覆蓋率分析、一致性檢查和趨勢分析，我會提出改進建議。

### AI 建議：改進計劃

```yaml
improvement_suggestions:
  coverage_improvements:
    - suggestion_id: "imp_001"
      type: "coverage"
      priority: "critical"
      title: "啟動 product_launch 故事線"
      description: "product_launch 故事線完全缺失，建議立即啟動相關內容生成"
      action: "執行 cross_channel_story playbook，選擇 product_launch 故事線"
      expected_impact: "高"
      estimated_effort: "中等"

    - suggestion_id: "imp_002"
      type: "coverage"
      priority: "high"
      title: "補充 rebranding 故事線內容"
      description: "rebranding 故事線覆蓋不足（20%），缺少社群媒體和課程內容"
      action: "為 rebranding 故事線生成 Instagram 和 Course 內容"
      expected_impact: "中高"
      estimated_effort: "低"

    - suggestion_id: "imp_003"
      type: "coverage"
      priority: "medium"
      title: "擴展 story-arc-1 到 Podcast 平台"
      description: "story-arc-1 覆蓋良好，可以考慮擴展到 podcast 平台"
      action: "執行 cross_channel_story playbook，為 story-arc-1 生成 podcast 腳本"
      expected_impact: "中"
      estimated_effort: "中等"

  consistency_improvements:
    - suggestion_id: "imp_004"
      type: "consistency"
      priority: "medium"
      title: "統一語氣風格"
      description: "5 個 artifacts 語氣不一致，建議統一為友善風格"
      action: "修改相關 artifacts，調整語氣"
      affected_artifacts: ["art_002", "art_005", "art_008", "art_012", "art_015"]
      expected_impact: "中"
      estimated_effort: "低"

    - suggestion_id: "imp_005"
      type: "consistency"
      priority: "low"
      title: "加強價值主張體現"
      description: "3 個 artifacts 缺少品牌價值主張，建議補充"
      action: "在相關內容中更明確地體現品牌價值主張"
      affected_artifacts: ["art_002", "art_007", "art_011"]
      expected_impact: "低"
      estimated_effort: "低"

  platform_diversification:
    - suggestion_id: "imp_006"
      type: "platform"
      priority: "medium"
      title: "增加 Podcast 內容"
      description: "目前沒有 Podcast 內容，建議為主要故事線生成 Podcast 腳本"
      action: "執行 cross_channel_story playbook，選擇 podcast 平台"
      expected_impact: "中"
      estimated_effort: "中等"

    - suggestion_id: "imp_007"
      type: "platform"
      priority: "low"
      title: "增加 Email 行銷內容"
      description: "目前沒有 Email 內容，可以為重要故事線生成 Email 行銷內容"
      action: "執行 cross_channel_story playbook，選擇 email 平台"
      expected_impact: "低"
      estimated_effort: "低"

  trend_based_suggestions:
    - suggestion_id: "imp_008"
      type: "trend"
      priority: "medium"
      title: "加強 Course 內容產出"
      description: "Course 內容呈下降趨勢，建議增加產出"
      action: "為活躍的故事線生成更多 Course 內容"
      expected_impact: "中"
      estimated_effort: "中等"
```

### 決策卡：改進計劃

```decision_card
card_id: dc_improvements
type: planning
title: "下個月改進計劃"
question: "要優先處理哪些改進建議？"
description: "可以多選，建議優先處理 critical 和 high priority 的項目"
options: [以上建議列表，按 priority 排序]
min_selections: 1
actions:
  - create_tasks: "創建改進任務"
  - schedule: "排程執行"
  - defer: "延後處理"
```

---

## Step 8: 生成月度檢視報告

我會生成完整的月度檢視報告。

### 創建報告 Artifact

```tool
create_artifact
workspace_id: {workspace_id}
playbook_code: brand_monthly_review
artifact_type: markdown
title: "品牌月度檢視報告 - {YYYY-MM}"
summary: "品牌產出覆蓋率、一致性和改進建議報告"
content: {完整的檢視報告內容}
metadata:
  kind: report
  report_type: monthly_review
  time_range: "{時間範圍}"
  generated_at: "{生成時間}"
primary_action_type: view
```

### 報告內容結構

報告包含：

1. **執行摘要**：整體狀況概述
2. **故事線覆蓋率**：詳細覆蓋率分析
3. **平台分布**：各平台內容分布
4. **一致性檢查**：品牌 MI 對齊情況
5. **趨勢分析**：產出趨勢和模式
6. **改進建議**：優先級排序的改進計劃
7. **附錄**：詳細數據和圖表

---

## 產出物

完成本階段後，會生成以下文件：

```text
reports/
├── monthly_review_{YYYY-MM}.md           # 月度檢視報告（Markdown）
├── monthly_review_{YYYY-MM}.json         # 月度檢視數據（JSON）
├── storyline_coverage.json                # 覆蓋率數據
├── consistency_check.json                 # 一致性檢查結果
├── trend_analysis.json                    # 趨勢分析數據
└── improvement_plan.md                    # 改進計劃
```

所有報告都會保存為 Artifacts，方便後續查閱和對比。

---

## 品質檢查清單

在完成前，我會檢查：

- [ ] 所有數據收集完整
- [ ] 覆蓋率計算正確
- [ ] 一致性檢查涵蓋所有相關 Artifacts
- [ ] 改進建議優先級合理
- [ ] 報告格式清晰易讀
- [ ] 所有 Artifacts 正確創建

---

## 進入下一階段

完成月度檢視後，可以：

1. **執行改進計劃**：根據建議啟動新的內容生成流程
2. **修正一致性問題**：修改不符合品牌 MI 的內容
3. **補充覆蓋不足的故事線**：為缺失或不足的故事線生成內容
4. **設定下個月目標**：基於檢視結果設定下個月的產出目標
5. **對比歷史報告**：查看過去的檢視報告，追蹤改進進度

---

## 注意事項

1. **時間範圍選擇**：建議從月度檢視開始，逐步擴展到季度和半年檢視
2. **品牌 MI 必須存在**：如果沒有品牌 MI，一致性檢查會受限
3. **數據完整性**：確保 Executions 和 Artifacts 都正確標記 `storyline_tags`
4. **定期執行**：建議每月固定時間執行，建立檢視習慣
5. **行動導向**：檢視報告的目的是發現問題並採取行動，不要只停留在分析
