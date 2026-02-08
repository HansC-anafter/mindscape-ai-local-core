---
playbook_code: disagreement_brief
version: 2.0.0
locale: en
name: "Disagreement Brief"
description: "Compare multiple materials to identify core points of disagreement. This is a \"writable asset\": accumulating 3-5 disagreement briefs per week results in a substantial article in a month."
capability_code: frontier_research
tags:
  - research
  - analysis
  - disagreement
---

# Disagreement Brief

## Overview
Compare multiple materials, group by proposition to identify core points of disagreement, analyze stance distribution, and produce "writable assets".

## What problem does this playbook solve?
- You have a pile of materials, know "they're talking about similar things", but don't know "where their disagreements are"
- You want to write in-depth articles, not just organize data, but organize "stance space"
- Accumulating 3-5 disagreement briefs per week results in a substantial article in a month

## Corresponding Existing Systems

| Model Used | Purpose |
|------------|---------|
| `Artifact (disagreement_brief)` | Store disagreement briefs |
| `Claim` / `Stance` | Read from lens_filter output |
| `EvidenceSpan` | Reference evidence anchored with block_id |

## Inputs
- `materials`: List of materials to compare (already passed through lens_filter, containing claims/lens_tags)
- `focus_topic`: Focus topic (optional)
- `intent_id`: Associated intent ID (optional)

## Execution Logic

```python
# 1. Collect all claims and tag sources
all_claims = []
for material in materials:
    for claim in material.get("claims", []):
        claim["material_id"] = material["material_id"]
        claim["source_title"] = material.get("source_title", "")
        claim["source_url"] = material.get("source_url", "")
        all_claims.append(claim)

# 2. Group by proposition (using semantic similarity)
async def group_by_proposition(claims):
    """Group semantically similar claims under the same proposition"""
    if len(claims) < 2:
        return [{"proposition": claims[0]["stance"]["proposition"], "claims": claims}]

    # Calculate embeddings
    texts = [c["claim_text_en"] for c in claims]
    vectors = await embedding_service.embed_batch(texts)

    # Hierarchical clustering
    from sklearn.cluster import AgglomerativeClustering
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=0.5,  # Semantic distance threshold
        metric='cosine',
        linkage='average'
    )
    labels = clustering.fit_predict(vectors)

    # Group
    groups = {}
    for claim, label in zip(claims, labels):
        if label not in groups:
            groups[label] = []
        groups[label].append(claim)

    # Generate proposition name for each group
    result = []
    for label, group_claims in groups.items():
        # Get representative proposition
        proposition = await llm.generate(
            prompt=f"Based on the following claims, describe the core proposition they discuss in one sentence:\n{[c['claim_text_en'] for c in group_claims]}"
        )
        result.append({
            "proposition": proposition,
            "claims": group_claims
        })

    return result

proposition_groups = await group_by_proposition(all_claims)

# 3. Analyze stance distribution for each proposition
def analyze_stance_distribution(group):
    """Analyze stance distribution under a single proposition"""
    claims = group["claims"]

    stance_dist = {"support": [], "oppose": [], "neutral": []}
    for claim in claims:
        position = claim["stance"]["position"]
        stance_dist[position].append({
            "claim_text_en": claim["claim_text_en"],
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
        "total_claims": len(claims)
    }

# 4. Identify core disagreements
def identify_core_disagreements(proposition_groups):
    """Identify core disagreements (propositions with both support and oppose)"""
    disagreements = []

    for group in proposition_groups:
        analysis = analyze_stance_distribution(group)

        # Only include if there's actual disagreement (both support and oppose)
        if analysis["support_count"] > 0 and analysis["oppose_count"] > 0:
            disagreements.append({
                "proposition": analysis["proposition"],
                "supporting_claims": analysis["stance_distribution"]["support"],
                "opposing_claims": analysis["stance_distribution"]["oppose"],
                "neutral_claims": analysis["stance_distribution"]["neutral"],
                "disagreement_intensity": min(analysis["support_count"], analysis["oppose_count"]) / analysis["total_claims"]
            })

    # Sort by disagreement intensity
    disagreements.sort(key=lambda x: x["disagreement_intensity"], reverse=True)
    return disagreements

core_disagreements = identify_core_disagreements(proposition_groups)

# 5. Generate disagreement brief
brief_content = await llm.generate(
    prompt=f"""
    Based on the following disagreements, write a brief that:
    1. Summarizes each proposition
    2. Highlights the key points of disagreement
    3. References evidence spans (block_id) for each claim

    Disagreements:
    {json.dumps(core_disagreements, indent=2)}
    """
)

# 6. Create Artifact
await artifact_store.create(
    workspace_id=workspace_id,
    artifact_type=ArtifactType.DISAGREEMENT_BRIEF,
    content={
        "intent_id": intent_id,
        "focus_topic": focus_topic,
        "materials_count": len(materials),
        "propositions_count": len(proposition_groups),
        "disagreements": core_disagreements,
        "brief_content": brief_content,
        "generated_at": datetime.now().isoformat()
    }
)
```
