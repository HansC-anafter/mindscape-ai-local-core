"""Visual Feature Set — intermediate schema between IG vision observation and analysis pack.

Produces the exact contract that analysis.ana_aggregate_visual_features consumes:
  - visual_tokens: List[str] — merged from style.aesthetic_tags + object labels
  - color_palette: List[str] — from style.color_palette
  - dominant_mood: str — from scene.mood
  - mood_vector: Optional[List[float]] — placeholder for embedding-based mood
  - timestamp: Optional[str] — ISO timestamp for timeline analysis
  - source: str — origin identifier (e.g. "ig_reference:ref_abc123")
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VisualFeatureSet(BaseModel):
    """Feature set contract for analysis.ana_aggregate_visual_features.

    Matches the fields consumed by visual_aggregator._cluster_features,
    _timeline_features, and _compare_features.
    """

    visual_tokens: List[str] = Field(default_factory=list)
    color_palette: List[str] = Field(default_factory=list)
    dominant_mood: str = ""
    mood_vector: Optional[List[float]] = None
    timestamp: Optional[str] = None
    source: str = "ig_reference"


def extract_feature_set(
    vision_data: Dict[str, Any],
    source_id: str = "",
    timestamp: Optional[str] = None,
) -> VisualFeatureSet:
    """Extract a VisualFeatureSet from a VisionAnalysisResult dict.

    This is the normalization layer between IG's vision observation (v1.0 or v2.0)
    and the analysis pack's aggregate_visual_features tool.

    Args:
        vision_data: Dict from VisionAnalysisResult.model_dump() or raw vision_description.
        source_id: Source identifier (e.g. reference_id or account handle).
        timestamp: Optional ISO timestamp for timeline analysis.

    Returns:
        VisualFeatureSet ready for ana_aggregate_visual_features consumption.
    """
    tokens: List[str] = []
    colors: List[str] = []
    mood = ""

    # --- Extract from v1.0 core tiers ---

    # Style tier
    style = vision_data.get("style", {})
    if isinstance(style, dict):
        tags = style.get("aesthetic_tags", [])
        if isinstance(tags, list):
            tokens.extend([t for t in tags if isinstance(t, str)])

        ig_style = style.get("instagram_style", "")
        if ig_style and isinstance(ig_style, str):
            tokens.append(ig_style)

        palette = style.get("color_palette", [])
        if isinstance(palette, list):
            colors.extend([c for c in palette if isinstance(c, str)])

        techniques = style.get("visual_techniques", [])
        if isinstance(techniques, list):
            tokens.extend([t for t in techniques if isinstance(t, str)])

    # Object tier
    objects = vision_data.get("objects", {})
    if isinstance(objects, dict):
        obj_list = objects.get("objects", [])
        if isinstance(obj_list, list):
            for obj in obj_list:
                if isinstance(obj, dict):
                    label = obj.get("label", "")
                    confidence = obj.get("confidence", 0)
                    if label and confidence >= 0.7:
                        tokens.append(label.lower().replace(" ", "-"))

    # Scene tier
    scene = vision_data.get("scene", {})
    if isinstance(scene, dict):
        mood = scene.get("mood", "") or ""

    # --- Extract from v2.0 extended tiers (if present) ---

    # Subjects
    subjects = vision_data.get("subjects", [])
    if isinstance(subjects, list):
        for subj in subjects:
            if isinstance(subj, dict):
                archetypes = subj.get("archetype_tags", [])
                if isinstance(archetypes, list):
                    tokens.extend([a for a in archetypes if isinstance(a, str)])

    # Camera tech
    camera = vision_data.get("camera_tech")
    if isinstance(camera, dict):
        shot_type = camera.get("shot_type", "")
        if shot_type:
            tokens.append(shot_type)
        focal = camera.get("focal_length_class", "")
        if focal:
            tokens.append(focal)

    # Environment
    env = vision_data.get("environment")
    if isinstance(env, dict):
        loc = env.get("location_type", "")
        if loc:
            tokens.append(loc)
        tod = env.get("time_of_day", "")
        if tod:
            tokens.append(tod)

    # Dedupe tokens preserving order
    seen = set()
    unique_tokens = []
    for t in tokens:
        t_lower = t.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            unique_tokens.append(t_lower)

    # Build source label
    source_label = f"ig_reference:{source_id}" if source_id else "ig_reference"

    return VisualFeatureSet(
        visual_tokens=unique_tokens,
        color_palette=colors,
        dominant_mood=mood,
        mood_vector=None,  # Placeholder for future embedding
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        source=source_label,
    )


def feature_set_to_aggregator_ref(
    fs: VisualFeatureSet,
    feature_set_id: str = "",
) -> Dict[str, Any]:
    """Convert a VisualFeatureSet into the format expected by
    analysis.ana_aggregate_visual_features' feature_refs input.

    This produces the inline-data variant (features key populated directly)
    so no storage round-trip is needed.

    Returns:
        Dict matching the schema: {source, feature_set_id, features: {...}}
    """
    return {
        "source": fs.source,
        "feature_set_id": feature_set_id,
        "features": {
            "visual_tokens": fs.visual_tokens,
            "color_palette": fs.color_palette,
            "dominant_mood": fs.dominant_mood,
            "mood_vector": fs.mood_vector,
            "timestamp": fs.timestamp,
        },
    }
