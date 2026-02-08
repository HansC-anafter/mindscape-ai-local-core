---
playbook_code: lens_filter
version: 2.0.0
locale: zh-TW
name: "視角過濾"
description: "對搜集到的材料進行視角標記，執行正向過濾（符合你的視角）和反向過濾（刻意看相反的），抽取 Claim/Stance/Evidence 結構。"
capability_code: frontier_research
tags:
  - research
  - filtering
  - perspective
---

# 視角過濾

## 概述
對搜集到的材料進行視角標記，執行正向過濾和反向過濾（contrarian），抽取 Claim/Stance/Evidence 結構並使用 block_id 錨定證據。

## 這個 playbook 解決什麼問題？
一般的資料整理只做「主題相似」，但你要的是：
- **按觀點結構相似/相反**：不只看「都在講 multi-agent」，還要看「他們的立場是什麼」
- **刻意看反方（contrarian）**：避免只看符合自己偏好的資料，造成 confirmation bias
- **可驗證的證據**：每個 claim 都有可追溯的 evidence span（用 block_id 錨定）

## 對應現有系統

| 使用模型 | 用途 |
|----------|------|
| `MindLensInstance` | 讀取個人視角偏好 |
| `LensComposition` | 讀取視角組合配置 |
| `RESEARCH_LENS_DIMENSIONS` | 研究領域專用維度定義 |

## 輸入
- `material_content`: 材料內容（文字）
- `source_url`: 材料來源 URL
- `source_title`: 材料標題
- `lens_composition_id`: 要用的視角組合 ID
- `extract_claims`: 是否抽取 Claim/Stance/Evidence（預設: true）
- `current_intent_lens_tags`: 當前意圖的視角標記（用於 contrarian 判斷）
- `current_intent_stances`: 當前意圖的立場（用於 stance opposite 判斷）

## 視角維度（RESEARCH_LENS_DIMENSIONS）

| 維度 | 選項 | Contrarian Pair | 說明 |
|------|------|-----------------|------|
| `governance_orientation` | control_plane, orchestration, tooling | control_plane ↔ tooling | 治理取向 |
| `evaluation_orientation` | benchmark, human_centered, auditing | benchmark ↔ auditing | 評估取向 |
| `collaboration_model` | human_primary, agent_primary, mixed_initiative | human_primary ↔ agent_primary | 協作模型 |
| `observability` | logging, tracing, provenance, reproducibility | （無對立組） | 可觀測性 |

## 執行邏輯

```python
from datetime import datetime, timedelta
from fuzzywuzzy import fuzz

# =====================
# 1. 預處理內容
# =====================
def preprocess_content(content: str) -> Dict[str, Any]:
    """切成 blocks 並分配 block_id"""
    blocks = {}
    paragraphs = content.split('\n\n')

    p_idx, h_idx, c_idx = 0, 0, 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if para.startswith('#'):
            h_idx += 1
            blocks[f"h_{h_idx:03d}"] = {"type": "heading", "text": para}
        elif para.startswith('```'):
            c_idx += 1
            blocks[f"c_{c_idx:03d}"] = {"type": "code_block", "text": para}
        else:
            p_idx += 1
            blocks[f"p_{p_idx:03d}"] = {"type": "paragraph", "text": para}

    return {"blocks": blocks, "full_text": content}

preprocessed = preprocess_content(material_content)

# =====================
# 2. Contrarian 規則配置
# =====================
CONTRARIAN_RULES = {
    "min_contrarian_per_intent": 2,
    "contrarian_definitions": [
        # ⚠️ stance.position opposite：最重要的 contrarian 規則
        {"field": "stance.position", "condition": "opposite"},
        # lens pair 對立
        {"field": "lens_tags.governance_orientation", "pair": ["control_plane", "tooling"]},
        {"field": "lens_tags.evaluation_orientation", "pair": ["benchmark", "auditing"]},
        {"field": "lens_tags.collaboration_model", "pair": ["human_primary", "agent_primary"]},
    ],
    # ⚠️ 品質門檻（必須套用）
    "quality_thresholds": {
        "min_evidence_count": 1,
        "min_source_credibility": 0.6,
        "max_age_days": 365
    }
}

# =====================
# 3. 視角標記 + Claim 抽取
# =====================
composition = await mind_lens_service.get_composition(lens_composition_id)

