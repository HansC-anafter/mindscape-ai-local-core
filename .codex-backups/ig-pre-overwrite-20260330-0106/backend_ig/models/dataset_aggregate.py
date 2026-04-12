"""IG Dataset Aggregate — batch observation aggregation following unsplash's extract_style_from_dataset pattern.

Independent schema, no BaseVisualLensSchema inheritance.
P1c is where synthesis to WebVisualLensSchema happens.

Aggregates multiple VisionAnalysisResult dicts into distributional summaries:
  - color_distribution: hex → coverage/frequency
  - keyword_frequency: tag → count
  - camera_tech_distribution: shot_type → ratio
  - scene_type_distribution: location_type → ratio
  - subject_archetype_distribution: archetype → ratio
"""

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ColorDistribution(BaseModel):
    """Color with frequency and coverage."""

    hex: str = ""
    frequency: int = 0
    coverage: float = 0.0  # 0-1, relative frequency


class KeywordFrequency(BaseModel):
    """Keyword with count."""

    keyword: str = ""
    count: int = 0
    coverage: float = 0.0  # 0-1, relative frequency


class IGDatasetAggregate(BaseModel):
    """Aggregated observations from multiple IG references.

    Independent schema — does NOT inherit BaseVisualLensSchema.
    P1c synthesizes this into WebVisualLensSchema when needed.
    """

    source_type: str = "ig_references"
    source_account: Optional[str] = None
    source_collection: Optional[str] = None
    observation_count: int = 0

    # Distributions
    color_distribution: List[ColorDistribution] = Field(default_factory=list)
    keyword_frequency: List[KeywordFrequency] = Field(default_factory=list)
    camera_tech_distribution: Dict[str, float] = Field(default_factory=dict)
    scene_type_distribution: Dict[str, float] = Field(default_factory=dict)
    subject_archetype_distribution: Dict[str, float] = Field(default_factory=dict)
    shot_type_distribution: Dict[str, float] = Field(default_factory=dict)

    # Aggregated mood
    dominant_moods: List[str] = Field(default_factory=list)  # top moods by frequency
    material_palette: List[str] = Field(default_factory=list)  # aggregated material types

    # Metadata
    aggregated_at: Optional[str] = None


def aggregate_observations(
    observations: List[Dict[str, Any]],
    source_account: Optional[str] = None,
    source_collection: Optional[str] = None,
) -> IGDatasetAggregate:
    """Aggregate multiple VisionAnalysisResult dicts into distributional summaries.

    Follows the same aggregation pattern as unsplash.extract_style_from_dataset:
    collect → count → normalize → sort → top-N.

    Args:
        observations: List of VisionAnalysisResult.model_dump() dicts.
        source_account: Optional source account handle.
        source_collection: Optional collection name.

    Returns:
        IGDatasetAggregate with distributional summaries.
    """
    if not observations:
        return IGDatasetAggregate(
            source_account=source_account,
            source_collection=source_collection,
            aggregated_at=datetime.now(timezone.utc).isoformat(),
        )

    n = len(observations)
    color_counter: Counter = Counter()
    keyword_counter: Counter = Counter()
    mood_counter: Counter = Counter()
    location_counter: Counter = Counter()
    shot_type_counter: Counter = Counter()
    focal_counter: Counter = Counter()
    archetype_counter: Counter = Counter()
    material_counter: Counter = Counter()

    for obs in observations:
        if not isinstance(obs, dict):
            continue

        # Style tier → keywords + colors
        style = obs.get("style", {})
        if isinstance(style, dict):
            for tag in style.get("aesthetic_tags", []):
                if isinstance(tag, str):
                    keyword_counter[tag.lower()] += 1
            ig_style = style.get("instagram_style", "")
            if ig_style:
                keyword_counter[ig_style.lower()] += 1
            for color in style.get("color_palette", []):
                if isinstance(color, str):
                    color_counter[color] += 1
            for tech in style.get("visual_techniques", []):
                if isinstance(tech, str):
                    keyword_counter[tech.lower()] += 1

        # Scene tier → mood
        scene = obs.get("scene", {})
        if isinstance(scene, dict):
            mood = scene.get("mood", "")
            if mood:
                mood_counter[mood.lower()] += 1

        # Camera tech → shot type, focal length
        camera = obs.get("camera_tech")
        if isinstance(camera, dict):
            st = camera.get("shot_type", "")
            if st:
                shot_type_counter[st.lower()] += 1
            fl = camera.get("focal_length_class", "")
            if fl:
                focal_counter[fl.lower()] += 1

        # Environment → location type
        env = obs.get("environment")
        if isinstance(env, dict):
            loc = env.get("location_type", "")
            if loc:
                location_counter[loc.lower()] += 1

        # Subjects → archetypes
        subjects = obs.get("subjects", [])
        if isinstance(subjects, list):
            for subj in subjects:
                if isinstance(subj, dict):
                    for arch in subj.get("archetype_tags", []):
                        if isinstance(arch, str):
                            archetype_counter[arch.lower()] += 1

        # Material
        mat = obs.get("material")
        if isinstance(mat, dict):
            for item in mat.get("materials", []):
                if isinstance(item, dict):
                    mt = item.get("material_type", "")
                    if mt:
                        material_counter[mt.lower()] += 1

    # Build distributions
    def _to_ratio(counter: Counter) -> Dict[str, float]:
        total = sum(counter.values())
        if total == 0:
            return {}
        return {k: round(v / total, 3) for k, v in counter.most_common(20)}

    color_total = sum(color_counter.values()) or 1
    color_dist = [
        ColorDistribution(hex=c, frequency=cnt, coverage=round(cnt / color_total, 3))
        for c, cnt in color_counter.most_common(15)
    ]

    kw_total = sum(keyword_counter.values()) or 1
    kw_freq = [
        KeywordFrequency(keyword=k, count=cnt, coverage=round(cnt / kw_total, 3))
        for k, cnt in keyword_counter.most_common(30)
    ]

    return IGDatasetAggregate(
        source_type="ig_references",
        source_account=source_account,
        source_collection=source_collection,
        observation_count=n,
        color_distribution=color_dist,
        keyword_frequency=kw_freq,
        camera_tech_distribution=_to_ratio(focal_counter),
        scene_type_distribution=_to_ratio(location_counter),
        subject_archetype_distribution=_to_ratio(archetype_counter),
        shot_type_distribution=_to_ratio(shot_type_counter),
        dominant_moods=[m for m, _ in mood_counter.most_common(5)],
        material_palette=[m for m, _ in material_counter.most_common(10)],
        aggregated_at=datetime.now(timezone.utc).isoformat(),
    )
