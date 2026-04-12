"""Vision Analysis Schema v2.1 — Pydantic model for structured vision output.

Core tiers (v1.0, always populated):
  Scene: overall composition, lighting, setting, mood
  Object: detected objects with confidence + bounding region
  Style: color palette, typography, visual techniques
  Insights: reverse prompt, engagement, hashtags, brands

Extended tiers (v2.0+, optional — populated based on analysis_profile):
  Subjects: per-person structured attributes (body, hair, clothing, pose)
  CameraTech: focal length, depth of field, shot type, framing
  Environment: location type, spatial layers, lighting, time of day
  Material: material identification, surface finish (for product analysis)
  SafetyFlags: content safety / compliance signals

Used by ig_analyze_reference tool with prompt-forced JSON + Pydantic validation.
Schema enforcement is transitional (json_object + post-hoc validation).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)
_SCHEMA_KEYS = ("scene", "objects", "style", "insights")

# ---------------------------------------------------------------------------
# Core Tiers (v1.0)
# ---------------------------------------------------------------------------


class SceneAnalysis(BaseModel):
    """Tier 1: Scene-level analysis."""

    composition: str = ""
    lighting: str = ""
    setting: str = ""
    mood: str = ""
    camera_angle: str = ""
    summary: str = ""
    evidence_notes: List[str] = Field(default_factory=list)


class DetectedObject(BaseModel):
    """Single detected object."""

    label: str
    confidence: float = 0.0
    region: str = ""  # e.g. "center", "top-left", "background"


class ObjectAnalysis(BaseModel):
    """Tier 2: Object-level analysis."""

    objects: List[DetectedObject] = Field(default_factory=list)
    dominant_subject: str = ""
    object_count: int = 0


class StyleAnalysis(BaseModel):
    """Tier 3: Style analysis."""

    color_palette: List[str] = Field(default_factory=list)
    dominant_colors: List[str] = Field(default_factory=list)
    typography: str = ""
    visual_techniques: List[str] = Field(default_factory=list)
    aesthetic_tags: List[str] = Field(default_factory=list)
    instagram_style: str = ""  # e.g. "flat-lay", "lifestyle", "studio"


class InsightAnalysis(BaseModel):
    """Tier 4: Insight analysis."""

    reverse_prompt: str = ""
    engagement: str = ""
    hashtags: List[str] = Field(default_factory=list)
    brands: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Extended Tiers (v2.0, optional)
# ---------------------------------------------------------------------------


class HairDescription(BaseModel):
    """Hair attributes."""

    color: str = ""
    length: str = ""  # short / medium / long
    style: str = ""  # straight / wavy / curly / braided / updo
    texture: str = ""  # fine / thick / coarse


class ClothingItem(BaseModel):
    """Single clothing item."""

    garment_type: str = ""  # top / bottom / dress / outerwear / swimwear
    color: str = ""
    material: str = ""  # cotton / denim / silk / leather / knit
    fit: str = ""  # slim / relaxed / oversized
    style_era: str = ""  # modern / vintage / streetwear / classic


class PoseDescription(BaseModel):
    """Body pose attributes."""

    stance: str = ""  # standing / sitting / lying / walking / leaning
    gesture: str = ""  # hands-in-pockets / holding-object / arms-crossed
    gaze_direction: str = ""  # camera / away / down / profile
    body_orientation: str = ""  # frontal / three-quarter / profile / back


class SubjectCoverage(BaseModel):
    """Visibility / coverage state for body regions that affect downstream semantics."""

    upper_body_coverage: str = ""  # covered / partially_covered / bare / not_visible / unknown
    lower_body_coverage: str = ""  # covered / partially_covered / bare / not_visible / unknown
    chest_visibility: str = ""  # visible / partially_visible / covered / not_visible / unknown
    chest_coverage_method: str = ""  # garment / hands / hair / prop / pose / unknown
    coverage_notes: str = ""


class SubjectProfile(BaseModel):
    """Per-person structured attributes."""

    gender_presentation: str = ""  # masculine / feminine / androgynous
    estimated_age_range: str = ""  # e.g. "20-25"
    body_type: str = ""  # athletic / slim / curvy / petite / tall
    skin_tone: str = ""  # fair / medium / olive / tan / dark
    perceived_ethnicity: str = ""  # east-asian / south-asian / caucasian / hispanic / african-descent / middle-eastern / mixed / uncertain
    face_shape: str = ""  # oval / round / square / heart / diamond / oblong / angular
    facial_features: str = ""  # objective description of eyes, nose, lips, eyebrows, jawline
    hair: HairDescription = Field(default_factory=HairDescription)
    clothing: List[ClothingItem] = Field(default_factory=list)
    accessories: List[str] = Field(default_factory=list)
    coverage: SubjectCoverage = Field(default_factory=SubjectCoverage)
    negative_observations: List[str] = Field(default_factory=list)
    evidence_notes: List[str] = Field(default_factory=list)
    pose: PoseDescription = Field(default_factory=PoseDescription)
    expression: str = ""  # neutral / smile / serious / playful / dramatic
    archetype_tags: List[str] = Field(default_factory=list)  # e.g. ["urban-professional"]

    @field_validator("accessories", mode="before")
    @classmethod
    def coerce_accessories(cls, v):
        """LLM sometimes returns accessories as dicts instead of strings."""
        if not isinstance(v, list):
            return v
        result = []
        for item in v:
            if isinstance(item, dict):
                # Extract the most descriptive field
                result.append(item.get("item", item.get("name", str(item))))
            else:
                result.append(str(item))
        return result


class FramingAnalysis(BaseModel):
    """Composition framing details."""

    rule_of_thirds: bool = False
    symmetry: bool = False
    leading_lines: bool = False
    negative_space_ratio: str = ""  # low / medium / high


class CameraTech(BaseModel):
    """Photography / cinematography technical parameters."""

    focal_length_class: str = ""  # ultra-wide / wide / standard / short-telephoto / telephoto
    focal_length_mm_range: str = ""  # e.g. "85-135mm"
    depth_of_field: str = ""  # shallow / moderate / deep
    estimated_aperture: str = ""  # e.g. "f/1.4-2.8"
    shutter_effect: str = ""  # frozen / slight-blur / motion-blur / long-exposure
    camera_movement: str = ""  # static / pan / dolly / handheld / stabilized
    framing: FramingAnalysis = Field(default_factory=FramingAnalysis)
    shot_type: str = ""  # extreme-close-up / close-up / medium-close-up / medium / full / wide
    aspect_ratio: str = ""  # 1:1 / 4:5 / 16:9 / 9:16
    evidence_notes: List[str] = Field(default_factory=list)


class PropItem(BaseModel):
    """Interactive prop."""

    name: str = ""
    usage: str = ""  # held / worn / resting-on / background
    region: str = ""  # center / left / right


class LightSource(BaseModel):
    """Light source analysis."""

    source_type: str = ""  # natural / artificial / mixed
    direction: str = ""  # front / side / back / overhead / ambient
    color_temperature: str = ""  # warm / neutral / cool
    intensity: str = ""  # soft / medium / hard


class EnvironmentContext(BaseModel):
    """Spatial / environment analysis."""

    location_type: str = ""  # indoor / outdoor / studio / hybrid
    location_subtype: str = ""  # cafe / apartment / rooftop / beach / forest / street
    foreground_elements: List[str] = Field(default_factory=list)
    midground_elements: List[str] = Field(default_factory=list)
    background_elements: List[str] = Field(default_factory=list)
    interactive_props: List[PropItem] = Field(default_factory=list)
    set_dressing: List[str] = Field(default_factory=list)
    light_source: LightSource = Field(default_factory=LightSource)
    time_of_day: str = ""  # golden-hour / blue-hour / noon / overcast / night / artificial
    weather_atmosphere: str = ""  # clear / cloudy / foggy / rainy
    evidence_notes: List[str] = Field(default_factory=list)


class ProductInteraction(BaseModel):
    """Product / brand interaction in the scene."""

    product_visible: bool = False
    product_category: str = ""  # cosmetics / fashion / food / tech / furniture
    interaction_type: str = ""  # held / worn / placed / used
    placement_region: str = ""  # center / foreground / background
    brand_visible: bool = False


class MaterialItem(BaseModel):
    """Material observation."""

    material_type: str = ""  # metal / wood / fabric / glass / leather / ceramic / plastic
    surface_finish: str = ""  # matte / glossy / brushed / textured
    region: str = ""
    confidence: float = 0.0


class MaterialObservation(BaseModel):
    """Material / texture analysis."""

    materials: List[MaterialItem] = Field(default_factory=list)
    texture_notes: str = ""


class SafetyFlags(BaseModel):
    """Content safety / compliance signals."""

    nsfw_risk: str = "none"  # none / low / medium / high
    medical_claims: bool = False
    copyright_concerns: str = ""  # text describing any concerns, or empty


class TrainingAnnotations(BaseModel):
    """Per-image training suitability hints for first-pass dataset selection."""

    training_lane_hints: List[str] = Field(default_factory=list)
    training_readiness: str = ""  # keep / review / reject
    training_source_kind: str = ""  # real_ref / generated_consistency_aug / screenshot_capture / unknown
    dataset_mix_role: str = ""  # anchor / support / exclude
    identity_signal_strength: str = ""  # high / medium / low
    primary_subject_clarity: str = ""  # clear / ambiguous / cluttered / multi_subject
    subject_framing: str = ""  # face_close_up / portrait_close_up / upper_body / half_body / full_body / detail / group / wide_scene
    face_angle: str = ""  # front / three_quarter / profile / back / obscured / not_visible
    face_visibility: str = ""  # high / medium / low / none
    occlusion_level: str = ""  # none / low / medium / high
    style_strength: str = ""  # photographic / lightly_filtered / stylized / heavily_stylized
    identity_drift_risk: str = ""  # low / medium / high
    look_variant_level: str = ""  # core / mild_variant / strong_variant / extreme_variant
    style_tags: List[str] = Field(default_factory=list)
    quality_flags: List[str] = Field(default_factory=list)
    hard_blockers: List[str] = Field(default_factory=list)
    reject_reasons: List[str] = Field(default_factory=list)
    identity_cluster_hint: str = ""
    look_state_hint: str = ""
    training_notes: str = ""

    @field_validator(
        "training_lane_hints",
        "style_tags",
        "quality_flags",
        "hard_blockers",
        "reject_reasons",
        mode="before",
    )
    @classmethod
    def coerce_string_lists(cls, value):
        if not isinstance(value, list):
            return value
        normalized: List[str] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(str(item.get("label", item.get("name", item))))
            else:
                normalized.append(str(item))
        return normalized


# ---------------------------------------------------------------------------
# Combined Result
# ---------------------------------------------------------------------------


class VisionAnalysisResult(BaseModel):
    """Complete vision analysis output (v1.0 core + v2.1 optional extensions)."""

    schema_version: str = "1.0"
    # Core tiers (v1.0)
    scene: SceneAnalysis = Field(default_factory=SceneAnalysis)
    objects: ObjectAnalysis = Field(default_factory=ObjectAnalysis)
    style: StyleAnalysis = Field(default_factory=StyleAnalysis)

    @field_validator("objects", mode="before")
    @classmethod
    def coerce_objects(cls, v):
        if isinstance(v, list):
            return {"objects": v, "object_count": len(v), "dominant_subject": ""}
        return v
    insights: InsightAnalysis = Field(default_factory=InsightAnalysis)
    raw_description: str = ""
    # Extended tiers (v2.0, all optional — absent in old data)
    subjects: List[SubjectProfile] = Field(default_factory=list)
    camera_tech: Optional[CameraTech] = None
    environment: Optional[EnvironmentContext] = None
    product_interaction: Optional[ProductInteraction] = None
    material: Optional[MaterialObservation] = None
    safety_flags: Optional[SafetyFlags] = None
    training_annotations: Optional[TrainingAnnotations] = None
    uncertainty: float = 0.0


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

# v1.0 core prompt — backward compatible, always used as baseline
VISION_ANALYSIS_PROMPT_HEADER = """\
You are a visual evidence extractor for sociological research.
Your task: report what is VISIBLE in this image. Prioritize accuracy over completeness.

