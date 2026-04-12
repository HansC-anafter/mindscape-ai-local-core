"""
Projection Builder — extract flat, filterable projection fields from V2.0 schema.

Turns a VisionAnalysisResult dict into a flat dict of searchable/filterable
fields prefixed with `p_`. These projections are stored in `_index.json`
alongside existing index fields, enabling structured queries on V2.0 schema
attributes without modifying the upstream schema.

Part of the Reference Compilation System — Phase 1 (Projection Layer + Hard Filter).
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _nested(d: dict, path: str, default: Any = "") -> Any:
    """Safely traverse a nested dict by dot-separated path."""
    parts = path.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def _first_subject(vision: dict, field_path: str, default: str = "") -> str:
    """Get a field from the first subject entry, traversing dot paths."""
    subjects = vision.get("subjects") or []
    if not subjects:
        return default
    return _nested(subjects[0], field_path, default)


def _first_subject_list(vision: dict, field_name: str) -> List[str]:
    """Get a list field from the first subject entry."""
    subjects = vision.get("subjects") or []
    if not subjects:
        return []
    val = subjects[0].get(field_name)
    if isinstance(val, list):
        return val
    return []


def _all_subjects_clothing_materials(vision: dict) -> List[str]:
    """Collect unique clothing material values across all subjects."""
    materials = set()
    for subj in vision.get("subjects") or []:
        for item in subj.get("clothing") or []:
            mat = item.get("material", "")
            if mat:
                materials.add(mat.strip().lower())
    return sorted(materials)


def _unique_lower(values: List[Any]) -> List[str]:
    """Normalize scalar/list items into unique lower-cased strings."""
    normalized: List[str] = []
    seen = set()
    for value in values:
        text = str(value).strip().lower() if value is not None else ""
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _collect_object_values(vision: dict, field_name: str) -> List[str]:
    objects = (vision.get("objects") or {}).get("objects") or []
    return _unique_lower([obj.get(field_name, "") for obj in objects if isinstance(obj, dict)])


def _collect_subject_values(vision: dict, field_path: str) -> List[str]:
    values: List[Any] = []
    for subj in vision.get("subjects") or []:
        if not isinstance(subj, dict):
            continue
        values.append(_nested(subj, field_path, ""))
    return _unique_lower(values)


def _collect_subject_list_values(vision: dict, field_name: str) -> List[str]:
    values: List[Any] = []
    for subj in vision.get("subjects") or []:
        if not isinstance(subj, dict):
            continue
        values.extend(subj.get(field_name) or [])
    return _unique_lower(values)


def _collect_subject_nested_list_values(
    vision: dict,
    list_name: str,
    field_name: str,
) -> List[str]:
    values: List[Any] = []
    for subj in vision.get("subjects") or []:
        if not isinstance(subj, dict):
            continue
        for item in subj.get(list_name) or []:
            if not isinstance(item, dict):
                continue
            values.append(item.get(field_name, ""))
    return _unique_lower(values)


def _collect_root_list_values(vision: dict, field_path: str) -> List[str]:
    value = _nested(vision, field_path, [])
    if isinstance(value, list):
        return _unique_lower(value)
    return []


def build_projection(vision: dict) -> Dict[str, Any]:
    """Extract flat, filterable projection from V2.0 schema dict.

    Args:
        vision: A VisionAnalysisResult dict (the `vision_description` field
                from ReferenceMetadata).

    Returns:
        Dict of `p_*` projection fields ready for index storage and querying.
        All enum-like fields are lowercased strings for consistent matching.
    """
    if not vision or not isinstance(vision, dict):
        return {}

    # --- Environment ---
    env = vision.get("environment") or {}
    light_source = env.get("light_source") or {}

    # --- Camera Tech ---
    cam = vision.get("camera_tech") or {}

    # --- Style ---
    style = vision.get("style") or {}

    # --- Scene ---
    scene = vision.get("scene") or {}

    # --- Material ---
    mat_obs = vision.get("material") or {}
    materials_list = mat_obs.get("materials") or []
    # --- Product / Safety ---
    product = vision.get("product_interaction") or {}
    safety = vision.get("safety_flags") or {}
    training = vision.get("training_annotations") or {}

    projection = {
        # ===== Hard filters (enum exact match) =====
        # Environment
        "p_location": _lower(env.get("location_type", "")),
        "p_location_sub": _lower(env.get("location_subtype", "")),
        "p_light_temp": _lower(light_source.get("color_temperature", "")),
        "p_light_intensity": _lower(light_source.get("intensity", "")),
        "p_light_direction": _lower(light_source.get("direction", "")),
        "p_light_source_type": _lower(light_source.get("source_type", "")),
        "p_time_of_day": _lower(env.get("time_of_day", "")),
        # Camera Tech
        "p_shot_type": _lower(cam.get("shot_type", "")),
        "p_focal_class": _lower(cam.get("focal_length_class", "")),
        "p_focal_range": _lower(cam.get("focal_length_mm_range", "")),
        "p_aperture": _lower(cam.get("estimated_aperture", "")),
        "p_dof": _lower(cam.get("depth_of_field", "")),
        "p_aspect_ratio": cam.get("aspect_ratio", ""),  # keep original case (e.g. "4:5")
        "p_camera_movement": _lower(cam.get("camera_movement", "")),
        # Subject (first person)
        "p_stance": _lower(_first_subject(vision, "pose.stance")),
        "p_gaze": _lower(_first_subject(vision, "pose.gaze_direction")),
        "p_body_orientation": _lower(_first_subject(vision, "pose.body_orientation")),
        "p_expression": _lower(_first_subject(vision, "expression")),
        "p_subject_count": len(vision.get("subjects") or []),
        # Product / safety
        "p_product_category": _lower(product.get("product_category", "")),
        "p_product_interaction_type": _lower(product.get("interaction_type", "")),
        "p_product_placement_region": _lower(product.get("placement_region", "")),
        "p_safety_nsfw_risk": _lower(safety.get("nsfw_risk", "")),
        "p_training_readiness": _lower(training.get("training_readiness", "")),
        "p_training_source_kind": _lower(training.get("training_source_kind", "")),
        "p_training_dataset_mix_role": _lower(training.get("dataset_mix_role", "")),
        "p_training_identity_signal_strength": _lower(training.get("identity_signal_strength", "")),
        "p_training_primary_subject_clarity": _lower(training.get("primary_subject_clarity", "")),
        "p_training_subject_framing": _lower(training.get("subject_framing", "")),
        "p_training_face_angle": _lower(training.get("face_angle", "")),
        "p_training_face_visibility": _lower(training.get("face_visibility", "")),
        "p_training_occlusion_level": _lower(training.get("occlusion_level", "")),
        "p_training_style_strength": _lower(training.get("style_strength", "")),
        "p_training_identity_drift_risk": _lower(training.get("identity_drift_risk", "")),
        "p_training_look_variant_level": _lower(training.get("look_variant_level", "")),
        # ===== List filters (any-match) =====
        "p_archetype_tags": _first_subject_list(vision, "archetype_tags"),
        "p_aesthetic_tags": style.get("aesthetic_tags", []),
        "p_materials": [
            _lower(m.get("material_type", ""))
            for m in materials_list
            if m.get("material_type")
        ],
        "p_clothing_materials": _all_subjects_clothing_materials(vision),
        "p_material_finishes": _unique_lower(
            [m.get("surface_finish", "") for m in materials_list if isinstance(m, dict)]
        ),
        "p_material_regions": _unique_lower(
            [m.get("region", "") for m in materials_list if isinstance(m, dict)]
        ),
        "p_object_labels": _collect_object_values(vision, "label"),
        "p_object_regions": _collect_object_values(vision, "region"),
        "p_dominant_colors": _unique_lower(style.get("dominant_colors", [])),
        "p_subject_genders": _collect_subject_values(vision, "gender_presentation"),
        "p_subject_age_ranges": _collect_subject_values(vision, "estimated_age_range"),
        "p_subject_skin_tones": _collect_subject_values(vision, "skin_tone"),
        "p_subject_ethnicities": _collect_subject_values(vision, "perceived_ethnicity"),
        "p_subject_face_shapes": _collect_subject_values(vision, "face_shape"),
        "p_subject_facial_features": _collect_subject_values(vision, "facial_features"),
        "p_hair_colors": _collect_subject_values(vision, "hair.color"),
        "p_hair_styles": _collect_subject_values(vision, "hair.style"),
        "p_hair_textures": _collect_subject_values(vision, "hair.texture"),
        "p_clothing_types": _collect_subject_nested_list_values(vision, "clothing", "garment_type"),
        "p_clothing_colors": _collect_subject_nested_list_values(vision, "clothing", "color"),
        "p_clothing_fits": _collect_subject_nested_list_values(vision, "clothing", "fit"),
        "p_clothing_style_eras": _collect_subject_nested_list_values(vision, "clothing", "style_era"),
        "p_accessories": _collect_subject_list_values(vision, "accessories"),
        "p_upper_body_coverage": _collect_subject_values(vision, "coverage.upper_body_coverage"),
        "p_lower_body_coverage": _collect_subject_values(vision, "coverage.lower_body_coverage"),
        "p_chest_visibility": _collect_subject_values(vision, "coverage.chest_visibility"),
        "p_chest_coverage_method": _collect_subject_values(vision, "coverage.chest_coverage_method"),
        "p_negative_observations": _collect_subject_list_values(vision, "negative_observations"),
        "p_subject_evidence": _collect_subject_list_values(vision, "evidence_notes"),
        "p_pose_gestures": _collect_subject_values(vision, "pose.gesture"),
        "p_interactive_props": _unique_lower(
            [prop.get("name", "") for prop in env.get("interactive_props") or [] if isinstance(prop, dict)]
        ),
        "p_prop_usages": _unique_lower(
            [prop.get("usage", "") for prop in env.get("interactive_props") or [] if isinstance(prop, dict)]
        ),
        "p_set_dressing": _unique_lower(env.get("set_dressing", [])),
        "p_training_lane_hints": _unique_lower(training.get("training_lane_hints", [])),
        "p_training_style_tags": _unique_lower(training.get("style_tags", [])),
        "p_training_quality_flags": _unique_lower(training.get("quality_flags", [])),
        "p_training_hard_blockers": _unique_lower(training.get("hard_blockers", [])),
        "p_training_reject_reasons": _unique_lower(training.get("reject_reasons", [])),
        "p_scene_evidence": _collect_root_list_values(vision, "scene.evidence_notes"),
        "p_camera_evidence": _collect_root_list_values(vision, "camera_tech.evidence_notes"),
        "p_environment_evidence": _collect_root_list_values(vision, "environment.evidence_notes"),
        # ===== Text projections (for future semantic matching) =====
        "p_mood": scene.get("mood", ""),
        "p_scene_summary": scene.get("summary", ""),
        "p_composition_text": scene.get("composition", ""),
        "p_lighting_text": scene.get("lighting", ""),
        "p_style_text": style.get("instagram_style", ""),
        "p_typography": style.get("typography", ""),
        "p_dominant_subject": (vision.get("objects") or {}).get("dominant_subject", ""),
        "p_texture_notes": mat_obs.get("texture_notes", ""),
        "p_copyright_concerns": safety.get("copyright_concerns", ""),
        "p_coverage_notes": _first_subject(vision, "coverage.coverage_notes"),
        "p_training_identity_cluster_hint": _compact(training.get("identity_cluster_hint", "")),
        "p_training_look_state_hint": _compact(training.get("look_state_hint", "")),
        "p_training_notes": _compact(training.get("training_notes", "")),
    }

    return projection


def _lower(val: Any) -> str:
    """Lowercase a string value; return empty string for non-strings."""
    if isinstance(val, str):
        return val.strip().lower()
    return ""


def _compact(val: Any) -> str:
    if isinstance(val, str):
        return val.strip()
    return ""
