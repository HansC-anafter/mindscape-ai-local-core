---
playbook_code: draft_article
version: 1.0.0
capability_code: mindscape_book
---
# 起草文章

## 概述
根據系列模板和已收集的素材，起草特定文章。

## 輸入
- `series_code`: 系列代碼
- `article_code`: 文章代碼（例如: multi-agent-needs-governance）
- `draft_mode`: 起草模式（outline | first_draft | revision）

## 工作流程

```
1. 讀取 series/{series_code}/config.yaml
       ↓
2. 找到對應的 article 配置（模板結構）
       ↓
3. 讀取 materials/{series_code}/{article_code}/ 下的素材
       ↓
4. 根據模板的 7 段結構，填充內容：
   - scenario: 真實場景
   - problem: 問題定義
   - diagram: 系統草圖
   - mechanism: 提出的機制
   - difference: 與主流的差異
   - tradeoffs: 取捨
   - next_experiment: 下一步
       ↓
5. 插入相關實作引用（從 implementation_references）
       ↓
6. 輸出到 Obsidian vault
```

## 模板對應

```markdown
# [文章標題]

## 一個真實場景
<!-- 從你的經驗或素材中的案例填充 -->

## 一句話問題定義
> [簡潔的問題陳述]

## 一張系統草圖
<!-- 插入 Mermaid 圖或圖片連結 -->

## 你提出的機制
<!-- 說明你的解法：Lens / Policy Gate / Provenance / Scope -->

### Mindscape AI 實作參考
<!-- 自動插入相關程式碼引用 -->
`execution_context.py` - ExecutionContext 的四層分離...

## 跟主流做法的差異
<!-- 對比 LangGraph / AutoGen / 其他框架 -->

## Trade-offs
<!-- 成本、複雜度、限制 -->

## 下一步實驗
<!-- 你要驗證的假設 -->

---

## 參考素材
<!-- 自動列出使用的素材 -->
- [LangGraph 0.3.0 Release Notes](...)
- [Dango: Mixed-Initiative Data Wrangling](...)
```

## 輸出位置
- 草稿: `{output_directory}/articles/{article_id}-{article_code}.md`
- 例如: `mindscape-book/human-factors-governance/articles/01-multi-agent-needs-governance.md`