EVIDENCE RULES:
1. [OBSERVED] fields — report only what you directly see. Be specific and concrete.
2. [INFERRED] fields — may be deduced from visual clues. Be conservative.
3. If a field cannot be reliably determined, use "unknown" or "not_visible". This is ALWAYS preferred over guessing.
4. Do NOT fill fields just to look complete. An empty string or "unknown" is better than an incorrect value.
5. Lists (objects, clothing, accessories, hashtags) — include ALL items you actually observe.
6. object_count — the real number of distinct objects you detect.

ALLOWED ENUM VALUES (pick ONE, or use "unknown" / "not_visible"):
- gender_presentation: masculine | feminine | androgynous | unknown
- body_type: athletic | slim | curvy | petite | tall | average | unknown | not_visible
- skin_tone: fair | medium | olive | tan | dark | unknown
- perceived_ethnicity: east-asian | south-asian | southeast-asian | caucasian | hispanic | african-descent | middle-eastern | mixed | uncertain
- face_shape: oval | round | square | heart | diamond | oblong | angular | unknown | not_visible
- expression: neutral | smile | serious | playful | dramatic | pensive | laughing | unknown
- hair.length: short | medium | long | not_visible
- hair.style: straight | wavy | curly | braided | updo | buzzed | not_visible
- pose.stance: standing | sitting | lying | walking | leaning | kneeling | crouching
- pose.gaze_direction: camera | away | down | up | profile
- pose.body_orientation: frontal | three-quarter | profile | back
- clothing.fit: slim | relaxed | oversized | tailored
- clothing.style_era: modern | vintage | streetwear | classic | bohemian
- coverage.upper_body_coverage: covered | partially_covered | bare | not_visible | unknown
- coverage.lower_body_coverage: covered | partially_covered | bare | not_visible | unknown
- coverage.chest_visibility: visible | partially_visible | covered | not_visible | unknown
- coverage.chest_coverage_method: garment | hands | hair | prop | pose | unknown
- focal_length_class: ultra-wide | wide | standard | short-telephoto | telephoto | unknown
- depth_of_field: shallow | moderate | deep
- shutter_effect: frozen | slight-blur | motion-blur | long-exposure
- shot_type: extreme-close-up | close-up | medium-close-up | medium | full | wide
- aspect_ratio: 1:1 | 4:5 | 16:9 | 9:16
- negative_space_ratio: low | medium | high
- location_type: indoor | outdoor | studio | hybrid | unknown
- time_of_day: golden-hour | blue-hour | noon | morning | afternoon | overcast | night | unknown
- weather_atmosphere: clear | cloudy | foggy | rainy | snowy | unknown
- light_source.source_type: natural | artificial | mixed
- light_source.direction: front | side | back | overhead | below | unknown
- light_source.color_temperature: warm | neutral | cool
- light_source.intensity: soft | medium | hard
- material_type: metal | wood | fabric | glass | leather | ceramic | plastic | stone | paper
- surface_finish: matte | glossy | brushed | textured | metallic | translucent
- training_readiness: keep | review | reject
- training_source_kind: real_ref | generated_consistency_aug | screenshot_capture | unknown
- dataset_mix_role: anchor | support | exclude
- identity_signal_strength: high | medium | low
- primary_subject_clarity: clear | ambiguous | cluttered | multi_subject
- subject_framing: face_close_up | portrait_close_up | upper_body | half_body | full_body | detail | group | wide_scene
- face_angle: front | three_quarter | profile | back | obscured | not_visible
- face_visibility: high | medium | low | none
- occlusion_level: none | low | medium | high
- style_strength: photographic | lightly_filtered | stylized | heavily_stylized
- identity_drift_risk: low | medium | high
- look_variant_level: core | mild_variant | strong_variant | extreme_variant

