# 品牌人格一致性檢查

## 目的

檢查內容與品牌人格定義（MI + BI）的一致性。此 playbook 對於內容產線至關重要，確保所有生成的內容維持品牌一致性。

## 使用時機

- AI 生成內容發布前
- 內容審核工作流程中
- 批量驗證既有內容
- 作為內容產線的品質閘門

## 輸入

- **content**（必填）：要檢查的內容文字
- **brand_identity_ref**（必填）：包含 MI 和 BI 的品牌 CIS 引用
- **content_type**（選填）：內容類型（general、social_post、blog、landing_page、email）
- **check_options**（選填）：
  - `strict_mode`：紅線違規立即判定失敗（預設：true）
  - `threshold`：通過門檻 0-1（預設：0.7）
  - `check_dimensions`：要檢查的維度

## 檢查維度

1. **tone_of_voice**：與品牌語氣定義的匹配度
2. **personality_traits**：品牌人格特質的展現
3. **never_do**：紅線（品牌永遠不做的事）檢查
4. **communication_style**：與 BI 溝通風格的匹配度
5. **worldview**：品牌世界觀的傳達

## 流程

1. **載入品牌身份**：從 brand_identity_ref 取得 MI 和 BI
2. **多維度檢查**：評估各個維度
3. **紅線偵測**：檢查 never_do 違規
4. **分數計算**：計算綜合一致性分數
5. **生成報告**：回傳詳細檢查結果

## 輸出

- **overall_score**：0-1 綜合一致性分數
- **is_aligned**：內容是否通過一致性檢查
- **dimensions**：各維度分數和建議
- **red_line_violations**：紅線違規列表（如有）
- **tone_match**：語氣匹配分數
- **personality_match**：人格匹配分數

## 使用範例

```yaml
inputs:
  content: "我們創新的 AI 解決方案幫助企業..."
  brand_identity_ref:
    artifact_type: "brand_identity"
    artifact_id: "cis_acme_corp"
  content_type: "landing_page"
  check_options:
    strict_mode: true
    threshold: 0.75
```

## 整合點

- **內容產線**：作為內容輸出前的品質閘門
- **analysis.ana_persona_alignment**：跨 pack 內容情報整合
- **ig.content_factory**：IG 內容產線整合

## 相關 Playbook

- `cis_mind_identity`：定義品牌 MI
- `cis_behavior_identity`：定義品牌 BI
- `cis_apply_content`：基於 CIS 生成內容
