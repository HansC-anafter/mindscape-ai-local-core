---
playbook_code: yogacoach_asana_id_suggestion
version: 1.0.0
locale: en
name: "Asana ID Suggestion"
description: "Suggest asana_id based on natural language name or video content"
capability_code: yogacoach
tags:
  - yoga
  - asana
  - translation
---

# Playbook: Asana ID Suggestion

**Playbook Code**: `yogacoach_asana_id_suggestion`
**Version**: 1.0.0
**Purpose**: Suggest asana_id based on natural language name or video content

---

## Input Data

```json
{
  "natural_language_name": "downward dog",
  "teacher_library": {
    "teacher_id": "teacher_001",
    "asana_whitelist": ["downward_dog", "warrior_ii", "triangle_pose"],
    "asana_whitelist_hash": "abc123"
  }
}
```

## Output Data

```json
{
  "suggested_asana_id": "downward_dog",
  "confidence": 0.9,
  "alternatives": [
    {
      "asana_id": "downward_dog_variation",
      "confidence": 0.75
    }
  ],
  "translation_source": "dictionary",
  "from_cache": false
}
```

## Process Flow

1. Check rate limit (API contract layer protection)
2. Check server-side cache (API contract layer protection)
3. If cache hit, return cached result directly
4. If cache miss, execute translation logic:
   - First check dictionary
   - If not found, use LLM or simple transformation
   - Check if in teacher_library's asana_whitelist
5. Store result to cache (if from_cache == false)

## Notes

- **Frontend Throttling**: Frontend should implement debounce (300-500ms)
- **Backend Protection**: Rate limit and server-side cache provide double protection
- **Tool Internal Logic**: Cache-hit judgment is handled inside `asana_translator` tool, no step condition used
- **Same Input Cache**: Same `natural_language_name` + `whitelist_hash` returns cache directly

