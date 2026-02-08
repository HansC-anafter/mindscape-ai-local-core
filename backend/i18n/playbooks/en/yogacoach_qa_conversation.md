---
playbook_code: yogacoach_qa_conversation
version: 1.0.0
locale: en
name: "Conversation Understanding & Response Generation"
description: "Intent recognition, context management, knowledge retrieval + LLM generation (RAG), fallback strategy"
capability_code: yogacoach
tags:
  - yoga
  - conversation
  - qa
---

# Playbook: Conversation Understanding & Response Generation

**Playbook Code**: `yogacoach_qa_conversation`
**Version**: 1.0.0
**Purpose": Intent recognition, context management, knowledge retrieval + LLM generation (RAG), fallback strategy

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `user_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "message": {
    "text": "How to handle wrist pain in downward dog?",
    "context": {
      "user_role": "student",
      "current_session_id": "session-abc123",
      "recent_asanas": ["downward_dog"]
    }
  },
  "conversation_id": "conv-xyz789"
}
```

## Output Data

```json
{
  "conversation_id": "conv-xyz789",
  "intent": {
    "primary": "ask_asana_detail",
    "confidence": 0.95
  },
  "response": {
    "text": "Wrist pain is usually caused by...",
    "sources": [
      {
        "entry_id": "entry-abc123",
        "title": "Downward Dog Wrist Protection Guide",
        "url": "/knowledge/entry-abc123"
      }
    ],
    "suggested_actions": [
      {
        "action": "view_demo_video",
        "label": "View Correct Demo",
        "url": "https://youtu.be/xxx"
      }
    ],
    "quality_score": 0.88
  },
  "next_best_action": {
    "action": "continue_chat",
    "reason": "Suggest continuing conversation for more help"
  }
}
```

## Execution Steps

1. **Intent Recognition"
   - Identify user intent (ask pose, ask course, request analysis, book class)
   - Calculate confidence score

2. **Knowledge Retrieval"
   - Call F1 (QA Knowledge Base) to retrieve relevant knowledge
   - Get top N relevant entries

3. **RAG Response Generation"
   - Use LLM to generate response based on retrieval results
   - Generate sources and suggested_actions

4. **Fallback Handling"
   - If retrieval fails or confidence too low, use fallback strategy
   - Return generic response or suggest consulting teacher

5. **Update Conversation Context"
   - Save conversation history
   - Update conversation_id

## Capability Dependencies

- `yogacoach.qa_conversation": Conversation management
- `yogacoach.qa_knowledge_base": Knowledge base retrieval
- `yogacoach.llm_service": LLM service

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Fallback Strategy

- Knowledge retrieval failed: Return generic response, suggest consulting teacher
- Confidence too low: Return generic response, suggest consulting teacher
- Sensitive topic: Return generic response, suggest consulting teacher

## Error Handling

- Intent recognition failed: Return error, log details
- LLM generation failed: Use fallback strategy, log details

