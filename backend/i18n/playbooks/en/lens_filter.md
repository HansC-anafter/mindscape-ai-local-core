---
playbook_code: lens_filter
version: 2.0.0
locale: en
name: "Lens Filter"
description: "Tag materials with perspective labels, perform forward filtering (matching your perspective) and reverse filtering (intentionally viewing opposite perspectives), and extract Claim/Stance/Evidence structures."
capability_code: frontier_research
tags:
  - research
  - filtering
  - perspective
---

# Lens Filter

## Overview
Tag collected materials with perspective labels, perform forward filtering and reverse filtering (contrarian), extract Claim/Stance/Evidence structures and anchor evidence using block_id.

## What problem does this playbook solve?
General data organization only does "topic similarity", but what you need is:
- **Similar/opposite by perspective structure**: Not just "all talking about multi-agent", but also "what is their stance"
- **Intentionally view opposing perspectives (contrarian)**: Avoid only viewing materials that match your preferences, causing confirmation bias
- **Verifiable evidence**: Each claim has traceable evidence spans (anchored with block_id)

## Corresponding Existing Systems

| Model Used | Purpose |
|------------|---------|
| `MindLensInstance` | Read personal perspective preferences |
| `LensComposition` | Read perspective composition configuration |
| `RESEARCH_LENS_DIMENSIONS` | Research domain-specific dimension definitions |

## Inputs
- `material_content`: Material content (text)
- `source_url`: Material source URL
- `source_title`: Material title
- `lens_composition_id`: Perspective composition ID to use
- `extract_claims`: Whether to extract Claim/Stance/Evidence (default: true)
- `current_intent_lens_tags`: Current intent's perspective tags (for contrarian judgment)
- `current_intent_stances`: Current intent's stances (for stance opposite judgment)

## Perspective Dimensions (RESEARCH_LENS_DIMENSIONS)

| Dimension | Options | Contrarian Pair | Description |
|-----------|---------|------------------|-------------|
| `governance_orientation` | control_plane, orchestration, tooling | control_plane ↔ tooling | Governance orientation |
| `evaluation_orientation` | benchmark, human_centered, auditing | benchmark ↔ auditing | Evaluation orientation |
| `collaboration_model` | human_primary, agent_primary, mixed_initiative | human_primary ↔ agent_primary | Collaboration model |
| `observability` | logging, tracing, provenance, reproducibility | (no opposite pair) | Observability |

## Execution Logic

```python
from datetime import datetime, timedelta
from fuzzywuzzy import fuzz

# =====================
# 1. Preprocess content
# =====================
def preprocess_content(content: str) -> Dict[str, Any]:
    """Split into blocks and assign block_id"""
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
# 2. Contrarian rules configuration
# =====================
CONTRARIAN_RULES = {
    "min_contrarian_per_intent": 2,
    "contrarian_definitions": [
        # ⚠️ stance.position opposite: Most important contrarian rule
        {"field": "stance.position", "condition": "opposite"},
        # Lens pair opposition
        {"field": "lens_tags.governance_orientation", "pair": ["control_plane", "tooling"]},
        {"field": "lens_tags.evaluation_orientation", "pair": ["benchmark", "auditing"]},
        {"field": "lens_tags.collaboration_model", "pair": ["human_primary", "agent_primary"]},
    ],
    # ⚠️ Quality thresholds (must apply)
    "quality_thresholds": {
        "min_evidence_count": 1,
        "min_source_credibility": 0.6,
        "max_age_days": 365
    }
}

# =====================
# 3. Perspective tagging + Claim extraction
# =====================
composition = await mind_lens_service.get_composition(lens_composition_id)

extraction_result = await llm.structured_generate(
    prompt=build_extraction_prompt(preprocessed, composition),
    output_schema={
        "lens_tags": {
            "governance_orientation": "enum(control_plane|orchestration|tooling)",
            "evaluation_orientation": "enum(benchmark|human_centered|auditing)",
            "collaboration_model": "enum(human_primary|agent_primary|mixed_initiative)",
            "observability": "array(enum(logging|tracing|provenance|reproducibility))"
        },
        "claims": [{
            "claim_text_en": "string",
            "claim_text_zh": "string",
            "evidence_spans": [{
                "block_id": "string",
                "original_text": "string"
            }],
            "stance": {
                "proposition": "string",
                "position": "enum(support|oppose|neutral)",
                "confidence": "float"
            }
        }]
    }
)

# =====================
# 4. Contrarian selection
# =====================
def select_contrarians(tagged_materials, current_intent_lens_tags, current_intent_stances):
    """Select materials that are contrarian to current intent"""
    contrarians = []

    for material in tagged_materials:
        is_contrarian = False
        contrarian_reason = []

        # Check stance.position opposite
        for claim in material.get("claims", []):
            for intent_stance in current_intent_stances:
                if (claim["stance"]["proposition"] == intent_stance["proposition"] and
                    claim["stance"]["position"] != intent_stance["position"]):
                    is_contrarian = True
                    contrarian_reason.append(f"stance.position opposite: {intent_stance['position']} vs {claim['stance']['position']}")

        # Check lens pair opposition
        for dimension, pair in CONTRARIAN_RULES["contrarian_definitions"]:
            if "pair" in pair:
                material_value = material["lens_tags"].get(dimension)
                intent_value = current_intent_lens_tags.get(dimension)
                if material_value in pair and intent_value in pair and material_value != intent_value:
                    is_contrarian = True
                    contrarian_reason.append(f"{dimension} opposite: {intent_value} vs {material_value}")

        if is_contrarian:
            material["contrarian"] = True
            material["contrarian_reason"] = contrarian_reason
            contrarians.append(material)

    return contrarians

contrarian_materials = select_contrarians(
    [extraction_result],
    current_intent_lens_tags,
    current_intent_stances
)

# =====================
# 5. Output
# =====================
output = {
    "material_id": material_id,
    "source_title": source_title,
    "source_url": source_url,
    "lens_tags": extraction_result["lens_tags"],
    "claims": extraction_result["claims"],
    "contrarian": len(contrarian_materials) > 0,
    "contrarian_reason": contrarian_materials[0]["contrarian_reason"] if contrarian_materials else None
}
```
