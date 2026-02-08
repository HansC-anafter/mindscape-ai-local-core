---
playbook_code: yogacoach_qa_conversation
version: 1.0.0
locale: zh-TW
name: "對話理解與回答生成"
description: "意圖識別、上下文管理、知識檢索 + LLM 生成（RAG）、降級策略"
capability_code: yogacoach
tags:
  - yoga
  - conversation
  - qa
---

# Playbook: 對話理解與回答生成

**Playbook Code**: `yogacoach_qa_conversation`
**版本**: 1.0.0
**用途**: 意圖識別、上下文管理、知識檢索 + LLM 生成（RAG）、降級策略

---

## 輸入資料

**注意**：`tenant_id`、`user_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "message": {
    "text": "下犬式手腕疼怎麼辦？",
    "context": {
      "user_role": "student",
      "current_session_id": "session-abc123",
      "recent_asanas": ["downward_dog"]
    }
  },
  "conversation_id": "conv-xyz789"
}
```

## 輸出資料

```json
{
  "conversation_id": "conv-xyz789",
  "intent": {
    "primary": "ask_asana_detail",
    "confidence": 0.95
  },
  "response": {
    "text": "手腕疼痛通常是因為...",
    "sources": [
      {
        "entry_id": "entry-abc123",
        "title": "下犬式手腕保護指南",
        "url": "/knowledge/entry-abc123"
      }
    ],
    "suggested_actions": [
      {
        "action": "view_demo_video",
        "label": "查看正確示範",
        "url": "https://youtu.be/xxx"
      }
    ],
    "quality_score": 0.88
  },
  "next_best_action": {
    "action": "continue_chat",
    "reason": "建議繼續對話以獲取更多幫助"
  }
}
```

## 執行步驟

1. **意圖識別**
   - 識別用戶意圖（問姿勢、問課程、要分析、要預約）
   - 計算 confidence score

2. **知識檢索**
   - 調用 F1 (QA Knowledge Base) 檢索相關知識
   - 獲取 top N 相關條目

3. **RAG 生成回答**
   - 使用 LLM 基於檢索結果生成回答
   - 生成 sources 和 suggested_actions

4. **降級處理**
   - 如果檢索失敗或 confidence 過低，使用降級策略
   - 返回通用回答或建議諮詢老師

5. **更新對話上下文**
   - 保存對話記錄
   - 更新 conversation_id

## 能力依賴

- `yogacoach.qa_conversation`: 對話管理
- `yogacoach.qa_knowledge_base`: 知識庫檢索
- `yogacoach.llm_service`: LLM 服務

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 降級策略

- 知識檢索失敗：返回通用回答，建議諮詢老師
- confidence 過低：返回通用回答，建議諮詢老師
- 敏感話題：返回通用回答，建議諮詢老師

## 錯誤處理

- 意圖識別失敗：返回錯誤，記錄日誌
- LLM 生成失敗：使用降級策略，記錄日誌

