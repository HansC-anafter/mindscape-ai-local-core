"""
Core LLM: Data Utilities
Data filtering and transformation utilities for playbook workflows
"""

import logging
from typing import Dict, Any, List, Union, Optional
from statistics import mean

logger = logging.getLogger(__name__)


async def filter_features(
    features_data: Union[Dict[str, Any], List[Dict[str, Any]]],
    remove_embeddings: bool = True,
    keep_embedding_metadata: bool = True,
    profile_id: Optional[str] = None  # Accept but not used (for compatibility with workflow_orchestrator)
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Filter feature data to remove redundant fields like embeddings for LLM processing.

    Strategy:
    - Remove actual embedding vectors (LLM cannot process raw vectors)
    - Keep embedding metadata (dimension, existence) for reference
    - This reduces token usage while preserving useful information

    Args:
        features_data: Feature data (single dict or list of dicts)
        remove_embeddings: Whether to remove visual_style_embedding vector (default: True)
        keep_embedding_metadata: Whether to keep embedding_dim and has_embedding metadata (default: True)

    Returns:
        Filtered feature data with same structure as input
    """
    def _filter_single_feature(feature: Dict[str, Any]) -> Dict[str, Any]:
        """Filter a single feature dictionary, keeping only essential fields for LLM analysis."""
        filtered = {}

        # Remove embedding vector
        if remove_embeddings and "visual_style_embedding" in feature:
            embedding = feature["visual_style_embedding"]
            if keep_embedding_metadata:
                if embedding is not None:
                    filtered["embedding_dim"] = len(embedding) if isinstance(embedding, list) else feature.get("embedding_dim", 768)
                    filtered["has_embedding"] = True
                else:
                    filtered["has_embedding"] = False

        # Keep essential color information (simplified)
        if "color_palette" in feature:
            color_palette = feature["color_palette"]
            filtered["color_palette"] = {
                "dominant_colors": color_palette.get("dominant_colors", [])[:5] if isinstance(color_palette.get("dominant_colors"), list) else color_palette.get("dominant_colors", []),
                "scheme_type": color_palette.get("scheme_type"),
                "contrast_ratio": color_palette.get("contrast_ratio"),
            }

        # Keep essential layout information
        if "layout_density" in feature:
            filtered["layout_density"] = feature["layout_density"]
        if "layout_type" in feature:
            filtered["layout_type"] = feature["layout_type"]
        if "composition" in feature and isinstance(feature["composition"], dict):
            # Keep only essential composition fields
            comp = feature["composition"]
            filtered["composition"] = {
                k: v for k, v in comp.items()
                if k in ["whitespace_ratio", "subject_position", "horizon_position", "geometry_preference"]
            }

        # Keep essential style information
        if "visual_style" in feature:
            style = feature["visual_style"]
            filtered["visual_style"] = {
                "primary_style": style.get("primary_style"),
                "confidence": style.get("confidence"),
                "secondary_styles": style.get("secondary_styles", [])[:3] if isinstance(style.get("secondary_styles"), list) else style.get("secondary_styles", []),
            }

        # Keep contrast preference
        if "contrast_pref" in feature:
            filtered["contrast_pref"] = feature["contrast_pref"]

        # Keep mood analysis (if present)
        if "mood_analysis" in feature:
            filtered["mood_analysis"] = feature["mood_analysis"]

        return filtered

    if isinstance(features_data, list):
        filtered_list = [_filter_single_feature(item) for item in features_data]
        logger.info(f"Filtered {len(filtered_list)} feature items, removed embeddings")
        return filtered_list
    elif isinstance(features_data, dict):
        filtered_dict = _filter_single_feature(features_data)
        logger.info("Filtered single feature item, removed embeddings")
        return filtered_dict
    else:
        logger.warning(f"Unexpected features_data type: {type(features_data)}, returning as-is")
        return features_data


async def simplify_photos(
    photos_data: List[Dict[str, Any]],
    keep_fields: Optional[List[str]] = None,
    max_items: int = 6,
    profile_id: Optional[str] = None  # Accept but not used (for compatibility)
) -> List[Dict[str, Any]]:
    """
    Keep only essential photo metadata for lens generation to reduce prompt tokens.

    Args:
        photos_data: Full Unsplash photo objects list
        keep_fields: Whitelisted top-level fields to keep; defaults to minimal set: id, urls, user, description, alt_description, color
        max_items: Max photos to keep (default: 6)

    Returns:
        Simplified photo list with only needed fields, with empty string fallbacks for missing fields
    """
    # Handle case where template engine returns JSON string instead of list
    if isinstance(photos_data, str):
        try:
            import json
            photos_data = json.loads(photos_data)
            logger.info(f"Parsed photos_data from JSON string, got {len(photos_data) if isinstance(photos_data, list) else 'non-list'} items")
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse photos_data JSON string: {photos_data[:100] if len(str(photos_data)) > 100 else photos_data}")
            return []

    if not isinstance(photos_data, list):
        logger.warning(f"Expected photos_data list, got {type(photos_data)}, value={str(photos_data)[:100] if len(str(photos_data)) > 100 else photos_data}, returning []")
        return []

    default_fields = ["id", "urls", "user", "description", "alt_description", "color"]
    fields = keep_fields or default_fields

    simplified: List[Dict[str, Any]] = []
    for photo in photos_data[:max_items]:
        item = {}
        for field in fields:
            if field == "user":
                user = photo.get("user") or {}
                item["photographer"] = user.get("name") or ""
                item["photographer_username"] = user.get("username") or ""
            elif field in photo:
                item[field] = photo[field]
            else:
                # Provide empty string fallback for missing fields
                if field in ["description", "alt_description"]:
                    item[field] = ""
                elif field == "color":
                    item[field] = photo.get("color", "")

        # Ensure required fields exist with fallbacks
        if "photographer" not in item:
            item["photographer"] = ""
        if "photographer_username" not in item:
            item["photographer_username"] = ""
        if "description" not in item:
            item["description"] = ""
        if "alt_description" not in item:
            item["alt_description"] = photo.get("alt_description", "")

        # Normalize urls to keep only needed sizes
        if "urls" in item and isinstance(item["urls"], dict):
            urls = item["urls"]
            item["urls"] = {k: v for k, v in urls.items() if k in ["raw", "full", "regular", "small", "thumb"]}

        # Map id to photo_id for schema compatibility
        if "id" in item:
            item["photo_id"] = item["id"]

        simplified.append(item)

    logger.info(f"Simplified photos from {len(photos_data)} to {len(simplified)}, fields={fields}, max_items={max_items}")
    return simplified


async def summarize_features(
    features_data: List[Dict[str, Any]],
    profile_id: Optional[str] = None  # Accept but not used
) -> Dict[str, Any]:
    """
    Aggregate feature list into compact statistical summary for LLM prompts.

    Returns:
        Dict with aggregated color/composition/style/mood stats (arrays kept small).
    """
    if not isinstance(features_data, list) or not features_data:
        logger.warning(f"Expected non-empty list for features_data, got {type(features_data)}")
        return {}

    def collect_list(key: str) -> List[Any]:
        vals = []
        for f in features_data:
            val = f.get(key)
            if isinstance(val, list):
                vals.extend(val)
            elif val:
                vals.append(val)
        return vals

    # Color
    palettes = [f.get("color_palette", {}) for f in features_data if isinstance(f.get("color_palette"), dict)]
    dominant_colors = []
    contrast_vals = []
    for p in palettes:
        dc = p.get("dominant_colors") or []
        if isinstance(dc, list):
            dominant_colors.extend(dc[:5])
        cr = p.get("contrast_ratio")
        if isinstance(cr, (int, float)):
            contrast_vals.append(cr)

    color_summary = {
        "main_colors": dominant_colors[:10],
        "contrast_avg": mean(contrast_vals) if contrast_vals else None
    }

    # Composition
    compositions = [f.get("composition", {}) for f in features_data if isinstance(f.get("composition"), dict)]
    whitespace_vals = [c.get("whitespace_ratio") for c in compositions if isinstance(c.get("whitespace_ratio"), (int, float))]
    subject_positions = [c.get("subject_position") for c in compositions if c.get("subject_position")]
    horizon_positions = [c.get("horizon_position") for c in compositions if c.get("horizon_position")]
    geometry_prefs = collect_list("geometry_preference")

    composition_summary = {
        "whitespace_avg": mean(whitespace_vals) if whitespace_vals else None,
        "subject_position_modes": subject_positions[:5],
        "horizon_position_modes": horizon_positions[:5],
        "geometry_preferences": geometry_prefs[:5],
    }

    # Style
    styles = [f.get("visual_style", {}) for f in features_data if isinstance(f.get("visual_style"), dict)]
    primary_styles = [s.get("primary_style") for s in styles if s.get("primary_style")]
    secondary_styles = []
    for s in styles:
        sec = s.get("secondary_styles")
        if isinstance(sec, list):
            secondary_styles.extend(sec[:3])

    style_summary = {
        "primary_styles": primary_styles[:5],
        "secondary_styles": secondary_styles[:5],
    }

    # Mood
    moods = [f.get("mood_analysis", {}) for f in features_data if isinstance(f.get("mood_analysis"), dict)]
    emotion_keywords = []
    narrative_distance = []
    rhythm = []
    for m in moods:
        ek = m.get("emotion_keywords")
        if isinstance(ek, list):
            emotion_keywords.extend(ek[:5])
        nd = m.get("narrative_distance")
        if nd:
            narrative_distance.append(nd)
        rh = m.get("rhythm")
        if rh:
            rhythm.append(rh)

    mood_summary = {
        "emotion_keywords": emotion_keywords[:8],
        "narrative_distance": narrative_distance[:3],
        "rhythm": rhythm[:3],
    }

    summary = {
        "color_analysis": color_summary,
        "composition_analysis": composition_summary,
        "style_analysis": style_summary,
        "mood_analysis": mood_summary,
        "sample_size": len(features_data),
    }
    logger.info(f"Summarized {len(features_data)} features for compact prompt")
    return summary


async def sample_features(
    features_data: List[Dict[str, Any]],
    max_items: int = 3,
    profile_id: Optional[str] = None  # Accept but not used
) -> List[Dict[str, Any]]:
    """
    Return a small sample of feature dicts to provide concrete examples without full payload.
    """
    if not isinstance(features_data, list):
        logger.warning(f"Expected features_data list, got {type(features_data)}")
        return []
    sample = features_data[:max_items]
    logger.info(f"Sampled {len(sample)} of {len(features_data)} features (max_items={max_items})")
    return sample


async def build_search_query(
    search_keywords: Optional[Dict[str, Any]] = None,
    theme_keywords: Optional[List[str]] = None,
    style_preferences: Optional[List[str]] = None,
    profile_id: Optional[str] = None  # Accept but not used
) -> Dict[str, str]:
    """
    Build Unsplash search query with fallback to input keywords.

    Args:
        search_keywords: Expanded keywords from LLM (may be empty)
        theme_keywords: Fallback theme keywords from input
        style_preferences: Fallback style preferences from input

    Returns:
        Dict with "query" key containing the search query string
    """
    core_themes = []
    styles = []

    if isinstance(search_keywords, dict):
        ct = search_keywords.get("core_themes")
        st = search_keywords.get("styles")
        if isinstance(ct, list):
            core_themes = [c for c in ct if c][:2]
        if isinstance(st, list):
            styles = [s for s in st if s][:1]

    if not core_themes and isinstance(theme_keywords, list):
        core_themes = [t for t in theme_keywords if t][:2]
    if not styles and isinstance(style_preferences, list):
        styles = [s for s in style_preferences if s][:1]

    query_parts = core_themes + styles
    query = " ".join(query_parts).strip() if query_parts else (theme_keywords[0] if theme_keywords and len(theme_keywords) > 0 else "minimalist")
    logger.info(f"Built search query='{query}' from core_themes={core_themes}, styles={styles}")
    return {"query": query}
