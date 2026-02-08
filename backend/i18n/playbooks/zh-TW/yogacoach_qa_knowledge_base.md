---
playbook_code: yogacoach_qa_knowledge_base
version: 1.0.0
locale: zh-TW
name: "姿勢知識庫管理"
description: "姿勢要點知識庫、向量化檢索、版本控制與多語言支援"
capability_code: yogacoach
tags:
  - yoga
  - knowledge
  - qa
---

# Playbook: 姿勢知識庫管理

**Playbook Code**: `yogacoach_qa_knowledge_base`
**版本**: 1.0.0
**用途**: 姿勢要點知識庫、向量化檢索、版本控制與多語言支援

---

## 輸入資料

**注意**：`tenant_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "action": "query",
  "query": {
    "question": "下犬式手腕疼怎麼辦？",
    "context": "student_asking",
    "max_results": 3
  }
}
```

## 輸出資料

```json
{
  "query_results": [
    {
      "entry_id": "entry-abc123",
      "title": "下犬式手腕保護指南",
      "snippet": "手腕疼痛通常是因為...",
      "relevance_score": 0.92,
      "source": "teacher_id",
      "url": "/knowledge/entry-abc123"
    }
  ],
  "suggested_follow_ups": [
    "如何避免手腕壓力過大？",
    "初學者常見錯誤有哪些？"
  ]
}
```

## 執行步驟

1. **向量化查詢**
   - 將查詢問題轉換為 embedding
   - 使用語義搜索在知識庫中檢索

2. **檢索相關條目**
   - 根據 relevance_score 排序
   - 返回 top N 結果

3. **生成建議後續問題**
   - 基於檢索結果生成相關問題
   - 提供 suggested_follow_ups

## 能力依賴

- `yogacoach.qa_knowledge_base`: 知識庫管理
- `yogacoach.embedding_service`: 向量化服務

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 錯誤處理

- 查詢失敗：返回錯誤，記錄日誌
- 知識庫為空：返回空結果

