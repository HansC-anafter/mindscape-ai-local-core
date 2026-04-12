"""
References API — REST endpoints for pinned reference assets.

Endpoints:
  POST /pin                    — Pin a reference image
  GET  /                       — List references with filters
  GET  /{ref_id}/status        — Analysis job status
  GET  /{ref_id}/image         — Local pinned reference image
  GET  /{ref_id}/detail        — Full metadata detail
  POST /batch-retry-analysis   — Batch retry failed analyses
  POST /{ref_id}/assign-project — Assign reference to project
  POST /{ref_id}/use           — Link reference to post context
  DELETE /{ref_id}             — Soft-delete reference

Auth: workspace_id query param (follows insights_api.py pattern).
"""

import mimetypes
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.models.runtime_execution_intent import WorkloadExecutionIntent
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_validator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IG References"])

_REFERENCE_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def _dump_request_reference_execution_intent(req: Any) -> Optional[Dict[str, Any]]:
    canonical_intent = getattr(req, "workload_execution_intent", None)
    if canonical_intent is None:
        return None
    return canonical_intent.model_dump(
        mode="json",
        exclude_none=True,
    )


def _reject_legacy_reference_execution_override_fields(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw

    legacy_keys = [
        key
        for key in ("vision_execution_backend", "vision_target_device_id")
        if raw.get(key) is not None
    ]
    if legacy_keys:
        raise ValueError(
            "Deprecated fields "
            + ", ".join(sorted(legacy_keys))
            + " are no longer accepted; send workload_execution_intent instead."
        )
    return raw


def _normalize_status_text(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().upper()


def _task_status_to_analysis_status(value: Any) -> str:
    status = _normalize_status_text(value)
    if status in {"SUCCEEDED", "COMPLETED"}:
        return "COMPLETED"
    if status in {"FAILED", "CANCELLED", "CANCELLED_BY_USER", "EXPIRED"}:
        return "FAILED"
    if status == "RUNNING":
        return "RUNNING"
    if status in {"PENDING", "QUEUED", "PAUSED"}:
        return "PENDING"
    return status


def _resolve_reference_image_path(metadata_path: Path) -> Optional[Path]:
    base_path = metadata_path.with_suffix("")
    for suffix in _REFERENCE_IMAGE_SUFFIXES:
        candidate = base_path.with_suffix(suffix)
        if candidate.exists():
            return candidate
    return None


def _load_latest_reference_analysis_tasks(
    workspace_id: str,
    reference_ids: Optional[set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    try:
        from sqlalchemy import text
        from backend.app.services.stores.tasks_store import TasksStore

        wanted = sorted({ref_id for ref_id in (reference_ids or set()) if ref_id})
        tasks_store = TasksStore()
        query = """
            SELECT
                execution_id,
                parent_execution_id,
                status,
                error,
                created_at,
                COALESCE(execution_context->'inputs'->>'reference_id', '') AS reference_id
            FROM tasks
            WHERE workspace_id = :workspace_id
              AND pack_id = 'ig_analyze_pinned_reference'
              AND COALESCE(execution_context->'inputs'->>'reference_id', '') <> ''
        """
        params: Dict[str, Any] = {"workspace_id": workspace_id}
        if wanted:
            query += """
              AND COALESCE(execution_context->'inputs'->>'reference_id', '') = ANY(:reference_ids)
            """
            params["reference_ids"] = wanted
        query += """
            ORDER BY created_at DESC
        """
        with tasks_store.get_connection() as conn:
            rows = (
                conn.execute(
                    text(query),
                    params,
                )
                .mappings()
                .all()
            )
    except Exception as e:
        logger.warning("[RefAPI] Failed to load live reference analysis tasks: %s", e)
        return {}

    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        reference_id = str(row.get("reference_id") or "").strip()
        if not reference_id:
            continue
        if wanted and reference_id not in wanted:
            continue
        if reference_id in latest:
            continue
        latest[reference_id] = {
            "analysis_execution_id": row.get("execution_id"),
            "analysis_parent_execution_id": row.get("parent_execution_id"),
            "analysis_task_status": _task_status_to_analysis_status(row.get("status")),
            "analysis_task_error": row.get("error"),
        }
        if wanted and len(latest) >= len(wanted):
            break
    return latest


def _apply_live_reference_state(
    entry: Dict[str, Any],
    task_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    enriched = dict(entry)
    raw_status = _normalize_status_text(enriched.get("analysis_status"))
    live_status = _normalize_status_text((task_state or {}).get("analysis_task_status"))
    effective_status = live_status or raw_status or (
        "COMPLETED" if enriched.get("has_analysis") else "PENDING"
    )

    enriched["analysis_status"] = effective_status
    enriched["analysis_completed"] = effective_status == "COMPLETED"

    if task_state:
        enriched["analysis_execution_id"] = task_state.get("analysis_execution_id")
        enriched["analysis_task_status"] = task_state.get("analysis_task_status")
        if task_state.get("analysis_parent_execution_id"):
            enriched["analysis_parent_execution_id"] = task_state.get(
                "analysis_parent_execution_id"
            )
        if task_state.get("analysis_task_error") and not enriched.get("analysis_error"):
            enriched["analysis_error"] = task_state.get("analysis_task_error")

    return enriched


_PENDING_SORT_PAGE_SCAN_BATCH_SIZE = 200
_STATUS_FILTER_LIVE_SCAN_BATCH_SIZE = 500


def _reference_id(entry: Dict[str, Any]) -> str:
    return str(entry.get("reference_id") or "").strip()


def _resolve_explicit_status_filtered_results(
    *,
    results: List[Dict[str, Any]],
    workspace_id: str,
    analysis_status: str,
) -> List[Dict[str, Any]]:
    """Resolve explicit status filters against live task state.

    The reference index can lag behind the latest task state. If we pass an
    explicit analysis_status into the index query, refs whose live task state
    has already changed (for example, PENDING -> FAILED) can be filtered out
    before overlay. To keep account-detail post badges and the main references
    filter aligned, scan candidate refs in batches, apply live overlay, then
    filter by the effective status.
    """
    target_status = _task_status_to_analysis_status(analysis_status)
    if not target_status:
        return results

    filtered_results: List[Dict[str, Any]] = []
    cursor = 0

    while cursor < len(results):
        batch = results[cursor : cursor + _STATUS_FILTER_LIVE_SCAN_BATCH_SIZE]
        cursor += len(batch)
        batch_reference_ids = {
            _reference_id(entry)
            for entry in batch
            if isinstance(entry, dict) and _reference_id(entry)
        }
        batch_live_task_states = (
            _load_latest_reference_analysis_tasks(workspace_id, batch_reference_ids)
            if batch_reference_ids
            else {}
        )

        for entry in batch:
            reference_id = _reference_id(entry)
            enriched = _apply_live_reference_state(
                entry,
                batch_live_task_states.get(reference_id),
            )
            if _normalize_status_text(enriched.get("analysis_status")) == target_status:
                filtered_results.append(enriched)

    return filtered_results


def _resolve_pending_sorted_page(
    *,
    results: List[Dict[str, Any]],
    workspace_id: str,
    offset: int,
    limit: int,
) -> tuple[List[Dict[str, Any]], Optional[int], bool]:
    """Build a pending-only page after live task overlay.

    The reference index can lag behind task state. For pending-oriented sorts, a
    stale index entry may still say PENDING while the latest task state is now
    COMPLETED. Filter those out after overlay and keep scanning forward until the
    requested page is filled.
    """
    target_size = offset + limit
    effective_results: List[Dict[str, Any]] = []
    cursor = 0

    while cursor < len(results) and len(effective_results) < target_size:
        batch = results[cursor : cursor + _PENDING_SORT_PAGE_SCAN_BATCH_SIZE]
        cursor += len(batch)
        batch_reference_ids = {
            _reference_id(entry)
            for entry in batch
            if isinstance(entry, dict) and _reference_id(entry)
        }
        batch_live_task_states = (
            _load_latest_reference_analysis_tasks(workspace_id, batch_reference_ids)
            if batch_reference_ids
            else {}
        )

        for entry in batch:
            reference_id = _reference_id(entry)
            enriched = _apply_live_reference_state(
                entry,
                batch_live_task_states.get(reference_id),
            )
            if _normalize_status_text(enriched.get("analysis_status")) == "COMPLETED":
                continue
            effective_results.append(enriched)

    paged_results = effective_results[offset : offset + limit]
    effective_total = len(effective_results) if cursor >= len(results) else None
    if effective_total is not None:
        has_more = offset + len(paged_results) < effective_total
    else:
        has_more = len(paged_results) == limit and cursor < len(results)
    return paged_results, effective_total, has_more


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class PinRequest(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_execution_override_fields(cls, raw: Any) -> Any:
        return _reject_legacy_reference_execution_override_fields(raw)

    workspace_id: str
    image_url: str
    source_handle: str = ""
    source_shortcode: str = ""
    source_url: str = ""
    tags: List[str] = []
    collections: List[str] = []
    workload_execution_intent: Optional[WorkloadExecutionIntent] = None


class BatchRetryAnalysisRequest(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_execution_override_fields(cls, raw: Any) -> Any:
        return _reject_legacy_reference_execution_override_fields(raw)

    workspace_id: str
    reference_ids: List[str] = []  # empty = retry ALL matching filter_status
    filter_status: str = "FAILED"  # FAILED | PENDING | COMPLETED
    analysis_profile: str = "visual_anatomy"
    workload_execution_intent: Optional[WorkloadExecutionIntent] = None


class AssignProjectRequest(BaseModel):
    workspace_id: str
    project_id: str


class UseForPostRequest(BaseModel):
    workspace_id: str
    post_id: str
    role: str = "style_guide"  # style_guide | layout_reference | mood_board


class PinFromPostRequest(BaseModel):
    workspace_id: str
    shortcode: str = ""            # single shortcode
    shortcodes: List[str] = []     # batch mode
    source_handle: str = ""
    tags: List[str] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/pin")
async def pin_reference(req: PinRequest):
    """Pin a reference image to workspace assets."""
    from capabilities.ig.tools.ig_pin_reference import ig_pin_reference
    request_execution_intent = _dump_request_reference_execution_intent(req)

    result = await ig_pin_reference(
        workspace_id=req.workspace_id,
        image_url=req.image_url,
        source_handle=req.source_handle,
        source_shortcode=req.source_shortcode,
        source_url=req.source_url,
        tags=req.tags,
        collections=req.collections,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    # Fire-and-forget: enqueue background analysis (non-blocking)
    ref_id = result.get("reference_id", "")
    if ref_id and result.get("status") != "error":
        try:
            from capabilities.ig.services.auto_analyze import enqueue_reference_analysis

            exec_id = enqueue_reference_analysis(
                workspace_id=req.workspace_id,
                reference_id=ref_id,
                image_url=req.image_url,
                source_handle=req.source_handle,
                workload_execution_intent=request_execution_intent,
            )
            if exec_id:
                result["auto_analysis_execution_id"] = exec_id
        except Exception as e:
            logger.warning("[RefAPI] Auto-analyze enqueue failed (non-fatal): %s", e)

    return result


@router.get("")
@router.get("/")
def list_references(
    workspace_id: str = Query(..., description="Workspace ID"),
    source_handle: Optional[str] = Query(None),
    tag: Optional[str] = Query(None, description="Single tag filter"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    collection: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None, description="Project ID filter"),
    analysis_status: Optional[str] = Query(None, description="Filter by analysis status"),
    analysis_profile: Optional[str] = Query(None, description="Filter by analysis profile"),
    schema_version: Optional[str] = Query(None, description="Filter by schema version"),
    has_analysis: Optional[bool] = Query(None, description="Filter by analysis presence"),
    search: Optional[str] = Query(None, description="Free-text search"),
    sort_by: str = Query("analyzed_latest", description="Sort order"),
    include_counts: bool = Query(True, description="Return aggregate status counts"),
    limit: int = Query(60, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    # --- V2.0 projection filters (Phase 1) ---
    location: Optional[str] = Query(None, description="V2.0: location_type (indoor/outdoor/studio/hybrid)"),
    shot_type: Optional[str] = Query(None, description="V2.0: shot_type (close-up/medium/full/wide)"),
    focal_class: Optional[str] = Query(None, description="V2.0: focal_length_class (ultra-wide/wide/standard/telephoto)"),
    focal_mm: Optional[str] = Query(None, description="V2.0: focal length mm (e.g. 35mm)"),
    aperture: Optional[str] = Query(None, description="V2.0: estimated_aperture (e.g. f/1.4, f/2.8)"),
    dof: Optional[str] = Query(None, description="V2.0: depth_of_field (shallow/moderate/deep)"),
    light_temp: Optional[str] = Query(None, description="V2.0: light color_temperature (warm/neutral/cool)"),
    aspect_ratio: Optional[str] = Query(None, description="V2.0: aspect_ratio (4:5/1:1/16:9/9:16)"),
    stance: Optional[str] = Query(None, description="V2.0: pose stance (standing/sitting/leaning)"),
    gaze: Optional[str] = Query(None, description="V2.0: gaze_direction (camera/away/down/profile)"),
    expression: Optional[str] = Query(None, description="V2.0: expression (neutral/smile/serious/playful)"),
    archetype_tag: Optional[str] = Query(None, description="V2.0: subject archetype tag"),
    aesthetic_tag: Optional[str] = Query(None, description="V2.0: style aesthetic tag"),
    material: Optional[str] = Query(None, description="V2.0: material type (metal/wood/fabric/glass)"),
    training_readiness: Optional[str] = Query(None, description="Training: keep/review/reject"),
    training_lane_hint: Optional[str] = Query(None, description="Training: lane hint"),
    training_style_tag: Optional[str] = Query(None, description="Training: style tag"),
    training_quality_flag: Optional[str] = Query(None, description="Training: quality flag"),
    identity_cluster_hint: Optional[str] = Query(None, description="Training: identity cluster hint"),
    look_state_hint: Optional[str] = Query(None, description="Training: look state hint"),
):
    """List pinned references with optional filters including V2.0 schema projections."""
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage

    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    raw_tags = tags or tag
    tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else None

    pending_sort_active = (
        (sort_by or "").strip().lower() in {"pending_latest", "pending_oldest"}
        and not (analysis_status or "").strip()
    )
    explicit_status_filter_active = bool((analysis_status or "").strip())

    results = index.query(
        source_handle=source_handle,
        tags=tag_list,
        collection=collection,
        project_id=project_id,
        analysis_status=None if explicit_status_filter_active else analysis_status,
        analysis_profile=analysis_profile,
        schema_version=schema_version,
        has_analysis=has_analysis,
        search=search,
        sort_by=sort_by,
        # V2.0 projection filters
        location=location,
        shot_type=shot_type,
        focal_class=focal_class,
        focal_mm=focal_mm,
        aperture=aperture,
        dof=dof,
        light_temp=light_temp,
        aspect_ratio=aspect_ratio,
        stance=stance,
        gaze=gaze,
        expression=expression,
        archetype_tag=archetype_tag,
        aesthetic_tag=aesthetic_tag,
        material=material,
        training_readiness=training_readiness,
        training_lane_hint=training_lane_hint,
        training_style_tag=training_style_tag,
        training_quality_flag=training_quality_flag,
        identity_cluster_hint=identity_cluster_hint,
        look_state_hint=look_state_hint,
    )
    if explicit_status_filter_active:
        results = _resolve_explicit_status_filtered_results(
            results=results,
            workspace_id=workspace_id,
            analysis_status=analysis_status or "",
        )
    total = len(results)
    counts: Dict[str, Any] = {}
    if include_counts:
        count_results = results
        if pending_sort_active:
            count_results = index.query(
                source_handle=source_handle,
                tags=tag_list,
                collection=collection,
                project_id=project_id,
                analysis_status=analysis_status,
                analysis_profile=analysis_profile,
                schema_version=schema_version,
                has_analysis=has_analysis,
                search=search,
                sort_by="analyzed_latest",
                location=location,
                shot_type=shot_type,
                focal_class=focal_class,
                focal_mm=focal_mm,
                aperture=aperture,
                dof=dof,
                light_temp=light_temp,
                aspect_ratio=aspect_ratio,
                stance=stance,
                gaze=gaze,
                expression=expression,
                archetype_tag=archetype_tag,
                aesthetic_tag=aesthetic_tag,
                material=material,
                training_readiness=training_readiness,
                training_lane_hint=training_lane_hint,
                training_style_tag=training_style_tag,
                training_quality_flag=training_quality_flag,
                identity_cluster_hint=identity_cluster_hint,
                look_state_hint=look_state_hint,
            )

        count_reference_ids = {
            str(entry.get("reference_id") or "").strip()
            for entry in count_results
            if isinstance(entry, dict)
            and _normalize_status_text(entry.get("analysis_status")) != "COMPLETED"
        }
        count_live_task_states: Dict[str, Dict[str, Any]] = {}
        # Avoid reconciling all 10k+ refs on every page load. Large result sets use
        # canonical index metadata for top-bar counts; live task overlays are applied
        # to the current page only.
        if count_reference_ids and len(count_reference_ids) <= 200:
            count_live_task_states = _load_latest_reference_analysis_tasks(
                workspace_id,
                count_reference_ids,
            )
        reconciled_count_results = [
            _apply_live_reference_state(
                entry,
                count_live_task_states.get(str(entry.get("reference_id") or "").strip()),
            )
            for entry in count_results
        ]

        counts = {"total": len(count_results), "completed": 0, "running": 0, "pending": 0, "failed": 0}
        for entry in reconciled_count_results:
            status = str(entry.get("analysis_status", "")).strip().upper()
            if status == "COMPLETED":
                counts["completed"] += 1
            elif status == "RUNNING":
                counts["running"] += 1
            elif status == "FAILED":
                counts["failed"] += 1
            else:
                counts["pending"] += 1

    has_more = False
    if pending_sort_active:
        paged_results, effective_total, has_more = _resolve_pending_sorted_page(
            results=results,
            workspace_id=workspace_id,
            offset=offset,
            limit=limit,
        )
        if effective_total is not None:
            total = effective_total
    else:
        paged_slice = results[offset: offset + limit]
        page_reference_ids = {
            _reference_id(entry)
            for entry in paged_slice
            if isinstance(entry, dict)
            and _normalize_status_text(entry.get("analysis_status")) != "COMPLETED"
        }
        page_live_task_states = _load_latest_reference_analysis_tasks(
            workspace_id,
            page_reference_ids,
        ) if page_reference_ids else {}

        paged_results = [
            _apply_live_reference_state(
                entry,
                page_live_task_states.get(_reference_id(entry)),
            )
            for entry in paged_slice
        ]
        has_more = offset + len(paged_results) < total
    return {
        "references": paged_results,
        "total": total,
        "offset": offset,
        "limit": limit,
        "returned": len(paged_results),
        "has_more": has_more,
        "counts": counts,
    }


@router.get("/facets")
def get_reference_facets(
    workspace_id: str = Query(..., description="Workspace ID"),
    source_handle: Optional[str] = Query(None),
    tag: Optional[str] = Query(None, description="Single tag filter"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    collection: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None, description="Project ID filter"),
    analysis_status: Optional[str] = Query(None, description="Filter by analysis status"),
    analysis_profile: Optional[str] = Query(None, description="Filter by analysis profile"),
    schema_version: Optional[str] = Query(None, description="Filter by schema version"),
    has_analysis: Optional[bool] = Query(None, description="Filter by analysis presence"),
    search: Optional[str] = Query(None, description="Free-text search"),
    location: Optional[str] = Query(None),
    shot_type: Optional[str] = Query(None),
    focal_class: Optional[str] = Query(None),
    focal_mm: Optional[str] = Query(None),
    aperture: Optional[str] = Query(None),
    dof: Optional[str] = Query(None),
    light_temp: Optional[str] = Query(None),
    aspect_ratio: Optional[str] = Query(None),
    stance: Optional[str] = Query(None),
    gaze: Optional[str] = Query(None),
    expression: Optional[str] = Query(None),
    archetype_tag: Optional[str] = Query(None),
    aesthetic_tag: Optional[str] = Query(None),
    material: Optional[str] = Query(None),
    training_readiness: Optional[str] = Query(None),
    training_lane_hint: Optional[str] = Query(None),
    training_style_tag: Optional[str] = Query(None),
    training_quality_flag: Optional[str] = Query(None),
    identity_cluster_hint: Optional[str] = Query(None),
    look_state_hint: Optional[str] = Query(None),
):
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage

    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    raw_tags = tags or tag
    tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else None
    facets = index.query_facets(
        source_handle=source_handle,
        tags=tag_list,
        collection=collection,
        project_id=project_id,
        analysis_status=analysis_status,
        analysis_profile=analysis_profile,
        schema_version=schema_version,
        has_analysis=has_analysis,
        search=search,
        location=location,
        shot_type=shot_type,
        focal_class=focal_class,
        focal_mm=focal_mm,
        aperture=aperture,
        dof=dof,
        light_temp=light_temp,
        aspect_ratio=aspect_ratio,
        stance=stance,
        gaze=gaze,
        expression=expression,
        archetype_tag=archetype_tag,
        aesthetic_tag=aesthetic_tag,
        material=material,
        training_readiness=training_readiness,
        training_lane_hint=training_lane_hint,
        training_style_tag=training_style_tag,
        training_quality_flag=training_quality_flag,
        identity_cluster_hint=identity_cluster_hint,
        look_state_hint=look_state_hint,
    )
    return facets


@router.get("/{reference_id}/status")
@router.get("/{reference_id}/analysis-status")
def get_analysis_status(
    reference_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Get analysis job status for a reference."""
    import json
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage

    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    data = index._read_index()
    entry = data.get("entries", {}).get(reference_id)

    if not entry:
        raise HTTPException(status_code=404, detail=f"Reference {reference_id} not found")

    resolved = _apply_live_reference_state(
        entry,
        _load_latest_reference_analysis_tasks(workspace_id, {reference_id}).get(reference_id),
    )

    return {
        "reference_id": reference_id,
        "analysis_status": resolved.get("analysis_status", ""),
        "has_analysis": resolved.get("analysis_completed", False) or entry.get("has_analysis", False),
        "analysis_execution_id": resolved.get("analysis_execution_id"),
        "analysis_task_status": resolved.get("analysis_task_status"),
    }


@router.get("/{reference_id}/detail")
def get_reference_detail(
    reference_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Get full metadata detail for a reference."""
    from capabilities.ig.models.reference_metadata import ReferenceMetadata
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
    from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file

    try:
        storage = WorkspaceStorage(workspace_id, "ig")
        refs_path = storage.get_references_path()
        index = ReferenceIndex(refs_path)

        metadata_path = _find_metadata_file(refs_path, reference_id, index)
        if not metadata_path or not metadata_path.exists():
            raise HTTPException(status_code=404, detail="Reference metadata not found")

        meta = ReferenceMetadata.from_json(
            metadata_path.read_text(encoding="utf-8")
        )
        task_state = _load_latest_reference_analysis_tasks(workspace_id, {reference_id}).get(
            reference_id
        )
        analysis_job_payload = (
            meta.analysis_job.model_dump() if meta.analysis_job else None
        )
        if task_state:
            if analysis_job_payload is None:
                analysis_job_payload = {}
            analysis_job_payload["status"] = task_state.get("analysis_task_status")
            if task_state.get("analysis_execution_id"):
                analysis_job_payload["execution_id"] = task_state.get(
                    "analysis_execution_id"
                )
            if (
                task_state.get("analysis_task_error")
                and not analysis_job_payload.get("last_error")
            ):
                analysis_job_payload["last_error"] = task_state.get(
                    "analysis_task_error"
                )

        effective_status = _normalize_status_text(
            (analysis_job_payload or {}).get("status")
            or (meta.analysis_job.status if meta.analysis_job else "")
            or "NONE"
        )

        return {
            "reference_id": meta.reference_id,
            "source_handle": meta.source_handle,
            "source_shortcode": meta.source_shortcode,
            "tags": meta.tags,
            "auto_tags": meta.auto_tags,
            "training_annotations": meta.training_annotations
            or ((meta.vision_description or {}).get("training_annotations")),
            "analysis_status": effective_status,
            "analysis_completed": effective_status == "COMPLETED",
            "analysis_execution_id": (task_state or {}).get("analysis_execution_id"),
            "analysis_task_status": (task_state or {}).get("analysis_task_status"),
            "analysis_parent_execution_id": (task_state or {}).get(
                "analysis_parent_execution_id"
            ),
            "analysis_error": (task_state or {}).get("analysis_task_error")
            or (analysis_job_payload or {}).get("last_error"),
            "vision_description": meta.vision_description,
            "analysis_provenance": meta.analysis_provenance.model_dump() if meta.analysis_provenance else None,
            "analysis_job": analysis_job_payload,
            "analysis_debug": meta.analysis_debug.model_dump() if meta.analysis_debug else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[RefAPI] Failed to read metadata detail: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{reference_id}/image")
def get_reference_image(
    reference_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Serve the local pinned asset stored beside the reference metadata JSON."""
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
    from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file

    try:
        storage = WorkspaceStorage(workspace_id, "ig")
        refs_path = storage.get_references_path()
        index = ReferenceIndex(refs_path)

        metadata_path = _find_metadata_file(refs_path, reference_id, index)
        if not metadata_path or not metadata_path.exists():
            raise HTTPException(status_code=404, detail="Reference metadata not found")

        image_path = _resolve_reference_image_path(metadata_path)
        if not image_path or not image_path.exists():
            raise HTTPException(status_code=404, detail="Reference image not found")

        media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        return FileResponse(
            image_path,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[RefAPI] Failed to serve reference image: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-retry-analysis")
def batch_retry_analysis(req: BatchRetryAnalysisRequest):
    """Batch retry failed/pending analysis jobs.

    If reference_ids is empty, scans ALL references and retries those matching filter_status.
    """
    from capabilities.ig.models.reference_metadata import ReferenceMetadata
    from capabilities.ig.services.auto_analyze import enqueue_reference_analysis
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
    from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file

    storage = WorkspaceStorage(req.workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    data = index._read_index()
    entries = data.get("entries", {})

    # Determine which refs to retry
    target_ids = req.reference_ids
    if not target_ids:
        for ref_id, entry in entries.items():
            status = entry.get("analysis_status", "")
            if status == req.filter_status or (status == "" and req.filter_status in ("FAILED", "PENDING")):
                target_ids.append(ref_id)

    results = {"enqueued": [], "skipped": [], "errors": []}
    request_execution_intent = _dump_request_reference_execution_intent(req)

    # === Task Grouping: Wrap batch in a single parent execution ID ===
    import uuid

    batch_parent_id = f"batch-retry-{uuid.uuid4().hex[:8]}"
    results["batch_parent_id"] = batch_parent_id
    active_parent_execution_id = None
    _parent_ctx_token = None
    try:
        from backend.app.services.parameter_adapter.context import (
            active_parent_execution_id as _active_parent_execution_id,
        )

        active_parent_execution_id = _active_parent_execution_id
        _parent_ctx_token = active_parent_execution_id.set(batch_parent_id)
    except Exception:
        # Capability tests can run without the backend package loaded.
        pass
    
    try:
        for ref_id in target_ids:
            try:
                metadata_path = _find_metadata_file(refs_path, ref_id, index)
                if not metadata_path or not metadata_path.exists():
                    results["skipped"].append({"id": ref_id, "reason": "no metadata file"})
                    continue

                meta = ReferenceMetadata.from_json(
                    metadata_path.read_text(encoding="utf-8")
                )

                if meta.analysis_job:
                    if meta.analysis_job.status in ("FAILED", "PENDING", "RUNNING"):
                        meta.analysis_job.queue()
                        meta.analysis_job.last_error = None
                        meta.analysis_provenance = None
                    elif meta.analysis_job.status == "COMPLETED" and req.filter_status == "COMPLETED":
                        # Re-analyze COMPLETED refs without discarding the last
                        # good analysis. The next successful run will overwrite
                        # these fields; if it fails, the previous result stays
                        # visible instead of disappearing into a pending state.
                        meta.analysis_job.queue()
                        meta.analysis_job.last_error = None
                        meta.analysis_job.retry_count = 0
                    else:
                        results["skipped"].append({"id": ref_id, "reason": f"status={meta.analysis_job.status}"})
                        continue
                else:
                    if req.filter_status not in ("FAILED", "PENDING"):
                        results["skipped"].append({"id": ref_id, "reason": "status=None"})
                        continue
                    from capabilities.ig.models.reference_metadata import AnalysisJob
                    meta.analysis_job = AnalysisJob.create_pending()

                metadata_path.write_text(meta.to_json(), encoding="utf-8")

                # Sync _index.json immediately so list/filter sees PENDING state
                index.add_entry(ref_id, meta.model_dump())

                image_url = entries.get(ref_id, {}).get("image_url", meta.source_url or "")
                exec_id = enqueue_reference_analysis(
                    workspace_id=req.workspace_id,
                    reference_id=ref_id,
                    image_url=image_url,
                    source_handle=meta.source_handle,
                    analysis_profile=req.analysis_profile,
                    workload_execution_intent=request_execution_intent,
                )
                results["enqueued"].append({"id": ref_id, "execution_id": exec_id})

            except Exception as e:
                logger.warning("[RefAPI] batch-retry error for %s: %s", ref_id, e)
                results["errors"].append({"id": ref_id, "error": str(e)})

    finally:
        if active_parent_execution_id is not None and _parent_ctx_token is not None:
            active_parent_execution_id.reset(_parent_ctx_token)

    return {
        "status": "ok",
        "batch_parent_id": batch_parent_id,
        "total_enqueued": len(results["enqueued"]),
        "total_skipped": len(results["skipped"]),
        "total_errors": len(results["errors"]),
        "details": results,
    }


@router.post("/{reference_id}/assign-project")
def assign_reference_to_project(reference_id: str, req: AssignProjectRequest):
    """Assign a reference to a project (sets project_id on metadata)."""
    from capabilities.ig.models.reference_metadata import ReferenceMetadata
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
    from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file

    storage = WorkspaceStorage(req.workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    metadata_path = _find_metadata_file(refs_path, reference_id, index)
    if not metadata_path or not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Reference metadata not found")

    meta = ReferenceMetadata.from_json(metadata_path.read_text(encoding="utf-8"))
    meta.project_id = req.project_id
    metadata_path.write_text(meta.to_json(), encoding="utf-8")

    # Sync index
    index.update_entry_field(reference_id, "project_id", req.project_id)

    return {"status": "ok", "reference_id": reference_id, "project_id": req.project_id}


@router.post("/{reference_id}/use-for-post")
def use_for_post(reference_id: str, req: UseForPostRequest):
    """Link a reference to a post context (reference_id + content_hash, NOT file copy)."""
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage

    storage = WorkspaceStorage(req.workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    data = index._read_index()
    entry = data.get("entries", {}).get(reference_id)

    if not entry:
        raise HTTPException(status_code=404, detail=f"Reference {reference_id} not found")

    # Build reference_ref (to be stored in post context)
    reference_ref = {
        "reference_id": reference_id,
        "content_hash": entry.get("content_hash", ""),
        "role": req.role,
    }

    return {
        "status": "linked",
        "reference_ref": reference_ref,
        "message": f"Reference {reference_id} linked to post {req.post_id} as {req.role}",
    }


@router.delete("/{reference_id}")
def delete_reference(
    reference_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Soft-delete a reference (file retained, excluded from listings)."""
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
    from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file

    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    # Update metadata file
    from capabilities.ig.models.reference_metadata import ReferenceMetadata

    metadata_path = _find_metadata_file(refs_path, reference_id, index)
    if metadata_path and metadata_path.exists():
        try:
            meta = ReferenceMetadata.from_json(
                metadata_path.read_text(encoding="utf-8")
            )
            meta.soft_delete()
            metadata_path.write_text(meta.to_json(), encoding="utf-8")
        except Exception as e:
            logger.warning("[RefAPI] Failed to update metadata for delete: %s", e)

    # Update index
    index.remove_entry(reference_id, soft=True)

    return {
        "status": "deleted",
        "reference_id": reference_id,
        "message": "Soft-deleted. File retained on disk.",
    }


@router.post("/pin-from-post")
async def pin_from_post(req: PinFromPostRequest):
    """Pin reference(s) from post detail — fetches post via browser, extracts all carousel images."""
    from capabilities.ig.tools.ig_pin_post_detail import ig_pin_post_detail

    shortcodes = list(req.shortcodes)
    if req.shortcode and req.shortcode not in shortcodes:
        shortcodes.append(req.shortcode)

    if not shortcodes:
        raise HTTPException(status_code=400, detail="No shortcode(s) provided")

    result = await ig_pin_post_detail(
        workspace_id=req.workspace_id,
        shortcodes=shortcodes,
        source_handle=req.source_handle,
        tags=req.tags if req.tags else ["post_detail"],
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/{reference_id}/carousel-group")
def get_carousel_group(
    reference_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Get carousel siblings for a reference."""
    from capabilities.ig.models.reference_metadata import ReferenceMetadata
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
    from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file

    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    # Read the target reference to find carousel parent
    metadata_path = _find_metadata_file(refs_path, reference_id, index)
    if not metadata_path or not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Reference not found")

    meta = ReferenceMetadata.from_json(metadata_path.read_text(encoding="utf-8"))

    if meta.carousel_total is None or meta.carousel_total <= 1:
        return {
            "reference_id": reference_id,
            "is_carousel": False,
            "siblings": [],
        }

    # Determine parent ID
    parent_id = meta.carousel_parent_id or reference_id

    # Scan index for siblings with same carousel_parent_id or the parent itself
    data = index._read_index()
    entries = data.get("entries", {})
    siblings = []
    for ref_id, entry in entries.items():
        entry_parent = entry.get("carousel_parent_id")
        if ref_id == parent_id or entry_parent == parent_id:
            siblings.append({
                "reference_id": ref_id,
                "carousel_index": entry.get("carousel_index"),
                "source_shortcode": entry.get("source_shortcode", ""),
                "analysis_status": entry.get("analysis_status", ""),
            })

    siblings.sort(key=lambda x: x.get("carousel_index") or 0)

    return {
        "reference_id": reference_id,
        "is_carousel": True,
        "carousel_parent_id": parent_id,
        "carousel_total": meta.carousel_total,
        "siblings": siblings,
    }