extraction_result = await llm.structured_generate(
    prompt=build_extraction_prompt(preprocessed, composition),
    output_schema={
        "lens_tags": {
            "governance_orientation": "enum(control_plane|orchestration|tooling)",
            "evaluation_orientation": "enum(benchmark|human_centered|auditing)",
            "collaboration_model": "enum(human_primary|agent_primary|mixed_initiative)",
            "observability": "enum(logging|tracing|provenance|reproducibility)"
        },
        "lens_scores": {
            "governance_orientation": "float(0-1)",
            "evaluation_orientation": "float(0-1)",
            "collaboration_model": "float(0-1)",
            "observability": "float(0-1)"
        },
        "claims": [{
            "claim_text_zh": "string",
            "claim_text_en": "string",
            "evidence_spans": [{
                "block_id": "string",
                "original_text": "string"
            }],
            "stance": {
                "proposition": "string",
                "position": "enum(support|oppose|neutral)",
                "confidence": "float"
            },
            "evidence_type": "enum(documentation|paper|case_study|opinion|benchmark)"
        }],
        "source_metadata": {
            "credibility_score": "float(0-1)",
            "published_date": "date|null"
        }
    }
)

# =====================
# 4. 驗證 evidence spans
# =====================
def validate_evidence_spans(spans: List[Dict], preprocessed: Dict) -> bool:
    """驗證 evidence spans（exact → fuzzy >= 90%）"""
    blocks = preprocessed["blocks"]
    for span in spans:
        block_id = span["block_id"]
        original_text = span["original_text"]

        # 優先 exact match
        if block_id in blocks:
            if original_text in blocks[block_id]["text"]:
                continue
            # 備援 fuzzy match
            if fuzz.partial_ratio(original_text, blocks[block_id]["text"]) >= 90:
                continue

        # 降級：全文 fuzzy match
        if fuzz.partial_ratio(original_text, preprocessed["full_text"]) >= 90:
            continue

        return False
    return True

validated_claims = [
    claim for claim in extraction_result["claims"]
    if validate_evidence_spans(claim["evidence_spans"], preprocessed)
]

# =====================
# 5. 品質門檻檢查
# =====================
def passes_quality_thresholds(
    claims: List[Dict],
    source_metadata: Dict,
    thresholds: Dict
) -> Tuple[bool, str]:
    """
    檢查是否通過品質門檻

    Returns: (passed, reason)
    """
    # 檢查 1：最少證據數
    min_evidence = thresholds.get("min_evidence_count", 1)
    total_evidence = sum(len(c.get("evidence_spans", [])) for c in claims)
    if total_evidence < min_evidence:
        return False, f"evidence_count={total_evidence} < {min_evidence}"

    # 檢查 2：來源可信度
    min_credibility = thresholds.get("min_source_credibility", 0.6)
    credibility = source_metadata.get("credibility_score", 0.5)
    if credibility < min_credibility:
        return False, f"credibility={credibility} < {min_credibility}"

    # 檢查 3：發布日期
    max_age_days = thresholds.get("max_age_days", 365)
    published_date = source_metadata.get("published_date")
    if published_date:
        try:
            pub_dt = datetime.fromisoformat(published_date)
            age_days = (datetime.now() - pub_dt).days
            if age_days > max_age_days:
                return False, f"age_days={age_days} > {max_age_days}"
        except:
            pass

    return True, "passed"

quality_passed, quality_reason = passes_quality_thresholds(
    validated_claims,
    extraction_result.get("source_metadata", {}),
    CONTRARIAN_RULES["quality_thresholds"]
)

# =====================
# 6. Contrarian 判斷（含 stance opposite）
# =====================
def is_contrarian(
    material_lens_tags: Dict,
    material_claims: List[Dict],
    current_intent_lens_tags: Dict,
    current_intent_stances: Dict
) -> Tuple[bool, str]:
    """
    檢查是否為 contrarian 材料

    規則：
    1. stance.position == opposite（最重要）
    2. lens pair 對立

    Returns: (is_contrarian, reason)
    """
    # ⚠️ 規則 1：stance.position opposite
    for claim in material_claims:
        stance = claim.get("stance", {})
        proposition = stance.get("proposition", "")
        position = stance.get("position", "")

        # 檢查是否與當前意圖的立場相反
        if proposition in current_intent_stances:
            intent_position = current_intent_stances[proposition]
            if (position == "support" and intent_position == "oppose") or \
               (position == "oppose" and intent_position == "support"):
                return True, f"stance.position opposite on '{proposition}': {intent_position} vs {position}"

    # 規則 2：lens pair 對立
    for rule in CONTRARIAN_RULES["contrarian_definitions"]:
        if "pair" not in rule:
            continue

        field_parts = rule["field"].split(".")
        if field_parts[0] != "lens_tags":
            continue

        dim = field_parts[-1]
        material_val = material_lens_tags.get(dim)
        intent_val = current_intent_lens_tags.get(dim)

        if material_val and intent_val:
            pair = rule["pair"]
            if material_val in pair and intent_val in pair:
                if material_val != intent_val:
                    return True, f"{dim}: {intent_val} vs {material_val}"

    return False, None