DON'T:
- Don't guess face_shape or body_type from a close-up where those are not visible
- Don't fill perceived_ethnicity if the face is obscured, too small, or ambiguous — use "uncertain"
- Don't assume time_of_day from color grading alone
- Don't invent brands or products that aren't clearly visible
- Don't copy any example text from this prompt

Return ONLY valid JSON with this structure:

{
  "scene": {
    "composition": "[OBSERVED] describe layout and framing",
    "lighting": "[OBSERVED] describe light quality, direction, color",
    "setting": "[OBSERVED] describe the environment",
    "mood": "[INFERRED] describe the emotional atmosphere",
    "camera_angle": "[OBSERVED] describe camera perspective",
    "summary": "[OBSERVED] one concise sentence",
    "evidence_notes": ["[OBSERVED/INFERRED] concise ambiguity or visibility note only when a dedicated field cannot express it"]
  },
  "objects": {
    "objects": [
      {"label": "object", "confidence": 0.95, "region": "center"}
    ],
    "dominant_subject": "[OBSERVED] main subject",
    "object_count": 0
  },
  "style": {
    "color_palette": ["#hex1", "#hex2"],
    "dominant_colors": ["color name"],
    "typography": "",
    "visual_techniques": ["technique"],
    "aesthetic_tags": ["tag"],
    "instagram_style": "[INFERRED] style category"
  },
  "insights": {
    "reverse_prompt": "[INFERRED] detailed image recreation prompt",
    "engagement": "[INFERRED] why this drives engagement",
    "hashtags": ["#tag"],
    "brands": []
  },
  "raw_description": "[OBSERVED] vivid one-line description"
"""

# JSON schema example closing block
VISION_ANALYSIS_PROMPT_FOOTER = """\
}

