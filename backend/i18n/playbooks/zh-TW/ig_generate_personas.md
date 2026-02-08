# AI 畫像生成

## 概述

整合帳號資料、貼文內容和網絡關係，使用 LLM 生成 AI 驅動的用戶畫像。

## 功能

- ✅ 彙整 ig_account_profiles, ig_posts, ig_follow_edges 資料
- ✅ LLM 驅動的畫像合成
- ✅ 結構化輸出：特質、主題、人口統計
- ✅ 品牌合作評分

## 輸入參數

| 參數 | 類型 | 必需 | 說明 |
| --- | --- | --- | --- |
| `workspace_id` | string | 是 | 工作區 ID |
| `target_handles` | array | 是 | 目標帳號 |
| `model` | string | 否 | LLM 模型（預設：gpt-4o-mini） |
| `batch_size` | integer | 否 | 批次大小（預設：10） |

## 3 步驟 LLM 流程

1. **collect_data** - 從所有資料表彙整資料
2. **generate_personas** - LLM 生成結構化畫像
3. **persist_personas** - 寫入 ig_generated_personas

## 畫像輸出格式

```json
{
  "persona_summary": "2-3 句摘要",
  "key_traits": ["特質1", "特質2"],
  "content_themes": ["主題1", "主題2"],
  "demographics": {
    "age_range": "25-34",
    "gender": "female",
    "location_type": "urban"
  },
  "collaboration_potential": 0.8,
  "recommended_approach": "產品試用..."
}
```

## 前置條件

- Phase 1: 已執行 `ig_tag_profiles`
- Phase 2: 已執行 `ig_analyze_content`（建議但非必需）

## 成本控制

- 可配置批次大小
- 結果快取（cache_key）
