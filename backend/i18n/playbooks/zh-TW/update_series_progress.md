---
playbook_code: update_series_progress
version: 1.0.0
capability_code: mindscape_book
---
# 更新系列進度

## 概述
檢視系列各文章狀態，更新進度追蹤，產生進度報告。

## 輸入
- `series_code`: 系列代碼

## 工作流程

```
1. 讀取 series/{series_code}/config.yaml
       ↓
2. 檢查每篇文章：
   - 草稿是否存在？
   - 素材收集狀態
   - 字數統計
   - 最後修改時間
       ↓
3. 更新 config.yaml 中的 status
       ↓
4. 產生進度報告
```

## 進度報告格式

```yaml
# progress_report.yaml
series_code: human_factors_governance
generated_at: "2026-01-01T12:00:00Z"

overall:
  total_articles: 10
  completed: 2
  in_progress: 3
  not_started: 5
  completion_percentage: 20%

articles:
  - id: "01"
    code: multi-agent-needs-governance
    title: "為什麼 multi-agent 做到最後會回到人因工程？"
    status: drafting
    word_count: 2500
    materials_count: 8
    last_modified: "2026-01-01"
    next_action: "完成 trade-offs 段落"

  - id: "02"
    code: dual-pipeline
    status: outline
    materials_count: 3
    next_action: "收集更多 pipeline 相關素材"

# 建議的下一步
recommendations:
  - priority: high
    action: "完成第一篇文章初稿"
    reason: "第一篇是系列基石"

  - priority: medium
    action: "為第 3、4 篇收集更多素材"
    reason: "素材不足以開始寫作"
```

## 輸出位置
- 進度報告: `{output_directory}/progress_report.yaml`
- 同時更新: `series/{series_code}/config.yaml` 中各文章的 status

