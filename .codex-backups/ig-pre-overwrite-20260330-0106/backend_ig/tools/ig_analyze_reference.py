"""
ig_analyze_reference — Preprocess a single reference image for structured vision analysis.

Reads the pinned image, converts to base64, and prepares input for
core_llm.multimodal_analyze with the 3-tier structured prompt.

Playbook pattern:
  Step 1: ig.ig_analyze_reference (this tool — preprocess + prepare)
  Step 2: core_llm.multimodal_analyze (vision LLM call)
  Step 3: ig.ig_analyze_reference with mode=backfill (validate + store results)

Schema enforcement: prompt-forced JSON + Pydantic validation post-hoc.
Model routing managed centrally via system settings / CapabilityProfileResolver.
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from capabilities.ig.models.reference_metadata import (
    AnalysisProvenance,
    AnalysisDebug,
    ReferenceMetadata,
)
from capabilities.ig.models.vision_schema import (
    VISION_ANALYSIS_PROMPT_HEADER,
    VISION_ANALYSIS_PROMPT_FOOTER,
    build_vision_prompt,
    extract_auto_tags,
    normalize_tags,
    validate_vision_output,
)
from capabilities.ig.services.reference_index import ReferenceIndex
from capabilities.ig.services.vision_evidence_enrichment import (
    enrich_vision_with_evidence,
    has_subject_paired_retention,
    has_subject_retention_cues,
)
from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

# Supported image extensions
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_VISION_SCHEMA_KEYS = ("scene", "objects", "style", "insights")


def _base64_size_bytes(b64_text: str) -> int:
    """Estimate decoded byte length from base64 text without decoding payload."""
    text = (b64_text or "").strip()
    if not text:
        return 0
    padding = text[-2:].count("=")
    return max(0, (len(text) * 3) // 4 - padding)


def _make_analysis_excerpt(raw_text: str, limit: int = 220) -> str:
    """Build a compact single-line excerpt for cards and list views."""
    collapsed = " ".join((raw_text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _find_schema_json_block_bounds(raw_text: str) -> Optional[tuple[int, int]]:
    """Locate the largest embedded JSON object that looks like a vision schema payload."""
    text = raw_text or ""
    if "{" not in text:
        return None

    best_bounds: Optional[tuple[int, int]] = None
    best_len = 0

    for match in re.finditer(r"\{", text):
        start = match.start()
        depth = 0
        i = start
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    if len(candidate) > best_len:
                        try:
                            parsed = json.loads(candidate)
                        except json.JSONDecodeError:
                            break
                        if isinstance(parsed, dict) and any(
                            key in parsed for key in _VISION_SCHEMA_KEYS
                        ):
                            best_bounds = (start, i + 1)
                            best_len = len(candidate)
                    break
            i += 1

    return best_bounds


def _ocr_timeout_seconds() -> float:
    """Bound OCR latency so vision analysis can proceed without OCR."""
    raw = os.getenv("IG_ANALYZE_OCR_TIMEOUT_SECONDS", "10").strip()
    try:
        return max(0.0, float(raw))
    except Exception:
        return 10.0


async def _run_ocr_with_timeout(client: Any, image_path: str, timeout_seconds: float) -> Dict[str, Any]:
    """Run OCR with an explicit per-image timeout."""
    coro = client.ocr_image(image_path)
    if timeout_seconds <= 0:
        return await coro
    return await asyncio.wait_for(coro, timeout=timeout_seconds)


def extract_thinking_text(raw_text: str = "", thinking_text: str = "") -> str:
    """Normalize model reasoning and derive it from raw text when needed.

    Some MLX responses currently put reasoning into `description` and only leave a
    closing `</think>` marker before the final JSON payload. Others stream
    free-form reasoning followed by the final JSON object without any think tag.
    Preserve explicit `thinking` when available, otherwise infer the prose prefix.
    """

    def _clean(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        text = re.sub(r"^\s*<think>\s*", "", text, flags=re.DOTALL)
        text = re.sub(r"\s*</think>\s*$", "", text, flags=re.DOTALL)
        text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```(?:json)?\s*$", "", text, flags=re.IGNORECASE)
        return text.strip()

    def _is_meaningful_prefix(value: str) -> bool:
        collapsed = " ".join(value.split())
        if not collapsed or not re.search(r"\w", collapsed):
            return False
        if re.fullmatch(
            r"(?:here(?:'s| is)\s+)?(?:the\s+)?(?:json|output|response)(?:\s+below)?[:.]?",
            collapsed,
            flags=re.IGNORECASE,
        ):
            return False
        return True

    explicit = _clean(thinking_text)
    if explicit:
        return explicit

    raw = raw_text or ""
    if "</think>" in raw:
        prefix = _clean(raw.split("</think>", 1)[0])
        return prefix if _is_meaningful_prefix(prefix) else ""

    bounds = _find_schema_json_block_bounds(raw)
    if not bounds:
        return ""

    prefix = _clean(raw[: bounds[0]])
    return prefix if _is_meaningful_prefix(prefix) else ""


def capture_analysis_debug(
    raw_text: str = "",
    thinking_text: str = "",
    failure_stage: str = "",
    failure_reason: str = "",
) -> AnalysisDebug:
    """Capture debug payload independent from structured analysis success."""
    from datetime import datetime, timezone

    return AnalysisDebug(
        raw_text=raw_text or "",
        description_excerpt=_make_analysis_excerpt(raw_text),
        thinking_text=extract_thinking_text(raw_text=raw_text, thinking_text=thinking_text),
        failure_stage=failure_stage or "",
        failure_reason=failure_reason or "",
        captured_at=datetime.now(timezone.utc),
    )


_capture_analysis_debug = capture_analysis_debug


def _bbox_to_quadrant(bbox: list) -> str:
    """Convert OCR bbox to coarse spatial label.

    bbox format varies by OCR service; commonly [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    or [x1,y1,x2,y2]. Returns "top-left", "center", "bottom-right", etc.
    """
    try:
        if not bbox:
            return "unknown"
        # Flatten nested list if needed
        if isinstance(bbox[0], (list, tuple)):
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        elif len(bbox) >= 4:
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
        else:
            return "unknown"
        # Normalize to 0-1 range (assume typical image ~1000px)
        # Without image dimensions, use relative positioning heuristic
        v = "top" if cy < 400 else ("bottom" if cy > 700 else "mid")
        h = "left" if cx < 400 else ("right" if cx > 700 else "center")
        if v == "mid" and h == "center":
            return "center"
        return f"{v}-{h}"
    except Exception:
        return "unknown"


def _crop_bbox_to_b64(image_path: Path, bbox: list) -> Optional[str]:
    """Crop image to bbox and return base64 jpeg. 
    Option C: Send high-res text regions directly to VLM.
    """
    try:
        import base64
        import io
        from PIL import Image
        
        if not bbox:
            return None
            
        # Extract coordinates (handles [x,y,x,y] or [[x,y],[x,y],[x,y],[x,y]])
        if isinstance(bbox[0], (list, tuple)):
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        elif len(bbox) >= 4:
            x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        else:
            return None
            
        if x2 <= x1 or y2 <= y1:
            return None
            
        with Image.open(image_path) as img:
            # Add 10% padding for better context
            pad_x, pad_y = (x2 - x1) * 0.1, (y2 - y1) * 0.1
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(img.width, x2 + pad_x)
            y2 = min(img.height, y2 + pad_y)
            
            crop = img.crop((x1, y1, x2, y2))
            
            # Skip tiny crops
            if crop.width < 32 or crop.height < 32:
                return None
                
            if crop.mode in ('RGBA', 'P'):
                crop = crop.convert('RGB')
                
            buf = io.BytesIO()
            crop.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except ImportError:
        logger.warning("PIL not installed, cannot crop OCR bounding boxes")
        return None
    except Exception as e:
        logger.warning(f"Failed to crop bbox: {e}")
        return None


async def ig_analyze_reference(
    workspace_id: str,
    reference_id: str,
    mode: str = "preprocess",
    vision_result: Optional[Dict[str, Any]] = None,
    analysis_profile: str = "visual_anatomy",
    **kwargs,
) -> Dict[str, Any]:
    """Analyze a pinned reference image.

    Modes:
        preprocess: Read image, return base64 + prompt for multimodal_analyze.
        backfill: Validate vision result and write back to metadata.

    Args:
        workspace_id: Target workspace.
        reference_id: Reference to analyze.
        mode: "preprocess" or "backfill".
        vision_result: Raw vision LLM output (for backfill mode).

    Returns:
        Dict with images + prompt (preprocess) or analysis status (backfill).
    """
    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    # Find reference metadata file
    metadata_path = _find_metadata_file(refs_path, reference_id, index)
    if not metadata_path:
        return {"status": "error", "error": f"Reference {reference_id} not found"}

    if mode == "preprocess":
        return await _preprocess(metadata_path, reference_id, analysis_profile, index)
    elif mode == "backfill":
        return _backfill(metadata_path, reference_id, vision_result, index, analysis_profile)
    else:
        return {"status": "error", "error": f"Unknown mode: {mode}"}


async def _preprocess(
    metadata_path: Path,
    reference_id: str,
    analysis_profile: str = "visual_anatomy",
    index: Optional[ReferenceIndex] = None,
) -> Dict[str, Any]:
    """Read image and prepare for vision analysis."""
    request_id = f"igva_{uuid.uuid4().hex[:12]}"
    preprocess_started = time.perf_counter()
    try:
        meta = ReferenceMetadata.from_json(
            metadata_path.read_text(encoding="utf-8")
        )
    except Exception as e:
        return {"status": "error", "error": f"Failed to read metadata: {e}"}

    # Update job status to RUNNING
    if meta.analysis_job:
        meta.analysis_job.start()
        metadata_path.write_text(meta.to_json(), encoding="utf-8")
        if index is not None:
            index.add_entry(reference_id, meta.model_dump())

    # Find image file (same basename, image extension)
    image_path = _find_image_file(metadata_path)
    if not image_path:
        if meta.analysis_job:
            meta.analysis_job.fail("Image file not found for reference")
            metadata_path.write_text(meta.to_json(), encoding="utf-8")
            if index is not None:
                index.add_entry(reference_id, meta.model_dump())
        return {"status": "error", "error": "Image file not found for reference"}

    # Read and encode
    try:
        read_started = time.perf_counter()
        image_data = image_path.read_bytes()
        b64 = base64.b64encode(image_data).decode("ascii")
        read_source_ms = (time.perf_counter() - read_started) * 1000.0
    except Exception as e:
        if meta.analysis_job:
            meta.analysis_job.fail(f"Failed to read image: {e}")
            metadata_path.write_text(meta.to_json(), encoding="utf-8")
            if index is not None:
                index.add_entry(reference_id, meta.model_dump())
        return {"status": "error", "error": f"Failed to read image: {e}"}

    # Integrate OCR
    ocr_text = ""
    ocr_blocks = []
    ocr_started = time.perf_counter()
    try:
        from capabilities.core_files.services.ocr_client import get_ocr_client
        logger.info(f"[AnalyzeRef] Triggering OCR for {reference_id}")
        client = get_ocr_client()
        ocr_timeout = _ocr_timeout_seconds()
        ocr_res = await _run_ocr_with_timeout(client, str(image_path), ocr_timeout)
        if ocr_res:
            if ocr_res.get("blocks"):
                ocr_blocks = ocr_res["blocks"]
                logger.info(f"[AnalyzeRef] OCR succeeded, {len(ocr_blocks)} blocks")
            elif ocr_res.get("text") and str(ocr_res["text"]).strip():
                ocr_text = str(ocr_res["text"]).strip()
                logger.info(f"[AnalyzeRef] OCR succeeded, {len(ocr_text)} chars (plain text)")
    except asyncio.TimeoutError:
        logger.warning(
            "[AnalyzeRef] OCR timed out for %s after %.1fs; continuing without OCR",
            reference_id,
            _ocr_timeout_seconds(),
        )
    except Exception as e:
        logger.warning(f"[AnalyzeRef] OCR extraction failed for {reference_id}: {e}")
    ocr_ms = (time.perf_counter() - ocr_started) * 1000.0

    if ocr_blocks or ocr_text:
        from capabilities.ig.models.reference_metadata import AnalysisProvenance
        if not meta.analysis_provenance:
            meta.analysis_provenance = AnalysisProvenance(schema_version="", analysis_profile="")
        meta.analysis_provenance.ocr_used = True
        # Save back the flag
        metadata_path.write_text(meta.to_json(), encoding="utf-8")
        if index is not None:
            index.add_entry(reference_id, meta.model_dump())

    images_payload = [
        {
            "shortcode": meta.source_shortcode or reference_id,
            "base64_jpeg": b64,
        }
    ]

    prompt_build_ms = 0.0
    prompt_started = time.perf_counter()
    prompt = build_vision_prompt(analysis_profile)
    prompt_build_ms += (time.perf_counter() - prompt_started) * 1000.0
    ocr_crop_ms = 0.0
    ocr_crop_count = 0
    if ocr_blocks:
        # Position-aware OCR: include bbox quadrant + confidence
        ocr_lines = []
        for i, b in enumerate(ocr_blocks[:10]):
            conf = b.get("confidence", 0)
            if conf > 0.5:
                bbox = b.get("bbox", [])
                region = _bbox_to_quadrant(bbox) if bbox else "unknown"
                text = b.get("text", "")
                ocr_lines.append(f'  [{region}] "{text}" (conf={conf:.0%})')
                
                # Option C Two-pass Crop: Append high-conf regions as separate images
                # Limit to top 3 crops to save tokens, only if high confidence
                if i < 3 and bbox and conf > 0.7:
                    crop_started = time.perf_counter()
                    crop_b64 = _crop_bbox_to_b64(image_path, bbox)
                    ocr_crop_ms += (time.perf_counter() - crop_started) * 1000.0
                    if crop_b64:
                        ocr_crop_count += 1
                        images_payload.append({
                            "shortcode": f"{meta.source_shortcode or reference_id}_crop_{i}",
                            "base64_jpeg": crop_b64,
                        })

        if ocr_lines:
            prompt_enrich_started = time.perf_counter()
            prompt += "\n\n[OCR Text with Position]\n" + "\n".join(ocr_lines)
            prompt += "\n(Use these text elements for brand, typography, and hashtag identification.)"
            prompt_build_ms += (time.perf_counter() - prompt_enrich_started) * 1000.0
    elif ocr_text:
        prompt_enrich_started = time.perf_counter()
        prompt += f"\n\n[OCR Text Extracted from Image]\n{ocr_text}\n(Use this exact text if it helps identify brands, typography, or hashtags.)"
        prompt_build_ms += (time.perf_counter() - prompt_enrich_started) * 1000.0

    image_payload_total_bytes = sum(
        _base64_size_bytes(item.get("base64_jpeg", ""))
        for item in images_payload
    )
    telemetry = {
        "request_id": request_id,
        "reference_id": reference_id,
        "analysis_profile": analysis_profile,
        "source_bytes": len(image_data),
        "read_source_ms": round(read_source_ms, 3),
        "ocr_ms": round(ocr_ms, 3),
        "ocr_blocks_count": len(ocr_blocks),
        "ocr_text_chars": len(ocr_text),
        "ocr_crop_ms": round(ocr_crop_ms, 3),
        "ocr_crop_count": ocr_crop_count,
        "prompt_build_ms": round(prompt_build_ms, 3),
        "image_payload_count": len(images_payload),
        "image_payload_total_bytes": image_payload_total_bytes,
        "total_preprocess_ms": round((time.perf_counter() - preprocess_started) * 1000.0, 3),
    }
    logger.info(
        "[AnalyzeRef][Perf] request_id=%s reference_id=%s profile=%s read_source_ms=%.2f ocr_ms=%.2f "
        "ocr_blocks=%d ocr_crop_ms=%.2f ocr_crops=%d prompt_build_ms=%.2f payload_images=%d payload_bytes=%d total_preprocess_ms=%.2f",
        request_id,
        reference_id,
        analysis_profile,
        telemetry["read_source_ms"],
        telemetry["ocr_ms"],
        telemetry["ocr_blocks_count"],
        telemetry["ocr_crop_ms"],
        telemetry["ocr_crop_count"],
        telemetry["prompt_build_ms"],
        telemetry["image_payload_count"],
        telemetry["image_payload_total_bytes"],
        telemetry["total_preprocess_ms"],
    )

    return {
        "status": "ready",
        "reference_id": reference_id,
        "request_id": request_id,
        "images": images_payload,
        "prompt": prompt,
        "analysis_profile": analysis_profile,
        "_telemetry": telemetry,
    }


def _backfill(
    metadata_path: Path,
    reference_id: str,
    vision_result: Optional[Dict[str, Any]],
    index: ReferenceIndex,
    analysis_profile: str = "visual_anatomy",
) -> Dict[str, Any]:
    """Validate vision output and write back to metadata."""
    if not vision_result:
        return {"status": "error", "error": "No vision_result provided for backfill", "auto_tags": [], "scene_summary": "", "object_count": 0}

    try:
        meta = ReferenceMetadata.from_json(
            metadata_path.read_text(encoding="utf-8")
        )
    except Exception as e:
        return {"status": "error", "error": f"Failed to read metadata: {e}", "auto_tags": [], "scene_summary": "", "object_count": 0}

    import json
    import logging
    logger = logging.getLogger(__name__)

    if isinstance(vision_result, str):
        # The template engine might pass strings that contain python dict reprs, or double encoded json.
        # We try to clean it
        try:
            # Handle Python stringified dicts like "{'status': 'error'}"
            if vision_result.startswith("{") and "'" in vision_result and '"' not in vision_result:
                import ast
                vision_result = ast.literal_eval(vision_result)
            else:
                # Normal JSON unpack, potentially multiple times if double encoded
                while isinstance(vision_result, str):
                    logger.debug(f"[DEBUG IG ANALYZE] decoding step string: {vision_result}")
                    vision_result = json.loads(vision_result)
        except Exception as e:
            logger.error(f"[DEBUG IG ANALYZE] Decode error: {e}. Raw vision_result: {repr(vision_result)}")
            return {"status": "error", "error": f"Invalid JSON in vision_result: {e}", "auto_tags": [], "scene_summary": "", "object_count": 0}

    if not isinstance(vision_result, dict):
        # If it's STILL not a dict (e.g. they sent an int or plain string that evaluates to list), fail gracefully
        return {"status": "error", "error": f"vision_result must be a dict, got {type(vision_result)}", "auto_tags": [], "scene_summary": "", "object_count": 0}

    # Extract raw description text from multimodal_analyze output
    raw_text = ""
    thinking_text = ""
    results = vision_result.get("results", [])
    if results and isinstance(results, list):
        raw_text = results[0].get("description", "")
        thinking_text = extract_thinking_text(
            raw_text=raw_text,
            thinking_text=results[0].get("thinking", ""),
        )

    if not raw_text:
        meta.analysis_debug = _capture_analysis_debug(
            raw_text="",
            thinking_text=thinking_text,
            failure_stage="empty_vision_result",
            failure_reason="Empty vision result",
        )
        # Mark job as failed
        if meta.analysis_job:
            meta.analysis_job.fail("Empty vision result")
            if meta.analysis_job.can_retry():
                meta.analysis_job.reset_for_retry()
        metadata_path.write_text(meta.to_json(), encoding="utf-8")
        index.add_entry(reference_id, meta.model_dump())
        return {"status": "failed", "error": "Empty vision result", "auto_tags": [], "scene_summary": "", "object_count": 0}

    # Validate with Pydantic
    validated = validate_vision_output(raw_text)
    if not validated:
        meta.analysis_debug = _capture_analysis_debug(
            raw_text=raw_text,
            thinking_text=thinking_text,
            failure_stage="schema_validation",
            failure_reason="Vision output failed schema validation",
        )
        logger.error(f"[AnalyzeRef] Schema validation failed. RAW TEXT:\n{raw_text}\n---END RAW TEXT---")
        # Mark job as failed
        if meta.analysis_job:
            meta.analysis_job.fail("Schema validation failed")
            if meta.analysis_job.can_retry():
                meta.analysis_job.reset_for_retry()
        metadata_path.write_text(meta.to_json(), encoding="utf-8")
        index.add_entry(reference_id, meta.model_dump())
        return {"status": "failed", "error": "Vision output failed schema validation", "auto_tags": [], "scene_summary": "", "object_count": 0}

    # Content quality gate — reject structurally valid but empty results
    _rd = (validated.raw_description or "").strip()
    _comp = (validated.scene.composition or "").strip()
    _has_content = (
        (len(_rd) > 5 and not _rd.startswith("["))
        or (len(_comp) > 5 and not _comp.startswith("["))
    )
    if not _has_content:
        meta.analysis_debug = _capture_analysis_debug(
            raw_text=raw_text,
            thinking_text=thinking_text,
            failure_stage="content_quality_gate",
            failure_reason="Content quality gate failed",
        )
        logger.warning(
            "[AnalyzeRef] Content quality gate FAILED for %s — raw_description=%r, composition=%r",
            reference_id, _rd, _comp,
        )
        if meta.analysis_job:
            meta.analysis_job.fail("Content quality gate failed: all fields empty")
            if meta.analysis_job.can_retry():
                meta.analysis_job.reset_for_retry()
        metadata_path.write_text(meta.to_json(), encoding="utf-8")
        index.add_entry(reference_id, meta.model_dump())
        return {"status": "failed", "error": "Content quality gate failed", "auto_tags": [], "scene_summary": "", "object_count": 0}

    # Extract and normalize auto-tags
    raw_auto_tags = extract_auto_tags(validated)
    normalized = normalize_tags(raw_auto_tags)

    # Read ocr_used set by preprocess
    ocr_used = False
    if meta.analysis_provenance:
        ocr_used = meta.analysis_provenance.ocr_used

    meta.analysis_debug = _capture_analysis_debug(
        raw_text=raw_text,
        thinking_text=thinking_text,
    )

    # Write back to metadata
    vision_dict = validated.model_dump()
    evidence_changes: List[str] = []
    if analysis_profile != "aesthetic_core":
        vision_dict, evidence_changes = enrich_vision_with_evidence(
            vision_dict,
            thinking_text=thinking_text,
            raw_text=raw_text,
        )
        if has_subject_retention_cues(thinking_text, raw_text) and not has_subject_paired_retention(vision_dict):
            meta.analysis_debug = _capture_analysis_debug(
                raw_text=raw_text,
                thinking_text=thinking_text,
                failure_stage="semantic_retention_gate",
                failure_reason="Subject coverage/absence cues were not retained in schema",
            )
            logger.warning(
                "[AnalyzeRef] Semantic retention gate FAILED for %s — subject coverage cues present upstream but paired retention fields are missing",
                reference_id,
            )
            if meta.analysis_job:
                meta.analysis_job.fail("Semantic retention gate failed")
                if meta.analysis_job.can_retry():
                    meta.analysis_job.reset_for_retry()
            metadata_path.write_text(meta.to_json(), encoding="utf-8")
            index.add_entry(reference_id, meta.model_dump())
            return {
                "status": "failed",
                "error": "Semantic retention gate failed",
                "auto_tags": [],
                "scene_summary": "",
                "object_count": 0,
            }
    if thinking_text:
        # Backward-compatible mirror for older UI payloads.
        vision_dict["_thinking"] = thinking_text
    
    meta.training_annotations = vision_dict.get("training_annotations")
    meta.vision_description = vision_dict
    meta.auto_tags = normalized
    # Determine schema_version based on analysis_profile
    from datetime import datetime, timezone
    meta.analysis_provenance = AnalysisProvenance(
        model_id=vision_result.get("model_id", ""),
        validated_at=datetime.now(timezone.utc),
        analysis_profile=analysis_profile,
        prompt_version="v2.1" if analysis_profile != "aesthetic_core" else "v1.0",
        schema_version="1.0" if analysis_profile == "aesthetic_core" else "2.1",
        ocr_used=ocr_used,
        evidence_enriched=bool(evidence_changes),
        evidence_enrichment_version="thinking_additive@1.0" if evidence_changes else "",
    )
    if meta.analysis_job:
        meta.analysis_job.last_error = None
        meta.analysis_job.complete()

    metadata_path.write_text(meta.to_json(), encoding="utf-8")
    index.add_entry(reference_id, meta.model_dump())

    logger.info(
        "[AnalyzeRef] Backfilled %s: %d auto_tags, analysis COMPLETED",
        reference_id,
        len(normalized),
    )

    return {
        "status": "completed",
        "reference_id": reference_id,
        "auto_tags": normalized,
        "scene_summary": validated.scene.summary,
        "object_count": validated.objects.object_count,
        "training_annotations": meta.training_annotations,
    }


def _find_metadata_file(
    refs_path: Path, reference_id: str, index: ReferenceIndex
) -> Optional[Path]:
    """Find metadata JSON file for a reference_id."""
    # Try index first
    data = index._read_index()
    entry = data.get("entries", {}).get(reference_id)

    if entry:
        handle = entry.get("source_handle", "_unsorted")
        shortcode = entry.get("source_shortcode", "")
        if handle and not handle.startswith("_"):
            candidate = refs_path / handle / f"{shortcode}.json"
        else:
            candidate = refs_path / "_unsorted" / f"{shortcode}.json"
        if candidate.exists():
            return candidate

    # Fallback: scan filesystem
    for child in refs_path.iterdir():
        if not child.is_dir():
            continue
        for json_file in child.glob("*.json"):
            if json_file.name.startswith("_"):
                continue
            try:
                content = json.loads(json_file.read_text(encoding="utf-8"))
                if content.get("reference_id") == reference_id:
                    return json_file
            except Exception:
                continue

    return None


def _find_image_file(metadata_path: Path) -> Optional[Path]:
    """Find image file matching metadata (same basename, image extension)."""
    stem = metadata_path.stem
    for ext in _IMAGE_EXTS:
        candidate = metadata_path.parent / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None