# 執行 contrarian 判斷
is_contrarian_result, contrarian_reason = is_contrarian(
    material_lens_tags=extraction_result["lens_tags"],
    material_claims=validated_claims,
    current_intent_lens_tags=current_intent_lens_tags or {},
    current_intent_stances=current_intent_stances or {}
)

# ⚠️ 只有通過品質門檻的 contrarian 才算數
if is_contrarian_result and not quality_passed:
    is_contrarian_result = False
    contrarian_reason = f"contrarian but failed quality: {quality_reason}"
```

## 輸出

```yaml
filter_result:
  material_id: "m_001"
  source_url: "https://..."
  source_title: "LangGraph HITL Best Practices"

  # lens_tags 是「維度 → 值」
  lens_tags:
    governance_orientation: "control_plane"
    evaluation_orientation: "human_centered"
    collaboration_model: "mixed_initiative"
    observability: "provenance"

  # lens_scores 是「維度 → 信心度」
  lens_scores:
    governance_orientation: 0.85
    evaluation_orientation: 0.72
    collaboration_model: 0.68
    observability: 0.90

  # 來源元資料（用於品質檢查）
  source_metadata:
    credibility_score: 0.85
    published_date: "2025-12-15"

  # 品質檢查結果
  quality_check:
    passed: true
    reason: "passed"

  filter_status:
    include_match: true
    is_contrarian: false
    contrarian_reason: null

  claims:
    - claim_id: "claim_001"
      claim_text_zh: "LangGraph 的 interrupt_before 是標準的 HITL 原語"
      claim_text_en: "LangGraph's interrupt_before is the standard HITL primitive"

      evidence_spans:
        - block_id: "p_003"
          original_text: "Use interrupt_before to pause the graph before executing a node."
        - block_id: "p_007"
          original_text: "This allows human review of intermediate outputs."

      stance:
        proposition: "HITL should be structurally enforced"
        position: "support"
        confidence: 0.9

      evidence_type: "documentation"

      lens_tags:
        governance_orientation: "control_plane"
        evaluation_orientation: "human_centered"

  preprocessed_content:
    blocks:
      h_001: {type: "heading", text: "# HITL Best Practices"}
      p_001: {type: "paragraph", text: "..."}
      p_003: {type: "paragraph", text: "Use interrupt_before to pause..."}

  raw_content_hash: "sha256:abc123..."
```

## Contrarian 範例（含 stance opposite）

### 範例 1：Lens Pair 對立

```yaml
filter_result:
  material_id: "m_005"

  lens_tags:
    governance_orientation: "tooling"  # ← 與 control_plane 對立
    collaboration_model: "agent_primary"  # ← 與 human_primary 對立

  filter_status:
    is_contrarian: true
    contrarian_reason: "governance_orientation: control_plane vs tooling"
```

### 範例 2：Stance Position Opposite（更重要）

```yaml
filter_result:
  material_id: "m_008"

  claims:
    - stance:
        proposition: "HITL should be structurally enforced"
        position: "oppose"  # ← 意圖立場是 support
        confidence: 0.85

  filter_status:
    is_contrarian: true
    # ⚠️ stance opposite 的 reason 更明確
    contrarian_reason: "stance.position opposite on 'HITL should be structurally enforced': support vs oppose"
```

### 範例 3：Contrarian 但品質不足

```yaml
filter_result:
  material_id: "m_012"

  quality_check:
    passed: false
    reason: "credibility=0.4 < 0.6"

  filter_status:
    is_contrarian: false
    # ⚠️ 即使符合 contrarian 規則，品質不足也不算
    contrarian_reason: "contrarian but failed quality: credibility=0.4 < 0.6"
```

## 依賴

| 服務 | 用途 |
|------|------|
| `LensTaggingService` | 視角標記 + claim 抽取 |
| `MindLensService` | 讀取 LensComposition |
| `fuzzywuzzy` | evidence span 驗證備援 |