ONLY output the JSON object. No markdown, no explanation.
Start with '{' immediately. Every value must reflect THIS specific image.
"""

# ---------------------------------------------------------------------------
# v2.0 extension fragments — appended when profile requires
# Each fragment includes a policy header comment for the model
# ---------------------------------------------------------------------------

VISION_PROMPT_SUBJECTS = """\
  "subjects": [
    {
      "gender_presentation": "[OBSERVED] enum",
      "estimated_age_range": "[INFERRED] e.g. 22-26",
      "body_type": "[OBSERVED if full body visible, else not_visible] enum",
      "skin_tone": "[OBSERVED] enum",
      "perceived_ethnicity": "[INFERRED — use uncertain if ambiguous] enum",
      "face_shape": "[OBSERVED if face clearly visible, else not_visible] enum",
      "facial_features": "[OBSERVED] describe eyes, nose, lips, eyebrows, jawline — only what is visible",
      "hair": {"color": "", "length": "[OBSERVED] enum", "style": "[OBSERVED] enum", "texture": ""},
      "clothing": [{"garment_type": "", "color": "", "material": "", "fit": "enum", "style_era": "enum"}],
      "accessories": [],
      "coverage": {
        "upper_body_coverage": "[OBSERVED] enum",
        "lower_body_coverage": "[OBSERVED] enum",
        "chest_visibility": "[OBSERVED] enum",
        "chest_coverage_method": "[OBSERVED] enum",
        "coverage_notes": "[OBSERVED] short note when body coverage semantics matter"
      },
      "negative_observations": ["[OBSERVED] missing or absent detail that materially affects interpretation"],
      "evidence_notes": ["[OBSERVED/INFERRED] concise coverage/visibility ambiguity note only when dedicated fields are insufficient"],
      "pose": {"stance": "[OBSERVED] enum", "gesture": "[OBSERVED] describe", "gaze_direction": "[OBSERVED] enum", "body_orientation": "[OBSERVED] enum"},
      "expression": "[OBSERVED] enum",
      "archetype_tags": ["[INFERRED] lifestyle label"]
    }
  ]\
