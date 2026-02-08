---
playbook_code: yogacoach_qa_knowledge_base
version: 1.0.0
locale: en
name: "Pose Knowledge Base Management"
description: "Pose knowledge base, vectorized retrieval, version control and multi-language support"
capability_code: yogacoach
tags:
  - yoga
  - knowledge
  - qa
---

# Playbook: Pose Knowledge Base Management

**Playbook Code**: `yogacoach_qa_knowledge_base`
**Version**: 1.0.0
**Purpose": Pose knowledge base, vectorized retrieval, version control and multi-language support

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "action": "query",
  "query": {
    "question": "How to handle wrist pain in downward dog?",
    "context": "student_asking",
    "max_results": 3
  }
}
```

## Output Data

```json
{
  "query_results": [
    {
      "entry_id": "entry-abc123",
      "title": "Downward Dog Wrist Protection Guide",
      "snippet": "Wrist pain is usually caused by...",
      "relevance_score": 0.92,
      "source": "teacher_id",
      "url": "/knowledge/entry-abc123"
    }
  ],
  "suggested_follow_ups": [
    "How to avoid excessive wrist pressure?",
    "What are common beginner mistakes?"
  ]
}
```

## Execution Steps

1. **Vectorize Query"
   - Convert query question to embedding
   - Use semantic search to retrieve from knowledge base

2. **Retrieve Relevant Entries"
   - Sort by relevance_score
   - Return top N results

3. **Generate Suggested Follow-ups"
   - Generate related questions based on retrieval results
   - Provide suggested_follow_ups

## Capability Dependencies

- `yogacoach.qa_knowledge_base": Knowledge base management
- `yogacoach.embedding_service": Vectorization service

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Error Handling

- Query failed: Return error, log details
- Knowledge base empty: Return empty results

