---
playbook_code: yogacoach_asana_id_suggestion
version: 1.0.0
locale: zh-TW
name: "動作名稱建議"
description: "根據中文動作名稱或視頻內容，建議 asana_id"
capability_code: yogacoach
tags:
  - yoga
  - asana
  - translation
---

# Playbook: 動作名稱建議

**Playbook Code**: `yogacoach_asana_id_suggestion`
**版本**: 1.0.0
**用途**: 根據中文動作名稱或視頻內容，建議 asana_id

---

## 輸入資料

```json
{
  "natural_language_name": "下犬式",
  "teacher_library": {
    "teacher_id": "teacher_001",
    "asana_whitelist": ["downward_dog", "warrior_ii", "triangle_pose"],
    "asana_whitelist_hash": "abc123"
  }
}
```

## 輸出資料

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

## 處理流程

1. 檢查 rate limit（API 合約層防呆）
2. 檢查 server-side cache（API 合約層防呆）
3. 如果 cache hit，直接返回快取結果
4. 如果 cache miss，執行翻譯邏輯：
   - 先查字典
   - 如果找不到，使用 LLM 或簡單轉換
   - 檢查是否在 teacher_library 的 asana_whitelist 中
5. 儲存結果到 cache（如果 from_cache == false）

## 注意事項

- **前端節流**：前端應實現 debounce (300-500ms)
- **後端保護**：rate limit 和 server-side cache 提供雙重保護
- **工具內部邏輯**：cache-hit 判斷在 `asana_translator` 工具內部處理，不使用 step condition
- **相同輸入快取**：相同 `natural_language_name` + `whitelist_hash` 直接回快取