"""

VISION_PROMPT_CAMERA_TECH = """\
  "camera_tech": {
    "focal_length_class": "[INFERRED] enum",
    "focal_length_mm_range": "[INFERRED] e.g. 50-85mm",
    "depth_of_field": "[OBSERVED] enum",
    "estimated_aperture": "[INFERRED] e.g. f/2.8",
    "shutter_effect": "[OBSERVED] enum",
    "camera_movement": "static",
    "framing": {"rule_of_thirds": true, "symmetry": false, "leading_lines": false, "negative_space_ratio": "[OBSERVED] enum"},
    "shot_type": "[OBSERVED] enum",
    "aspect_ratio": "[OBSERVED] enum",
    "evidence_notes": ["[OBSERVED/INFERRED] concise camera ambiguity note only when needed"]
  }\
"""

VISION_PROMPT_ENVIRONMENT = """\
  "environment": {
    "location_type": "[OBSERVED] enum",
    "location_subtype": "[OBSERVED] specific place type",
    "foreground_elements": ["[OBSERVED] list visible FG items"],
    "midground_elements": ["[OBSERVED] list visible MG items"],
    "background_elements": ["[OBSERVED] list visible BG items"],
    "interactive_props": [{"name": "", "usage": "held/worn/resting-on", "region": ""}],
    "set_dressing": [],
    "light_source": {"source_type": "[OBSERVED] enum", "direction": "[OBSERVED] enum", "color_temperature": "[OBSERVED] enum", "intensity": "[OBSERVED] enum"},
    "time_of_day": "[INFERRED — use unknown if ambiguous] enum",
    "weather_atmosphere": "[OBSERVED if outdoor, else unknown] enum",
    "evidence_notes": ["[OBSERVED/INFERRED] concise environment ambiguity note only when needed"]
  }\
"""

VISION_PROMPT_MATERIAL = """\
  "material": {
    "materials": [{"material_type": "[OBSERVED] enum", "surface_finish": "[OBSERVED] enum", "region": "", "confidence": 0.9}],
    "texture_notes": "[OBSERVED] describe visible textures"
  }\
"""

VISION_PROMPT_TRAINING_ANNOTATIONS = """\
  "training_annotations": {
    "training_lane_hints": ["identity_core_lora"],
    "training_readiness": "[INFERRED from visible training utility only] enum",
    "training_source_kind": "[INFERRED from source appearance only] enum",
    "dataset_mix_role": "[INFERRED from dataset usefulness only] enum",
    "identity_signal_strength": "[INFERRED from visible identity signal only] enum",
    "primary_subject_clarity": "[OBSERVED/INFERRED] enum",
    "subject_framing": "[OBSERVED] enum",
    "face_angle": "[OBSERVED] enum",
    "face_visibility": "[OBSERVED] enum",
    "occlusion_level": "[OBSERVED] enum",
    "style_strength": "[INFERRED from visible filtering/stylization] enum",
    "identity_drift_risk": "[INFERRED from visible look drift / strong styling risk] enum",
    "look_variant_level": "[INFERRED from visible look deviation only] enum",
    "style_tags": ["[OBSERVED/INFERRED] conservative style label such as pastel"],
    "quality_flags": ["[OBSERVED] text_overlay / screenshot / collage / multi_person / motion_blur / heavy_filter / extreme_lighting / crop_issue / low_resolution"],
    "hard_blockers": ["[OBSERVED] multi_person / face_too_small / severe_occlusion / ui_overlay / watermark / extreme_filter / unreadable_source"],
    "reject_reasons": ["[INFERRED] short reason only when training_readiness=reject"],
    "identity_cluster_hint": "[INFERRED] short loose cue label for same-person grouping, not a guaranteed global ID",
    "look_state_hint": "[INFERRED] short loose cue label for hair/makeup/look state, not a guaranteed global ID",
    "training_notes": "[INFERRED] concise note explaining why this image is useful or risky for training"
  }\
