---
playbook_code: disagreement_brief
version: 2.0.0
locale: zh-TW
name: "分歧摘要"
description: "比較多份材料，找出核心分歧點。這是「可寫作的資產」：每週累積 3-5 個分歧摘要，一個月就是一篇很硬的文章。"
capability_code: frontier_research
tags:
  - research
  - analysis
  - disagreement
---

# 分歧摘要

## 概述
比較多份材料，按 proposition 分組找出核心分歧點，分析 stance 分佈，產出「可寫作的資產」。

## 這個 playbook 解決什麼問題？
- 你有一堆材料，知道「他們在講類似的事」，但不知道「他們的分歧在哪裡」
- 你想寫有深度的文章，不只是整理資料，而是整理「立場空間」
- 每週累積 3-5 個分歧摘要，一個月就是一篇很硬的文章

## 對應現有系統

| 使用模型 | 用途 |
|----------|------|
| `Artifact (disagreement_brief)` | 儲存分歧摘要 |
| `Claim` / `Stance` | 從 lens_filter 輸出讀取 |
| `EvidenceSpan` | 引用 block_id 錨定的證據 |

## 輸入
- `materials`: 要比較的材料列表（已通過 lens_filter，包含 claims/lens_tags）
- `focus_topic`: 聚焦的主題（可選）
- `intent_id`: 關聯的意圖 ID（可選）

## 執行邏輯

```python
# 1. 收集所有 claims 並標記來源
all_claims = []
for material in materials:
    for claim in material.get("claims", []):
        claim["material_id"] = material["material_id"]
        claim["source_title"] = material.get("source_title", "")
        claim["source_url"] = material.get("source_url", "")
        all_claims.append(claim)

# 2. 按 proposition 分組（用語意相似度）
async def group_by_proposition(claims):
    """將語意相似的 claim 分到同一個 proposition 下"""
    if len(claims) < 2:
        return [{"proposition": claims[0]["stance"]["proposition"], "claims": claims}]

    # 計算 embeddings
    texts = [c["claim_text_zh"] for c in claims]
    vectors = await embedding_service.embed_batch(texts)

    # 層次聚類
    from sklearn.cluster import AgglomerativeClustering
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=0.5,  # 語意距離閾值
        metric='cosine',
        linkage='average'
    )
    labels = clustering.fit_predict(vectors)

    # 分組
    groups = {}
    for claim, label in zip(claims, labels):
        if label not in groups:
            groups[label] = []
        groups[label].append(claim)

    # 為每個組生成 proposition 名稱
    result = []
    for label, group_claims in groups.items():
        # 取代表性的 proposition
        proposition = await llm.generate(
            prompt=f"根據以下主張，用一句話描述它們討論的核心命題：\n{[c['claim_text_zh'] for c in group_claims]}"
        )
        result.append({
            "proposition": proposition,
            "claims": group_claims
        })

    return result

proposition_groups = await group_by_proposition(all_claims)

# 3. 分析每個 proposition 的 stance 分佈
def analyze_stance_distribution(group):
    """分析單個 proposition 下的立場分佈"""
    claims = group["claims"]

    stance_dist = {"support": [], "oppose": [], "neutral": []}
    for claim in claims:
        position = claim["stance"]["position"]
        stance_dist[position].append({
            "claim_text_zh": claim["claim_text_zh"],
            "source_title": claim["source_title"],
            "source_url": claim["source_url"],
            "confidence": claim["stance"]["confidence"],
            "evidence_spans": claim["evidence_spans"],
            "lens_tags": claim.get("lens_tags", {})
        })

    return {
        "proposition": group["proposition"],
        "stance_distribution": stance_dist,
        "support_count": len(stance_dist["support"]),
        "oppose_count": len(stance_dist["oppose"]),
        "neutral_count": len(stance_dist["neutral"]),
        "is_controversial": len(stance_dist["support"]) >= 1 and len(stance_dist["oppose"]) >= 1
    }

analyzed_groups = [analyze_stance_distribution(g) for g in proposition_groups]

# 4. 找出有分歧的 proposition（至少有支持和反對）
controversial = [g for g in analyzed_groups if g["is_controversial"]]

# 5. 分析分歧根源
async def analyze_disagreement(group):
    """分析單個分歧的根源"""
    support_claims = group["stance_distribution"]["support"]
    oppose_claims = group["stance_distribution"]["oppose"]

    # 對比視角標記
    support_lenses = [c.get("lens_tags", {}) for c in support_claims]
    oppose_lenses = [c.get("lens_tags", {}) for c in oppose_claims]

    # 找出視角差異
    lens_differences = {}
    for dim in ["governance_orientation", "evaluation_orientation", "collaboration_model"]:
        support_vals = [l.get(dim) for l in support_lenses if l.get(dim)]
        oppose_vals = [l.get(dim) for l in oppose_lenses if l.get(dim)]
        if support_vals and oppose_vals:
            if set(support_vals) != set(oppose_vals):
                lens_differences[dim] = {
                    "support_tendency": max(set(support_vals), key=support_vals.count),
                    "oppose_tendency": max(set(oppose_vals), key=oppose_vals.count)
                }

    # 生成根源分析
    root_cause = await llm.generate(
        prompt=f"""分析以下分歧的根源：

命題：{group["proposition"]}

支持方主張：
{[c["claim_text_zh"] for c in support_claims]}

反對方主張：
{[c["claim_text_zh"] for c in oppose_claims]}

視角差異：{lens_differences}

請用一句話描述分歧的根本原因，以及 2-3 個可能的調和點。"""
    )

    return {
        **group,
        "lens_differences": lens_differences,
        "root_cause_analysis": root_cause
    }

disagreements = [await analyze_disagreement(g) for g in controversial]

# 6. 創建 Artifact
artifact = Artifact(
    workspace_id=workspace_id,
    artifact_type=ArtifactType.DISAGREEMENT_BRIEF,
    title=f"分歧摘要: {focus_topic or disagreements[0]['proposition']}",
    content={
        "brief_id": str(uuid.uuid4()),
        "generated_at": datetime.now().isoformat(),
        "focus_topic": focus_topic,
        "intent_id": intent_id,
        "materials_count": len(materials),
        "claims_count": len(all_claims),
        "disagreements": disagreements,
        "non_controversial": [g for g in analyzed_groups if not g["is_controversial"]]
    }
)
await artifact_store.create(artifact)
```

