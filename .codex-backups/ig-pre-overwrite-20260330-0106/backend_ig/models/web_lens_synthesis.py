"""Synthesize IGDatasetAggregate into WebVisualLensSchema.

P1c: the bridge between IG dataset-level observation aggregates
and web_generation's theme routing system.

Converts distributional summaries (colors, keywords, moods, camera settings)
into the structured contract that web_generation's theme_routing.py expects.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from capabilities.ig.models.dataset_aggregate import IGDatasetAggregate

logger = logging.getLogger(__name__)

# Optional import for flexibility
try:
    from capabilities.mind_lens.schema.base_visual_lens_schema import (
        BaseVisualLensSchema,
        ColorEntry,
        CompositionRules,
        ImageVocabulary,
        LightColorTokens,
        MoodNarrative,
        ThemeEntry,
    )
    from capabilities.web_generation.schema.visual_lens_schema import (
        StyleGuardrails,
        WebTranslationRules,
        WebVisualLensSchema,
    )

    HAS_DEPENDENCIES = True
except ImportError:
    HAS_DEPENDENCIES = False
    logger.warning("[P1c] mind_lens or web_generation not available; synthesis disabled")


def synthesize_web_visual_lens(
    aggregate: IGDatasetAggregate,
    lens_name: Optional[str] = None,
    lens_description: Optional[str] = None,
) -> "WebVisualLensSchema":
    """Synthesize an IGDatasetAggregate into a WebVisualLensSchema.

    Maps distributional summaries to the structured fields that web_generation's
    theme_routing.py requires:
      - keyword_frequency → ImageVocabulary.themes + themes_enhanced
      - shot_type_distribution → ImageVocabulary.distances
      - camera_tech_distribution → CompositionRules.depth_of_field_hint, focal_length
      - color_distribution → LightColorTokens.color_palette + color_palette_enhanced
      - dominant_moods → MoodNarrative.emotion_keywords
      - distributions → WebTranslationRules heuristics

    Args:
        aggregate: IGDatasetAggregate from P1b.
        lens_name: Optional lens name (auto-generated if omitted).
        lens_description: Optional description.

    Returns:
        WebVisualLensSchema ready for theme routing.

    Raises:
        ImportError: If mind_lens or web_generation schemas are not available.
    """
    if not HAS_DEPENDENCIES:
        raise ImportError(
            "mind_lens and web_generation schemas required for synthesis. "
            "Ensure both capability packs are available."
        )

    lens_id = f"ig_synth_{uuid4().hex[:8]}"
    name = lens_name or f"IG Style — {aggregate.source_account or 'collection'}"
    desc = lens_description or (
        f"Auto-synthesized from {aggregate.observation_count} IG references"
        f" ({aggregate.source_account or 'mixed sources'})"
    )

    # --- ImageVocabulary ---
    themes = [kw.keyword for kw in aggregate.keyword_frequency[:15]]
    themes_enhanced = [
        ThemeEntry(keyword=kw.keyword, confidence=kw.coverage, source="ig_aggregate")
        for kw in aggregate.keyword_frequency[:15]
    ]

    # Map shot_type_distribution to distances
    shot_to_distance = {
        "extreme-close-up": "extreme-close-up",
        "close-up": "close-up",
        "medium-close-up": "medium-close-up",
        "medium": "medium",
        "full": "full",
        "wide": "wide",
    }
    distances = [
        shot_to_distance.get(st, st)
        for st in aggregate.shot_type_distribution.keys()
    ]

    # Map camera_tech_distribution to depth of field hints
    dof_hints = []
    for tech, ratio in aggregate.camera_tech_distribution.items():
        if "telephoto" in tech or "short-telephoto" in tech:
            dof_hints.append("shallow")
        elif "wide" in tech or "ultra-wide" in tech:
            dof_hints.append("deep")
        elif "standard" in tech:
            dof_hints.append("moderate")

    image_vocab = ImageVocabulary(
        themes=themes,
        themes_enhanced=themes_enhanced,
        distances=distances,
        angles=[],  # Not tracked in aggregate
        depth_of_field=list(set(dof_hints)) if dof_hints else [],
        dynamics=[],
    )

    # --- CompositionRules ---
    # Infer from camera tech distribution
    dominant_focal = max(aggregate.camera_tech_distribution, key=aggregate.camera_tech_distribution.get) if aggregate.camera_tech_distribution else None
    focal_length_map = {
        "ultra-wide": 16.0,
        "wide": 28.0,
        "standard": 50.0,
        "short-telephoto": 85.0,
        "telephoto": 135.0,
    }

    composition = CompositionRules(
        whitespace_ratio=0.3,  # Default moderate
        subject_position="rule-of-thirds",  # Safe default
        focal_length=focal_length_map.get(dominant_focal) if dominant_focal else None,
        depth_of_field_hint=dof_hints[0] if dof_hints else None,
    )

    # --- LightColorTokens ---
    valid_hex_colors = []
    enhanced_colors = []
    for cd in aggregate.color_distribution[:8]:
        hex_val = cd.hex
        if hex_val.startswith("#") and len(hex_val) == 7:
            try:
                int(hex_val[1:], 16)
                valid_hex_colors.append(hex_val)
                role = "primary" if cd.coverage > 0.2 else ("secondary" if cd.coverage > 0.1 else "accent")
                enhanced_colors.append(
                    ColorEntry(hex=hex_val, coverage=cd.coverage, role=role, score=cd.coverage)
                )
            except ValueError:
                pass

    # Infer color temperature from moods
    warm_signals = {"warm", "cozy", "golden", "sunset", "amber"}
    cool_signals = {"cool", "cold", "blue", "crisp", "winter"}
    mood_set = set(aggregate.dominant_moods)
    if mood_set & warm_signals:
        color_temp = "warm"
    elif mood_set & cool_signals:
        color_temp = "cool"
    else:
        color_temp = "neutral"

    light_color = LightColorTokens(
        color_temperature=color_temp,
        contrast_level="medium",
        saturation=0.5,
        color_palette=valid_hex_colors,
        color_palette_enhanced=enhanced_colors if enhanced_colors else None,
    )

    # --- MoodNarrative ---
    mood_narrative = MoodNarrative(
        emotion_keywords=aggregate.dominant_moods[:5],
        narrative_distance="observer",
        rhythm="steady",
    )

    # --- WebTranslationRules ---
    # Heuristic: image-heavy if many visual tokens, dense if many observations
    kw_count = len(aggregate.keyword_frequency)
    layout_density = "dense" if kw_count > 20 else ("medium" if kw_count > 8 else "sparse")
    image_text_ratio = "image-heavy" if aggregate.observation_count > 10 else "balanced"

    web_rules = WebTranslationRules(
        hero_image_preference=distances[:2] if distances else ["medium"],
        image_text_ratio=image_text_ratio,
        layout_density=layout_density,
        border_radius="medium",
        shadow_style="subtle",
        animation_rhythm="steady",
    )

    # --- StyleGuardrails ---
    guardrails = StyleGuardrails(
        forbidden_elements=[],
        required_elements=themes[:3] if themes else [],
    )

    return WebVisualLensSchema(
        lens_id=lens_id,
        name=name,
        description=desc,
        image_vocabulary=image_vocab,
        composition_rules=composition,
        light_color_tokens=light_color,
        mood_narrative=mood_narrative,
        version="1.0.0",
        created_at=datetime.now(timezone.utc),
        web_translation_rules=web_rules,
        style_guardrails=guardrails,
    )