"""

# ---------------------------------------------------------------------------
# Profile policies — extraction rules per profile
# ---------------------------------------------------------------------------

_PROFILE_POLICIES: Dict[str, str] = {
    "portrait_deep": """\
PROFILE POLICY — Portrait Deep:
PRIORITY: subject details (face, expression, hair, clothing, pose). Be thorough on these.
SECONDARY: camera technique (DoF, focal length, framing).
RULE: If only head/shoulders visible, set body_type to "not_visible". Do not guess.""",

    "cinematic": """\
PROFILE POLICY — Cinematic:
PRIORITY: camera technique (focal length, DoF, framing), lighting, spatial layers.
SECONDARY: subject body details.
RULE: Focus on technical cinematography. Do not write mood as marketing copy.""",

    "product_material": """\
PROFILE POLICY — Product Material:
PRIORITY: material identification, surface finish, object placement, lighting.
SECONDARY: human subject demographics.
RULE: If a person is present but not the focus, keep subject details minimal.""",

    "visual_anatomy": """\
PROFILE POLICY — Visual Anatomy (full analysis):
PRIORITY: equal weight across all sections.
RULE: Be thorough but never guess. Use "unknown" / "not_visible" freely.
RULE: archetype_tags should be conservative — 1-3 clear labels, not aspirational marketing.""",
}

# Profile -> prompt fragments mapping
VISION_PROMPT_PROFILES: Dict[str, List[str]] = {
    "aesthetic_core": [],  # v1.0 only — backward compatible
    "portrait_deep": ["subjects", "camera_tech"],
    "cinematic": ["camera_tech", "environment"],
    "product_material": ["material", "environment"],
    "visual_anatomy": ["subjects", "camera_tech", "environment", "material", "training_annotations"],
    "full": ["subjects", "camera_tech", "environment", "material", "training_annotations"],  # backward compat alias
}

_PROMPT_FRAGMENTS: Dict[str, str] = {
    "subjects": VISION_PROMPT_SUBJECTS,
    "camera_tech": VISION_PROMPT_CAMERA_TECH,
    "environment": VISION_PROMPT_ENVIRONMENT,
    "material": VISION_PROMPT_MATERIAL,
    "training_annotations": VISION_PROMPT_TRAINING_ANNOTATIONS,
}


def build_vision_prompt(profile: str = "aesthetic_core") -> str:
    """Build the vision analysis prompt for the given profile.

    Returns VISION_ANALYSIS_PROMPT_HEADER with optional v2.0 fragments appended,
    then closes the JSON block with VISION_ANALYSIS_PROMPT_FOOTER.
    Profile policy text is prepended when available.
    Unknown profiles fall back to aesthetic_core (v1.0 only).
    """
    fragments = VISION_PROMPT_PROFILES.get(profile, [])

    # Get profile policy if available
    policy = _PROFILE_POLICIES.get(profile, "")

    if not fragments:
        header = VISION_ANALYSIS_PROMPT_HEADER
        if policy:
            header = policy + "\n\n" + header
        return header + VISION_ANALYSIS_PROMPT_FOOTER

    header = VISION_ANALYSIS_PROMPT_HEADER
    if policy:
        header = policy + "\n\n" + header

    parts = [header.rstrip() + ","]
    
    valid_frags = []
    for frag_key in fragments:
        if frag_key in _PROMPT_FRAGMENTS:
            valid_frags.append(_PROMPT_FRAGMENTS[frag_key].rstrip())
            
    parts.append(",\n".join(valid_frags))
    parts.append(VISION_ANALYSIS_PROMPT_FOOTER)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Validation & auto-tag extraction
# ---------------------------------------------------------------------------


def validate_vision_output(raw_text: str) -> Optional[VisionAnalysisResult]:
    """Parse and validate free-text LLM output into structured schema.

    Handles three cases:
      1. Pure JSON response (ideal)
      2. Markdown fenced JSON block
      3. Mixed text with embedded JSON block (e.g. thinking + JSON)

    Returns validated VisionAnalysisResult or None if parsing fails.
    """
    # Strip <think>...</think> blocks from reasoning models (e.g. DeepSeek-R1)
    text = raw_text.strip()
    import re
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    attempt1_outcome = "not_run"

    # Attempt 1: direct parse (pure JSON)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            has_schema_keys = any(k in data for k in _SCHEMA_KEYS)
            if has_schema_keys:
                result = VisionAnalysisResult.model_validate(data)
                return result
            else:
                attempt1_outcome = "parsed_json_missing_schema_keys"
                logger.info(
                    "[VisionSchema] Attempt 1 parsed JSON but missing schema keys; "
                    "continuing to mixed-text extraction."
                )
        else:
            attempt1_outcome = "parsed_json_non_dict"
            logger.info(
                "[VisionSchema] Attempt 1 parsed JSON but it is not a dictionary; "
                "continuing to mixed-text extraction."
            )
    except Exception as e:
        attempt1_outcome = f"pure_json_failed:{e}"
        logger.info(
            "[VisionSchema] Attempt 1 (pure JSON) failed: %s; continuing to mixed-text extraction.",
            e,
        )

    # Attempt 2: find JSON block with schema keys in mixed text
    # Scan ALL balanced { } pairs and score validated candidates. Models often
    # repeat the prompt schema inside reasoning; those placeholder-heavy blocks
    # should lose to the final concrete answer near the end of the text.
    validated_candidates: List[tuple[float, int, int, VisionAnalysisResult]] = []
    fallback_candidates: List[tuple[int, int, Dict[str, Any], ValidationError]] = []
    for match in re.finditer(r'\{', text):
        start = match.start()
        depth = 0
        i = start
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        has_schema_keys = any(k in parsed for k in _SCHEMA_KEYS)
                        if has_schema_keys:
                            try:
                                result = VisionAnalysisResult.model_validate(parsed)
                                validated_candidates.append(
                                    (
                                        _score_validated_candidate(
                                            parsed=parsed,
                                            result=result,
                                            start=start,
                                            text_length=len(text),
                                        ),
                                        start,
                                        len(candidate),
                                        result,
                                    )
                                )
                            except ValidationError as err:
                                fallback_candidates.append(
                                    (start, len(candidate), parsed, err)
                                )
                    break  # move to next '{' position
            i += 1

    if validated_candidates:
        best_score, best_start, best_len, best_result = max(
            validated_candidates,
            key=lambda item: (item[0], item[1], item[2]),
        )
        logger.info(
            "[VisionSchema] Attempt 2 succeeded via mixed-text extraction "
            "(score=%.2f, start=%d, len=%d, candidates=%d, attempt1=%s)",
            best_score,
            best_start,
            best_len,
            len(validated_candidates),
            attempt1_outcome,
        )
        return best_result

    if fallback_candidates:
        _, _, best_data, first_error = max(
            fallback_candidates,
            key=lambda item: (item[0], item[1]),
        )
        try:
            result = VisionAnalysisResult.model_validate(best_data)
            logger.info(
                "[VisionSchema] Attempt 2 succeeded via mixed-text extraction "
                "(attempt1=%s)",
                attempt1_outcome,
            )
            return result
        except ValidationError as e:
            logger.warning(
                "[VisionSchema] Extracted JSON but strict validation failed "
                "(%d errors): %s",
                e.error_count(),
                e,
            )
            # Lenient retry: coerce types where possible
            try:
                # Strip fields that caused errors and retry
                cleaned = dict(best_data)
                for err in e.errors():
                    # Remove the problematic field path
                    loc = err.get("loc", ())
                    if loc and len(loc) == 1:
                        cleaned.pop(str(loc[0]), None)
                    elif loc and len(loc) >= 2:
                        # Nested field — remove the top-level container
                        # e.g. ('subjects', 0, 'hair', 'length') → keep subjects but skip
                        pass  # Don't remove entire nested containers
                result = VisionAnalysisResult.model_validate(cleaned)
                logger.info(
                    "[VisionSchema] Attempt 2 lenient validation succeeded after removing %d problematic fields "
                    "(attempt1=%s)",
                    e.error_count(),
                    attempt1_outcome,
                )
                return result
            except ValidationError as e2:
                logger.warning("[VisionSchema] Lenient validation also failed: %s", e2)
            logger.debug("[VisionSchema] First mixed-text validation error: %s", first_error)

    # No valid JSON found — reject instead of soft-accepting raw text.
    # Returning None causes _backfill to mark the job as failed, which is
    # correct: a raw_description-only result is not a valid schema analysis.
    logger.warning(
        "[VisionSchema] All parsing attempts failed (%d chars, attempt1=%s); "
        "rejecting final output (raw text will not be treated as successful analysis)",
        len(raw_text),
        attempt1_outcome,
    )
    return None


def _is_placeholder_like_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return text.startswith("[") and (
        "observed" in lowered
        or "inferred" in lowered
        or "enum" in lowered
        or "describe" in lowered
        or "list" in lowered
    )


def _is_meaningful_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if _is_placeholder_like_text(text):
        return False
    return text.lower() not in {"unknown", "not_visible"}


def _count_placeholder_strings(value: Any) -> int:
    if isinstance(value, str):
        return 1 if _is_placeholder_like_text(value) else 0
    if isinstance(value, list):
        return sum(_count_placeholder_strings(item) for item in value)
    if isinstance(value, dict):
        return sum(_count_placeholder_strings(item) for item in value.values())
    return 0


def _score_validated_candidate(
    *,
    parsed: Dict[str, Any],
    result: VisionAnalysisResult,
    start: int,
    text_length: int,
) -> float:
    score = 0.0

    for field in (
        result.raw_description,
        result.scene.composition,
        result.scene.summary,
        result.scene.setting,
        result.scene.lighting,
        result.insights.reverse_prompt,
        result.insights.engagement,
    ):
        if _is_meaningful_text(field):
            score += 6.0

    if result.objects.object_count:
        score += min(float(result.objects.object_count), 12.0)
    score += min(float(len(result.objects.objects)) * 0.5, 5.0)
    score += min(float(len(result.style.dominant_colors)) * 0.5, 3.0)
    score += min(float(len(result.subjects)) * 1.5, 6.0)

    if result.camera_tech and any(
        _is_meaningful_text(field)
        for field in (
            result.camera_tech.focal_length_class,
            result.camera_tech.depth_of_field,
            result.camera_tech.shot_type,
            result.camera_tech.aspect_ratio,
        )
    ):
        score += 2.0

    if result.environment and any(
        _is_meaningful_text(field)
        for field in (
            result.environment.location_type,
            result.environment.location_subtype,
            result.environment.time_of_day,
            result.environment.weather_atmosphere,
        )
    ):
        score += 2.0

    if result.material and (
        len(result.material.materials) > 0
        or _is_meaningful_text(result.material.texture_notes)
    ):
        score += 2.0

    for subject in result.subjects:
        coverage = subject.coverage
        if any(
            _is_meaningful_text(value)
            for value in (
                coverage.upper_body_coverage,
                coverage.lower_body_coverage,
                coverage.chest_visibility,
                coverage.chest_coverage_method,
                coverage.coverage_notes,
            )
        ):
            score += 2.5
        if len(subject.negative_observations) > 0:
            score += 2.0
        if len(subject.evidence_notes) > 0:
            score += 1.0

    if result.scene.evidence_notes:
        score += 0.5
    if result.camera_tech and result.camera_tech.evidence_notes:
        score += 0.5
    if result.environment and result.environment.evidence_notes:
        score += 0.5

    score -= float(_count_placeholder_strings(parsed)) * 4.0
    score += start / max(float(text_length), 1.0)
    return score


def extract_auto_tags(result: VisionAnalysisResult) -> List[str]:
    """Extract candidate auto-tags from vision analysis.

    Pulls from v1.0 core tiers and v2.0 extended tiers (when present).
    """
    tags: List[str] = []

    # From style (v1.0)
    tags.extend(result.style.aesthetic_tags)
    if result.style.instagram_style:
        tags.append(result.style.instagram_style)

    # From objects (v1.0)
    for obj in result.objects.objects:
        if obj.confidence >= 0.7:
            tags.append(obj.label.lower().replace(" ", "-"))

    # From scene (v1.0)
    if result.scene.mood:
        tags.append(result.scene.mood.lower().replace(" ", "-"))

    # From subjects (v2.0)
    for subj in result.subjects:
        tags.extend(subj.archetype_tags)
        if subj.expression and subj.expression != "neutral":
            tags.append(subj.expression.lower().replace(" ", "-"))

    # From camera_tech (v2.0)
    if result.camera_tech:
        if result.camera_tech.shot_type:
            tags.append(result.camera_tech.shot_type.lower().replace(" ", "-"))
        if result.camera_tech.focal_length_class:
            tags.append(result.camera_tech.focal_length_class.lower())

    # From environment (v2.0)
    if result.environment:
        if result.environment.location_type:
            tags.append(result.environment.location_type.lower())
        if result.environment.time_of_day:
            tags.append(result.environment.time_of_day.lower())

    return list(dict.fromkeys(tags))  # dedupe preserving order


# ---------------------------------------------------------------------------
# Tag vocabulary normalizer
# ---------------------------------------------------------------------------

_TAG_VOCABULARY: Optional[Dict[str, str]] = None


def _load_vocabulary() -> Dict[str, str]:
    """Load tag vocabulary from JSON file."""
    global _TAG_VOCABULARY
    if _TAG_VOCABULARY is not None:
        return _TAG_VOCABULARY

    vocab_path = Path(__file__).parent / "tag_vocabulary.json"
    if vocab_path.exists():
        with open(vocab_path, "r", encoding="utf-8") as f:
            _TAG_VOCABULARY = json.load(f)
    else:
        _TAG_VOCABULARY = {}

    return _TAG_VOCABULARY


def normalize_tags(tags: List[str]) -> List[str]:
    """Normalize tags using controlled vocabulary."""
    vocab = _load_vocabulary()
    normalized = []
    seen = set()

    for tag in tags:
        # Check if tag has a canonical form
        canonical = vocab.get(tag, tag)
        if canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)

    return normalized
