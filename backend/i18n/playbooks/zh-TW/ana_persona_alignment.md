# 人格一致性檢查

## 目的

檢查內容是否與 brand_identity pack 中定義的品牌人格一致。此 playbook 驗證產出的內容是否保持與既定人格準則的一致性。

## 使用時機

- 生成新內容批次後
- 內容品質審核期間
- 新內容創作者入職時
- 發布重要內容前

## 輸入

- **content_refs**（必填）：要檢查一致性的內容引用陣列
  - 應包含視覺特徵、主題、語調指標
- **persona_ref**（必填）：來自 brand_identity pack 的品牌人格引用
  - 可包含語調設定、詞彙提示、視覺識別準則

## 流程

1. **聚合內容特徵**：分析提供內容的視覺和內容模式
2. **與人格比較**：跨語調、視覺和主題維度檢查一致性
3. **生成報告**：建立包含具體建議的一致性報告

## 輸出

- **alignment_results**：詳細的一致性分析
  - 按維度的一致性分數
  - 具體的不一致範例
  - 改進建議

## 使用範例

```yaml
inputs:
  content_refs:
    - source: "recent_posts"
      features:
        visual_tokens: ["gradient", "minimalist"]
        topics: ["productivity", "ai"]
        tone_indicators: {"formality": 0.4, "warmth": 0.7}
  persona_ref:
    persona_id: "mindscape_voice"
    tone:
      formality: 0.3
      warmth: 0.8
      energy: 0.6
    vocabulary:
      preferred: ["empower", "create", "discover"]
      avoid: ["simply", "just"]
    visual_identity:
      visual_tokens: ["gradient", "soft_shadow", "rounded"]
```

## 相關 Playbook

- `bi_create_persona`：定義或更新品牌人格
- `bi_validate_content_against_persona`：詳細的逐內容驗證
- `content_drafting`：創建符合人格的內容