## 輸出

```yaml
artifact_type: disagreement_brief
brief_id: "db_001"
generated_at: "2026-01-01T10:00:00Z"
focus_topic: "HITL 多少才夠？"
intent_id: "intent_001"

summary:
  materials_count: 6
  claims_count: 12
  disagreements_found: 2
  non_controversial_propositions: 3

# 核心分歧（按重要性排序）
disagreements:
  - proposition: "Multi-agent 系統是否需要充分的 human-in-the-loop"

    stance_distribution:
      support:
        - claim_text_zh: "mixed-initiative 提升使用者對結果的信任度"
          source_title: "Dango Paper"
          source_url: "https://arxiv.org/..."
          confidence: 0.9
          evidence_spans:
            - block_id: "p_012"
              original_text: "User trust increased by 34%..."
          lens_tags:
            collaboration_model: "mixed_initiative"
            evaluation_orientation: "human_centered"

        - claim_text_zh: "interrupt_before/after 是標準的 HITL 原語"
          source_title: "LangGraph 0.3.0 Release Notes"
          source_url: "https://..."
          confidence: 0.85
          evidence_spans:
            - block_id: "p_003"
              original_text: "Use interrupt_before to pause..."
          lens_tags:
            governance_orientation: "control_plane"

      oppose:
        - claim_text_zh: "過多的 HITL 會拖慢效率，應該最小化人工介入"
          source_title: "AutoGen Blog Post"
          source_url: "https://..."
          confidence: 0.75
          evidence_spans:
            - block_id: "p_007"
              original_text: "The goal is to minimize human intervention..."
          lens_tags:
            governance_orientation: "tooling"
            collaboration_model: "agent_primary"

      neutral: []

    support_count: 2
    oppose_count: 1
    neutral_count: 0

    # 視角差異分析
    lens_differences:
      governance_orientation:
        support_tendency: "control_plane"
        oppose_tendency: "tooling"
      collaboration_model:
        support_tendency: "mixed_initiative"
        oppose_tendency: "agent_primary"

    # 根源分析
    root_cause_analysis:
      root_cause: "評估場景不同：支持方多在研究/實驗環境，重視可解釋性和信任；反對方多在 production 環境，重視效率和規模。"
      synthesis_potential:
        - "也許需要區分「訓練期」和「部署期」的 HITL 策略"
        - "也許需要「可調節的 HITL 強度」而不是二元選擇"
        - "Mindscape 的 Policy Gate 設計可能是一個解法"

    # 寫作啟發
    insight_for_writing: |
      這個分歧可以變成一篇文章：
      「HITL 不是多或少的問題，而是『何時』和『多少』的設計問題」

      文章結構：
      1. 介紹兩種極端立場（引用 Dango + AutoGen）
      2. 分析分歧根源（場景差異）
      3. 提出解法（Mindscape 的 Policy Gate 設計）
      4. 討論 trade-offs

# 無分歧的命題（僅供參考）
non_controversial:
  - proposition: "Agent 需要可觀測性"
    support_count: 4
    oppose_count: 0
    consensus: "強共識：所有材料都支持"
```

## 這些分歧摘要可以怎麼用？

1. **累積寫作素材**：每週 3-5 個分歧，一個月就有 12-20 個
2. **找到自己的立場**：在「立場空間」中定位自己
3. **寫有深度的文章**：不只整理資料，而是整理觀點
4. **發現創新點**：分歧往往是創新的起點

## 依賴

| 服務 | 用途 |
|------|------|
| `EmbeddingService` | proposition 語意分組 |
| `artifact_store` | 創建 disagreement_brief Artifact |
| `sklearn.cluster` | AgglomerativeClustering |
