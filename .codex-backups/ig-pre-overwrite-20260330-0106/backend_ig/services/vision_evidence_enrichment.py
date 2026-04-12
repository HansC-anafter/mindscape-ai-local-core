"""Deterministic post-validation evidence enrichment from stored thinking/raw text.

This module is intentionally additive-only:
- never calls a model
- never overwrites non-empty structured values
- only fills evidence-bearing fields that the base JSON often drops
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, List, Sequence, Tuple

from capabilities.ig.models.vision_schema import ClothingItem, SubjectProfile


MISSING_NUMERIC_KEYS = {"confidence", "uncertainty"}
SUBJECT_NOUN_GENDER = {
    "woman": "feminine",
    "women": "feminine",
    "girl": "feminine",
    "girls": "feminine",
    "female": "feminine",
    "females": "feminine",
    "man": "masculine",
    "men": "masculine",
    "boy": "masculine",
    "boys": "masculine",
    "male": "masculine",
    "males": "masculine",
}
COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4}
COLOR_PATTERNS = [
    "black and white",
    "red and white",
    "blue and white",
    "light blue",
    "dark blue",
    "navy blue",
    "sky blue",
    "light pink",
    "dark green",
    "off white",
    "reddish-brown",
    "reddish brown",
    "brown",
    "cream",
    "white",
    "black",
    "yellow",
    "red",
    "blue",
    "green",
    "pink",
    "purple",
    "orange",
    "beige",
    "grey",
    "gray",
    "gold",
    "silver",
    "tan",
]
MATERIAL_PATTERNS = [
    "denim",
    "leather",
    "lace",
    "silk",
    "cotton",
    "linen",
    "knit",
    "knitted",
    "wool",
    "mesh",
    "satin",
    "velvet",
    "ribbed",
    "sheer",
]
GARMENT_PATTERNS = [
    ("long-sleeved top", "top"),
    ("long sleeved top", "top"),
    ("short-sleeved top", "top"),
    ("short sleeved top", "top"),
    ("tank top", "top"),
    ("crop top", "top"),
    ("tube top", "top"),
    ("off-shoulder top", "top"),
    ("off shoulder top", "top"),
    ("t-shirt", "t-shirt"),
    ("tee shirt", "t-shirt"),
    ("tee", "t-shirt"),
    ("shirt", "shirt"),
    ("blouse", "blouse"),
    ("top", "top"),
    ("sweater", "sweater"),
    ("hoodie", "hoodie"),
    ("cardigan", "cardigan"),
    ("jacket", "jacket"),
    ("coat", "coat"),
    ("dress", "dress"),
    ("gown", "dress"),
    ("sarong", "sarong"),
    ("wrap skirt", "sarong"),
    ("skirt", "skirt"),
    ("pants", "pants"),
    ("trousers", "pants"),
    ("jeans", "jeans"),
    ("shorts", "shorts"),
    ("leggings", "leggings"),
    ("stockings", "stockings"),
    ("bikini", "bikini"),
    ("swimsuit", "swimsuit"),
    ("bra", "bra"),
    ("robe", "robe"),
    ("uniform", "uniform"),
    ("jersey", "jersey"),
]
NEGATIVE_CLOTHING_MARKERS = [
    "shirtless",
    "topless",
    "bottomless",
    "naked",
    "nude",
    "bare-chested",
    "bare chested",
    "without a shirt",
    "without any shirt",
    "without clothes",
    "without clothing",
    "not wearing a top",
    "no top visible",
    "no bra visible",
]
SUBJECT_NOUN_PATTERN = (
    r"woman|women|girl|girls|female|females|man|men|boy|boys|male|males|"
    r"person|people|model|models|figure|figures|subject|subjects"
)
SINGULAR_SUBJECT_RE = re.compile(
    rf"\b(?P<label>one|another|the other|first|second|third)?\s*"
    rf"(?P<noun>{SUBJECT_NOUN_PATTERN})\b"
    rf"(?P<context>[^.!?\n]{{0,140}}?)\b"
    rf"(?:(?<!not )wearing|dressed in|wears|wore)\s+"
    rf"(?P<attire>[^.!?\n]+)",
    re.IGNORECASE,
)
PLURAL_SUBJECT_RE = re.compile(
    rf"\b(?P<count>one|two|three|four|\d+)\s+"
    rf"(?P<noun>women|girls|females|men|boys|males|people|models|figures|subjects)\b"
    rf"(?P<context>[^.!?\n]{{0,120}}?)\b"
    rf"(?:(?<!not )wearing|dressed in|wearing matching|dressed alike in)\s+"
    rf"(?P<attire>[^.!?\n]+)",
    re.IGNORECASE,
)
NEGATIVE_SUBJECT_RE = re.compile(
    rf"\b(?P<label>one|another|the other|first|second|third)?\s*"
    rf"(?P<noun>{SUBJECT_NOUN_PATTERN})\b"
    rf"(?P<context>[^.!?\n]{{0,120}}?)\b"
    rf"(?P<marker>shirtless|topless|bottomless|naked|nude|bare[- ]chested|"
    rf"without a shirt|without any shirt|without clothes|without clothing|"
    rf"not wearing a top|no top visible|no bra visible)\b",
    re.IGNORECASE,
)
PRONOUN_WEARING_RE = re.compile(
    r"\b(?:she|he|they)\b[^.!?\n]{0,40}\b(?:(?<!not )wearing|dressed in|wears|wore)\s+(?P<attire>[^.!?\n]+)",
    re.IGNORECASE,
)
PRONOUN_NEGATIVE_RE = re.compile(
    r"\b(?:she|he|they)\b[^.!?\n]{0,60}\b(?:shirtless|topless|bottomless|naked|nude|bare[- ]chested|"
    r"without a shirt|without any shirt|without clothes|without clothing|"
    r"not wearing a top|no top visible|no bra visible)\b",
    re.IGNORECASE,
)
HAND_CHEST_RE = re.compile(
    r"\bcover(?:ing|s|ed)?\s+(?:her|his|their)?\s*chest\b[^.!?\n]{0,40}\bwith\s+(?:her|his|their)?\s*(hands|arms)\b",
    re.IGNORECASE,
)
HAIR_CHEST_RE = re.compile(
    r"\b(?:hair|long hair)\b[^.!?\n]{0,40}\bcover(?:ing|s|ed)?\s+(?:her|his|their)?\s*chest\b",
    re.IGNORECASE,
)
PROP_CHEST_RE = re.compile(
    r"\bcover(?:ing|s|ed)?\s+(?:her|his|their)?\s*chest\b[^.!?\n]{0,40}\bwith\s+(?:a|an|the)?\s*(towel|fabric|blanket|prop|object|book|bag|flowers?)\b",
    re.IGNORECASE,
)
UNCERTAINTY_TERMS = (
    "likely",
    "maybe",
    "appears",
    "seems",
    "looks",
    "hard to",
    "uncertain",
    "ambiguous",
    "cannot tell",
    "can't tell",
    "not visible",
    "not_visible",
)
SUBJECT_RETENTION_TERMS = (
    "wearing",
    "dressed",
    "covering",
    "covered",
    "visible",
    "not visible",
    "top",
    "bra",
    "shirtless",
    "topless",
    "chest",
    "torso",
    "upper body",
    "lower body",
    "hands",
    "hair",
    "prop",
)
CAMERA_NOTE_TERMS = (
    "camera",
    "focal",
    "lens",
    "framing",
    "shot",
    "angle",
    "aperture",
    "depth of field",
    "dof",
    "handheld",
    "pan",
    "dolly",
    "zoom",
    "close-up",
    "wide shot",
)
ENV_NOTE_TERMS = (
    "indoor",
    "outdoor",
    "studio",
    "room",
    "beach",
    "street",
    "forest",
    "window",
    "curtain",
    "weather",
    "sunlight",
    "afternoon",
    "morning",
    "night",
    "background",
    "foreground",
    "midground",
)
SCENE_NOTE_TERMS = (
    "composition",
    "layout",
    "centered",
    "left",
    "right",
    "mood",
    "setting",
    "lighting",
    "summary",
)
UPPER_BODY_STATE_RE = re.compile(
    r"\b(?:upper body|upper-body|torso|chest)\b[^.!?\n]{0,40}\b(?:covered|uncovered|bare|hidden|obscured|occluded)\b",
    re.IGNORECASE,
)
LOWER_BODY_STATE_RE = re.compile(
    r"\b(?:lower body|lower-body|hips|legs)\b[^.!?\n]{0,40}\b(?:covered|uncovered|bare|hidden|obscured|occluded)\b",
    re.IGNORECASE,
)
APPEND_UNIQUE_LIST_FIELDS = {"negative_observations", "evidence_notes"}
UPPER_BODY_GARMENTS = {
    "top",
    "t-shirt",
    "shirt",
    "blouse",
    "sweater",
    "hoodie",
    "cardigan",
    "jacket",
    "coat",
    "bra",
}
LOWER_BODY_GARMENTS = {
    "sarong",
    "skirt",
    "pants",
    "jeans",
    "shorts",
    "leggings",
    "stockings",
}
FULL_BODY_GARMENTS = {"dress", "robe", "swimsuit", "bikini", "uniform"}


def _clean_text_block(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").split())


def _clean_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).strip(" ,.;:-")


def _split_sentences(text: str) -> List[str]:
    normalized = (text or "").replace("\r", "\n")
    return [
        sentence
        for sentence in (_clean_sentence(part) for part in re.split(r"(?:\n+|(?<=[.!?])\s+)", normalized))
        if sentence
    ]


def _dedupe_keep_order(values: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for raw in values:
        value = _clean_sentence(raw)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def _gender_from_noun(noun: str) -> str:
    return SUBJECT_NOUN_GENDER.get((noun or "").strip().lower(), "")


def _empty_subject(gender: str = "") -> Dict[str, Any]:
    subject = SubjectProfile().model_dump()
    if gender:
        subject["gender_presentation"] = gender
    return subject


def _find_color(text: str) -> str:
    lowered = f" {text.lower()} "
    for color in COLOR_PATTERNS:
        if f" {color} " in lowered:
            return color.replace("-", " ")
    return ""


def _find_material(text: str) -> str:
    lowered = f" {text.lower()} "
    for material in MATERIAL_PATTERNS:
        if f" {material} " in lowered:
            return "knit" if material == "knitted" else material
    return ""


def _extract_clothing_items(attire: str) -> List[Dict[str, Any]]:
    source = _clean_text_block(attire)
    if not source:
        return []

    lowered = source.lower()
    matches: List[Tuple[int, int, str]] = []
    for phrase, garment_type in GARMENT_PATTERNS:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        for match in pattern.finditer(lowered):
            matches.append((match.start(), match.end(), garment_type))
    if not matches:
        return []

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    filtered: List[Tuple[int, int, str]] = []
    last_end = -1
    for start, end, garment_type in matches:
        if start < last_end:
            continue
        filtered.append((start, end, garment_type))
        last_end = end

    items: List[Dict[str, Any]] = []
    for index, (_start, end, garment_type) in enumerate(filtered):
        next_start = filtered[index + 1][0] if index + 1 < len(filtered) else len(source)
        phrase_start = filtered[index - 1][1] if index > 0 else 0
        phrase = source[phrase_start:next_start].strip(" ,.")
        phrase = re.sub(r"^(?:and|with|in)\s+", "", phrase, flags=re.IGNORECASE)
        item = ClothingItem(
            garment_type=garment_type,
            color=_find_color(phrase),
            material=_find_material(phrase),
        ).model_dump()
        if item not in items:
            items.append(item)
    return items


def _apply_coverage_from_clothing(subject: Dict[str, Any]) -> None:
    coverage = subject.setdefault("coverage", {})
    garment_types = {
        (item or {}).get("garment_type", "").strip().lower()
        for item in subject.get("clothing") or []
        if isinstance(item, dict)
    }
    if not garment_types:
        return
    if not coverage.get("upper_body_coverage") and (
        garment_types & UPPER_BODY_GARMENTS or garment_types & FULL_BODY_GARMENTS
    ):
        coverage["upper_body_coverage"] = "covered"
    if not coverage.get("lower_body_coverage") and (
        garment_types & LOWER_BODY_GARMENTS or garment_types & FULL_BODY_GARMENTS
    ):
        coverage["lower_body_coverage"] = "covered"


def _apply_negative_coverage(subject: Dict[str, Any], text: str) -> None:
    lowered = (text or "").lower()
    coverage = subject.setdefault("coverage", {})
    negative = list(subject.get("negative_observations") or [])
    notes = list(subject.get("evidence_notes") or [])

    if any(marker in lowered for marker in NEGATIVE_CLOTHING_MARKERS):
        if "topless" in lowered or "shirtless" in lowered or "not wearing a top" in lowered or "no top visible" in lowered:
            if not coverage.get("upper_body_coverage"):
                coverage["upper_body_coverage"] = "bare"
            negative.append("no top visible")
        if "no bra visible" in lowered:
            negative.append("no bra visible")
        if "bottomless" in lowered:
            if not coverage.get("lower_body_coverage"):
                coverage["lower_body_coverage"] = "bare"
            negative.append("no bottom garment visible")
        if "nude" in lowered or "naked" in lowered or "without clothes" in lowered or "without clothing" in lowered:
            if not coverage.get("upper_body_coverage"):
                coverage["upper_body_coverage"] = "bare"
            if not coverage.get("lower_body_coverage"):
                coverage["lower_body_coverage"] = "bare"
            negative.append("minimal or no visible clothing")

    if HAND_CHEST_RE.search(text):
        if not coverage.get("chest_visibility"):
            coverage["chest_visibility"] = "covered"
        if not coverage.get("chest_coverage_method"):
            coverage["chest_coverage_method"] = "hands"
        if not coverage.get("coverage_notes"):
            coverage["coverage_notes"] = "Chest covered by hands or arms."
        notes.append("Chest is covered by hands or arms rather than a garment.")
    elif HAIR_CHEST_RE.search(text):
        if not coverage.get("chest_visibility"):
            coverage["chest_visibility"] = "covered"
        if not coverage.get("chest_coverage_method"):
            coverage["chest_coverage_method"] = "hair"
        if not coverage.get("coverage_notes"):
            coverage["coverage_notes"] = "Chest covered by hair."
        notes.append("Chest is covered by hair rather than a garment.")
    else:
        prop_match = PROP_CHEST_RE.search(text)
        if prop_match:
            if not coverage.get("chest_visibility"):
                coverage["chest_visibility"] = "covered"
            if not coverage.get("chest_coverage_method"):
                coverage["chest_coverage_method"] = "prop"
            if not coverage.get("coverage_notes"):
                coverage["coverage_notes"] = f"Chest covered by {prop_match.group(1)}."
            notes.append(f"Chest is covered by {prop_match.group(1)} rather than a garment.")

    subject["negative_observations"] = _dedupe_keep_order(negative)
    subject["evidence_notes"] = _dedupe_keep_order(notes)


def _parse_subjects_from_text(text: str) -> List[Dict[str, Any]]:
    source = _clean_text_block(text)
    if not source:
        return []

    subjects: List[Dict[str, Any]] = []
    singular_matches = list(SINGULAR_SUBJECT_RE.finditer(source))
    if singular_matches:
        seen_keys = set()
        for match in singular_matches:
            clothing = _extract_clothing_items(match.group("attire") or "")
            if not clothing:
                continue
            dedupe_key = (
                (match.group("label") or "").strip().lower() or "unlabeled",
                _gender_from_noun(match.group("noun") or ""),
                tuple(
                    (item.get("garment_type", ""), item.get("color", ""), item.get("material", ""))
                    for item in clothing
                ),
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            subject = _empty_subject(_gender_from_noun(match.group("noun") or ""))
            subject["clothing"] = clothing
            _apply_coverage_from_clothing(subject)
            _apply_negative_coverage(subject, match.group(0) or source)
            subjects.append(subject)
        if subjects:
            return subjects

    plural_matches = list(PLURAL_SUBJECT_RE.finditer(source))
    if plural_matches:
        for match in plural_matches:
            clothing = _extract_clothing_items(match.group("attire") or "")
            if not clothing:
                continue
            count_raw = (match.group("count") or "").lower()
            count = COUNT_WORDS.get(count_raw, 0)
            if not count and count_raw.isdigit():
                count = int(count_raw)
            count = max(1, min(count or 1, 4))
            gender = _gender_from_noun(match.group("noun") or "")
            for _ in range(count):
                subject = _empty_subject(gender)
                subject["clothing"] = deepcopy(clothing)
                _apply_coverage_from_clothing(subject)
                _apply_negative_coverage(subject, match.group(0) or source)
                subjects.append(subject)
        if subjects:
            return subjects

    seen_negative = set()
    for match in NEGATIVE_SUBJECT_RE.finditer(source):
        dedupe_key = (
            (match.group("label") or "").strip().lower() or "unlabeled",
            _gender_from_noun(match.group("noun") or ""),
        )
        if dedupe_key in seen_negative:
            continue
        seen_negative.add(dedupe_key)
        subject = _empty_subject(_gender_from_noun(match.group("noun") or ""))
        _apply_negative_coverage(subject, source)
        subjects.append(subject)

    if subjects:
        return subjects

    pronoun_subject: Dict[str, Any] | None = None
    pronoun_wearing = PRONOUN_WEARING_RE.search(source)
    if pronoun_wearing:
        clothing = _extract_clothing_items(pronoun_wearing.group("attire") or "")
        if clothing:
            pronoun_subject = _empty_subject()
            pronoun_subject["clothing"] = clothing
            _apply_coverage_from_clothing(pronoun_subject)

    pronoun_negative = PRONOUN_NEGATIVE_RE.search(source)
    if pronoun_negative:
        if pronoun_subject is None:
            pronoun_subject = _empty_subject()
        _apply_negative_coverage(pronoun_subject, source)

    if pronoun_subject:
        subjects.append(pronoun_subject)

    return subjects


def _is_missing(value: Any, path: Sequence[str]) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    if isinstance(value, (int, float)) and path and path[-1] in MISSING_NUMERIC_KEYS:
        return float(value) == 0.0
    return False


def _is_meaningful_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if text.startswith("[") and any(marker in lowered for marker in ("observed", "inferred", "enum", "describe", "list")):
        return False
    return lowered not in {"unknown", "not_visible"}


def _has_meaningful_payload(value: Any, path: Sequence[str] = ()) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return _is_meaningful_text(value)
    if isinstance(value, bool):
        return value is True
    if isinstance(value, (int, float)):
        if path and path[-1] in MISSING_NUMERIC_KEYS:
            return float(value) > 0.0
        return True
    if isinstance(value, list):
        return any(_has_meaningful_payload(item, path) for item in value)
    if isinstance(value, dict):
        return any(_has_meaningful_payload(item, (*path, str(key))) for key, item in value.items())
    return True


def _merge_additive(existing: Any, candidate: Any, path: Tuple[str, ...] = ()) -> Tuple[Any, List[Tuple[str, ...]]]:
    changes: List[Tuple[str, ...]] = []

    if isinstance(existing, dict) and isinstance(candidate, dict):
        merged = deepcopy(existing)
        for key, candidate_value in candidate.items():
            child_path = (*path, str(key))
            existing_value = merged.get(key)
            if key not in merged or _is_missing(existing_value, child_path):
                if _has_meaningful_payload(candidate_value, child_path):
                    merged[key] = deepcopy(candidate_value)
                    changes.append(child_path)
                continue
            merged_value, child_changes = _merge_additive(existing_value, candidate_value, child_path)
            merged[key] = merged_value
            changes.extend(child_changes)
        return merged, changes

    if isinstance(existing, list) and isinstance(candidate, list):
        if path and path[-1] in APPEND_UNIQUE_LIST_FIELDS:
            merged = _dedupe_keep_order([*(str(item) for item in existing), *(str(item) for item in candidate)])
            if merged != list(existing):
                return merged, [path]
            return deepcopy(existing), []
        if not candidate:
            return deepcopy(existing), []
        if not existing:
            if _has_meaningful_payload(candidate, path):
                return deepcopy(candidate), [path]
            return deepcopy(existing), []
        if (
            len(existing) == len(candidate)
            and all(isinstance(item, dict) for item in existing)
            and all(isinstance(item, dict) for item in candidate)
        ):
            merged_list: List[Any] = []
            for index, (existing_item, candidate_item) in enumerate(zip(existing, candidate)):
                merged_item, child_changes = _merge_additive(
                    existing_item,
                    candidate_item,
                    (*path, str(index)),
                )
                merged_list.append(merged_item)
                changes.extend(child_changes)
            return merged_list, changes
        return deepcopy(existing), []

    if _is_missing(existing, path) and _has_meaningful_payload(candidate, path):
        return deepcopy(candidate), [path]
    return deepcopy(existing), []


def _classify_sentence(sentence: str) -> str:
    lowered = sentence.lower()
    if any(term in lowered for term in CAMERA_NOTE_TERMS):
        return "camera"
    if any(term in lowered for term in ENV_NOTE_TERMS):
        return "environment"
    if any(term in lowered for term in SUBJECT_RETENTION_TERMS):
        return "subject"
    if any(term in lowered for term in SCENE_NOTE_TERMS):
        return "scene"
    return ""


def _should_keep_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    if any(term in lowered for term in UNCERTAINTY_TERMS):
        return any(
            term in lowered for term in CAMERA_NOTE_TERMS + ENV_NOTE_TERMS + SCENE_NOTE_TERMS + SUBJECT_RETENTION_TERMS
        )
    if any(marker in lowered for marker in NEGATIVE_CLOTHING_MARKERS):
        return True
    if HAND_CHEST_RE.search(sentence) or HAIR_CHEST_RE.search(sentence) or PROP_CHEST_RE.search(sentence):
        return True
    if UPPER_BODY_STATE_RE.search(sentence) or LOWER_BODY_STATE_RE.search(sentence):
        return True
    return False


def _extract_evidence_notes(text_blocks: List[str]) -> Dict[str, List[str]]:
    notes = {"scene": [], "subject": [], "camera": [], "environment": []}
    for block in text_blocks:
        for sentence in _split_sentences(block):
            if not _should_keep_sentence(sentence):
                continue
            bucket = _classify_sentence(sentence)
            if bucket:
                notes[bucket].append(sentence)
    # Subject evidence is limited to compact coverage/occlusion notes, not general demographics or identity guesses.
    notes["subject"] = [
        sentence
        for sentence in notes["subject"]
        if (
            HAND_CHEST_RE.search(sentence)
            or HAIR_CHEST_RE.search(sentence)
            or PROP_CHEST_RE.search(sentence)
            or UPPER_BODY_STATE_RE.search(sentence)
            or LOWER_BODY_STATE_RE.search(sentence)
            or any(marker in sentence.lower() for marker in NEGATIVE_CLOTHING_MARKERS)
        )
    ]
    return {key: _dedupe_keep_order(value)[:4] for key, value in notes.items()}


def _build_candidate_from_text(text_blocks: List[str]) -> Dict[str, Any]:
    candidate: Dict[str, Any] = {}
    subject_candidate: List[Dict[str, Any]] = []

    for block in text_blocks:
        subject_candidate = _parse_subjects_from_text(block)
        if subject_candidate:
            break

    evidence_notes = _extract_evidence_notes(text_blocks)
    if evidence_notes["scene"]:
        candidate.setdefault("scene", {})["evidence_notes"] = evidence_notes["scene"]
    if evidence_notes["camera"]:
        candidate.setdefault("camera_tech", {})["evidence_notes"] = evidence_notes["camera"]
    if evidence_notes["environment"]:
        candidate.setdefault("environment", {})["evidence_notes"] = evidence_notes["environment"]

    if subject_candidate:
        candidate["subjects"] = subject_candidate

    if evidence_notes["subject"]:
        if not candidate.get("subjects"):
            candidate["subjects"] = [_empty_subject()]
        first_subject = candidate["subjects"][0]
        first_subject["evidence_notes"] = _dedupe_keep_order(
            list(first_subject.get("evidence_notes") or []) + evidence_notes["subject"]
        )

    return candidate


def enrich_vision_with_evidence(
    vision: Dict[str, Any],
    *,
    thinking_text: str = "",
    raw_text: str = "",
) -> Tuple[Dict[str, Any], List[str]]:
    """Add evidence-bearing fields from stored prose without overwriting canonical values."""
    if not isinstance(vision, dict):
        return vision, []

    text_blocks: List[str] = []
    if thinking_text and thinking_text.strip():
        text_blocks.append(thinking_text.strip())
    if raw_text and raw_text.strip() and raw_text.strip() not in text_blocks:
        text_blocks.append(raw_text.strip())
    if not text_blocks:
        return deepcopy(vision), []

    candidate = _build_candidate_from_text(text_blocks)
    if not candidate:
        return deepcopy(vision), []

    merged, changes = _merge_additive(vision, candidate)
    formatted_changes = []
    for path in changes:
        label = ""
        for segment in path:
            label = f"{label}.{segment}" if label and not segment.isdigit() else (f"{label}[{segment}]" if segment.isdigit() else segment)
        formatted_changes.append(label)
    return merged, formatted_changes


def has_subject_retention_cues(*texts: str) -> bool:
    """Detect strong absence/coverage/occlusion cues that require paired retention."""
    for text in texts:
        if not text:
            continue
        for sentence in _split_sentences(text):
            lowered = sentence.lower()
            if any(marker in lowered for marker in NEGATIVE_CLOTHING_MARKERS):
                return True
            if HAND_CHEST_RE.search(sentence) or HAIR_CHEST_RE.search(sentence) or PROP_CHEST_RE.search(sentence):
                return True
            if UPPER_BODY_STATE_RE.search(sentence) or LOWER_BODY_STATE_RE.search(sentence):
                return True
    return False


def has_subject_paired_retention(vision: Dict[str, Any]) -> bool:
    """Check whether structured output retained coverage/absence semantics for a subject."""
    subjects = (vision or {}).get("subjects") or []
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        coverage = subject.get("coverage") or {}
        if any(
            str(coverage.get(field, "")).strip()
            for field in (
                "upper_body_coverage",
                "lower_body_coverage",
                "chest_visibility",
                "chest_coverage_method",
                "coverage_notes",
            )
        ):
            return True
        if subject.get("negative_observations"):
            return True
        if subject.get("evidence_notes"):
            return True
    return False
