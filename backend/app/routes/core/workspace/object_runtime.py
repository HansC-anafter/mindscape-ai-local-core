"""Workspace-scoped runtime APIs for the Addressable Object Layer."""

from __future__ import annotations

import importlib
import inspect
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from fastapi.encoders import jsonable_encoder

from ....models.meeting_session import MeetingSession
from ....models.object_runtime import (
    ObjectAction,
    ObjectCatalogEntry,
    ObjectCatalogResponse,
    ObjectGraphProjectRequest,
    ObjectGraphProjectResponse,
    ObjectGraphProjection,
    ObjectGraphProjectionCapabilities,
    ObjectGraphRelation,
    ObjectMeetingAttachRequest,
    ObjectMeetingAttachResponse,
    ObjectMaterializeRequest,
    ObjectMaterializeResponse,
    ObjectMaterializerCapabilities,
    ObjectMeetingProjectionCapabilities,
    ObjectRoleEntry,
    ObjectRef,
    ObjectResolverCapabilities,
    ObjectSummary,
    ResolvedSelectionObject,
    MeetingAttachmentSummary,
    SelectionResolveError,
    SelectionResolveRequest,
    SelectionResolveResponse,
)
from ....services.mindscape_store import MindscapeStore
from ....services.object_catalog_registry import ObjectCatalogRegistry
from ....services.object_meeting_attachment_service import (
    ObjectMeetingContextRecord,
    ObjectMeetingAttachmentService,
)
from ....services.stores.meeting_session_store import MeetingSessionStore

router = APIRouter()
logger = logging.getLogger(__name__)
_workspace_store: MindscapeStore | None = None
_meeting_session_store: MeetingSessionStore | None = None
_object_meeting_attachment_service: ObjectMeetingAttachmentService | None = None


def _resolve_local_core_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _get_object_catalog_registry() -> ObjectCatalogRegistry:
    return ObjectCatalogRegistry(_resolve_local_core_root())


def _get_workspace_store() -> MindscapeStore:
    global _workspace_store
    if _workspace_store is None:
        _workspace_store = MindscapeStore()
    return _workspace_store


def _get_meeting_session_store() -> MeetingSessionStore:
    global _meeting_session_store
    if _meeting_session_store is None:
        _meeting_session_store = MeetingSessionStore()
    return _meeting_session_store


def _get_object_meeting_attachment_service() -> ObjectMeetingAttachmentService:
    global _object_meeting_attachment_service
    if _object_meeting_attachment_service is None:
        _object_meeting_attachment_service = ObjectMeetingAttachmentService()
    return _object_meeting_attachment_service


async def _ensure_workspace_exists(workspace_id: str) -> None:
    workspace = await _get_workspace_store().get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=404, detail=f"Workspace '{workspace_id}' not found"
        )


def _to_catalog_entry(entry: Dict[str, Any]) -> ObjectCatalogEntry:
    return ObjectCatalogEntry(
        owner_pack=entry.get("owner_pack", ""),
        object_kind=entry.get("object_kind", ""),
        display_name=entry.get("display_name", ""),
        canonical_schema=entry.get("canonical_schema"),
        id_field=entry.get("id_field", ""),
        summary_fields=list(entry.get("summary_fields") or []),
        supports=list(entry.get("supports") or []),
        resolver_capabilities=ObjectResolverCapabilities(
            **(entry.get("resolver_capabilities") or {})
        ),
        meeting_projection_capabilities=ObjectMeetingProjectionCapabilities(
            **(entry.get("meeting_projection_capabilities") or {})
        ),
        materializer_capabilities=ObjectMaterializerCapabilities(
            **(entry.get("materializer_capabilities") or {})
        ),
        graph_projection_capabilities=ObjectGraphProjectionCapabilities(
            **(entry.get("graph_projection_capabilities") or {})
        ),
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _string_list(values: Any, *, limit: int | None = None) -> List[str]:
    output: List[str] = []
    for raw_value in list(values or []):
        normalized = _text(raw_value)
        if not normalized or normalized in output:
            continue
        output.append(normalized)
        if limit is not None and len(output) >= limit:
            break
    return output


def _build_object_ref(
    *,
    workspace_id: str,
    owner_pack: str,
    object_kind: str,
    object_id: str,
    version: str | None,
    selector: Dict[str, Any] | None,
    source_surface: str | None,
) -> ObjectRef:
    return ObjectRef(
        uri=f"mindscape://{owner_pack}/{object_kind}/{object_id}",
        owner_pack=owner_pack,
        object_kind=object_kind,
        object_id=object_id,
        workspace_id=workspace_id,
        version=version,
        selector=selector,
        source_surface=source_surface,
    )


def _parse_mindscape_uri(uri: str) -> Tuple[str | None, str | None, str | None]:
    normalized_uri = _text(uri)
    if not normalized_uri.startswith("mindscape://"):
        return None, None, None
    remainder = normalized_uri.removeprefix("mindscape://")
    parts = remainder.split("/", 2)
    if len(parts) != 3:
        return None, None, None
    owner_pack, object_kind, object_id = (_text(part) for part in parts)
    if not owner_pack or not object_kind or not object_id:
        return None, None, None
    return owner_pack, object_kind, object_id


def _build_object_summary(
    *,
    entry: ObjectCatalogEntry,
    ref: ObjectRef,
    request: SelectionResolveRequest,
) -> ObjectSummary:
    subtitle_parts: List[str] = []
    if request.element and request.element.label:
        subtitle_parts.append(request.element.label)
    if request.surface.surface_id:
        subtitle_parts.append(request.surface.surface_id)

    summary_parts: List[str] = []
    if request.element and request.element.label:
        summary_parts.append(f"Selection label: {request.element.label}.")
    if request.surface.route:
        summary_parts.append(f"Owner surface: {request.surface.route}.")

    labels = sorted({"selection", ref.owner_pack, ref.object_kind})

    return ObjectSummary(
        ref=ref,
        title=f"{entry.display_name} {ref.object_id}",
        subtitle=" / ".join(subtitle_parts) or None,
        summary_text=" ".join(summary_parts) or None,
        status="ready",
        labels=labels,
        owner_surface_url=request.surface.route,
    )


def _build_catalog_summary(
    *,
    entry: ObjectCatalogEntry,
    ref: ObjectRef,
) -> ObjectSummary:
    return ObjectSummary(
        ref=ref,
        title=f"{entry.display_name} {ref.object_id}",
        summary_text=f"Addressable object from {ref.owner_pack}.{ref.object_kind}.",
        status="ready",
        labels=sorted({"meeting", ref.owner_pack, ref.object_kind}),
    )


def _first_text(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(payload.get(key))
        if value:
            return value
    return ""


def _coerce_summary_from_backend_payload(
    *,
    payload: Dict[str, Any],
    ref: ObjectRef,
    fallback_summary: ObjectSummary,
) -> ObjectSummary:
    title = _first_text(payload, "title", "display_label", "label")
    if not title:
        title = fallback_summary.title

    subtitle = _first_text(payload, "subtitle")
    if not subtitle:
        subtitle_parts: List[str] = []
        source_handle = _text(payload.get("source_handle"))
        source_shortcode = _text(payload.get("source_shortcode"))
        if source_handle:
            subtitle_parts.append(source_handle)
        if source_shortcode:
            subtitle_parts.append(f"#{source_shortcode}")
        if not subtitle_parts:
            for key in ("project_id", "run_id", "session_id", "scene_id", "artifact_id"):
                value = _text(payload.get(key))
                if value:
                    subtitle_parts.append(value)
                if len(subtitle_parts) >= 3:
                    break
        subtitle = " / ".join(subtitle_parts) or fallback_summary.subtitle or ""

    summary_text = _first_text(
        payload,
        "summary_text",
        "scene_summary",
        "summary",
        "review_summary",
        "post_caption",
    )
    if not summary_text:
        summary_text = fallback_summary.summary_text or ""

    status = _first_text(
        payload,
        "status",
        "analysis_status",
        "editorial_status",
        "approval_state",
    ) or (fallback_summary.status or "")

    labels = sorted(
        {
            *list(fallback_summary.labels or []),
            *_string_list(payload.get("labels"), limit=8),
            *_string_list(payload.get("tags"), limit=8),
            *_string_list(payload.get("auto_tags"), limit=8),
        }
    )
    thumbnail_ref = _first_text(payload, "thumbnail_ref", "thumbnail_url", "image_url")
    owner_surface_url = _first_text(payload, "owner_surface_url") or (
        fallback_summary.owner_surface_url or ""
    )
    updated_at = _first_text(payload, "updated_at")

    return ObjectSummary(
        ref=ref,
        title=title,
        subtitle=subtitle or None,
        summary_text=summary_text or None,
        status=status or None,
        labels=labels,
        thumbnail_ref=thumbnail_ref or None,
        owner_surface_url=owner_surface_url or None,
        updated_at=updated_at or None,
    )


def _select_summary_backend(entry_payload: Dict[str, Any]) -> str | None:
    resolver_backends = dict(entry_payload.get("resolver_backends") or {})
    backend = _text(resolver_backends.get("summary_backend"))
    return backend or None


async def _resolve_runtime_summary(
    *,
    entry_payload: Dict[str, Any],
    workspace_id: str,
    ref: ObjectRef,
    fallback_summary: ObjectSummary,
) -> ObjectSummary:
    backend = _select_summary_backend(entry_payload)
    if not backend:
        return fallback_summary

    try:
        payload = await _invoke_backend_callable(
            backend,
            workspace_id=workspace_id,
            object_id=ref.object_id,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception(
            "Failed to resolve object summary via %s for %s: %s",
            backend,
            ref.uri,
            exc,
        )
        return fallback_summary

    if not isinstance(payload, dict):
        return fallback_summary

    return _coerce_summary_from_backend_payload(
        payload=payload,
        ref=ref,
        fallback_summary=fallback_summary,
    )


def _default_meeting_projection_payload(
    *,
    ref: ObjectRef,
    summary: ObjectSummary,
    verb: str,
) -> Dict[str, Any]:
    return {
        "verb": _text(verb) or "attach",
        "uri": ref.uri,
        "owner_pack": ref.owner_pack,
        "object_kind": ref.object_kind,
        "object_id": ref.object_id,
        "title": summary.title,
        "summary_text": summary.summary_text,
        "labels": list(summary.labels or []),
    }


def _attach_action() -> ObjectAction:
    return ObjectAction(
        action_code="attach_to_meeting",
        label="Bring Into Meeting",
        description="Attach this object to a meeting as a source or target.",
        verb="attach",
        mode="meeting",
        requires_review=False,
        target_kind=None,
    )


def _recommend_action() -> ObjectAction:
    return ObjectAction(
        action_code="recommend_related_objects",
        label="Recommend Related Objects",
        description="Suggest nearby refs, storyboard targets, or review pathways.",
        verb="recommend",
        mode="contextual",
        requires_review=False,
        target_kind=None,
    )


def _open_owner_surface_action() -> ObjectAction:
    return ObjectAction(
        action_code="open_owner_surface",
        label="Open Owner Surface",
        description="Open the owner pack surface for this object.",
        verb="open",
        mode="navigation",
        requires_review=False,
        target_kind=None,
    )


def _build_actions(
    *,
    entry: ObjectCatalogEntry,
    request: SelectionResolveRequest,
) -> Tuple[List[ObjectAction], List[SelectionResolveError]]:
    if request.mode == "resolve_only":
        return [], []

    meeting_verbs = set(entry.meeting_projection_capabilities.verbs)
    actions: List[ObjectAction] = []
    warnings: List[SelectionResolveError] = []

    if request.mode in {"contextual_actions", "attach_to_meeting"}:
        if "attach" in meeting_verbs:
            actions.append(_attach_action())
        elif request.mode == "attach_to_meeting":
            warnings.append(
                SelectionResolveError(
                    code="meeting_attach_not_supported",
                    message=(
                        "Resolved object does not declare attach support for meeting entry."
                    ),
                )
            )

    if request.mode == "contextual_actions" and "recommend" in meeting_verbs:
        actions.append(_recommend_action())

    if request.mode in {"contextual_actions", "open_owner_surface"}:
        if request.surface.route:
            actions.append(_open_owner_surface_action())
        elif request.mode == "open_owner_surface":
            warnings.append(
                SelectionResolveError(
                    code="owner_surface_missing",
                    message="Selection surface did not provide an owner route.",
                )
            )

    return actions, warnings


def _validate_selection_hints(request: SelectionResolveRequest) -> None:
    if not request.hints:
        return

    identity_values = [
        request.hints.owner_pack,
        request.hints.object_kind,
        request.hints.object_id,
    ]
    populated_count = sum(1 for value in identity_values if value)
    if 0 < populated_count < 3:
        raise HTTPException(
            status_code=422,
            detail=(
                "Selection hints must provide owner_pack, object_kind, and object_id "
                "together when any object identity hint is supplied."
            ),
        )

    if (
        request.surface.surface_type == "installed_pack_ui"
        and request.surface.pack_code
        and request.hints.owner_pack
        and request.surface.pack_code != request.hints.owner_pack
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "surface.pack_code and hints.owner_pack must match for installed "
                "pack UI selections."
            ),
        )


def _validate_object_ref_identity(ref: ObjectRef, workspace_id: str) -> None:
    expected_uri = f"mindscape://{ref.owner_pack}/{ref.object_kind}/{ref.object_id}"
    if ref.uri != expected_uri:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_object_ref",
                "message": (
                    "ObjectRef uri must round-trip into owner_pack, object_kind, "
                    "and object_id."
                ),
                "details": {
                    "expected_uri": expected_uri,
                    "provided_uri": ref.uri,
                },
            },
        )
    if ref.workspace_id and ref.workspace_id != workspace_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_object_ref",
                "message": "ObjectRef workspace_id must match the route workspace.",
                "details": {
                    "route_workspace_id": workspace_id,
                    "ref_workspace_id": ref.workspace_id,
                },
            },
        )


async def _resolve_attach_ref(
    *,
    registry: ObjectCatalogRegistry,
    workspace_id: str,
    ref: ObjectRef,
    require_meeting_projection: bool,
    error_code: str,
) -> Tuple[ObjectCatalogEntry, ObjectSummary]:
    _validate_object_ref_identity(ref, workspace_id)

    entry_payload = registry.get_entry(ref.owner_pack, ref.object_kind)
    if not entry_payload:
        raise HTTPException(
            status_code=404,
            detail={
                "code": error_code,
                "message": (
                    "ObjectRef does not map to an installed addressable object kind."
                ),
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                    "object_id": ref.object_id,
                },
            },
        )

    entry = _to_catalog_entry(entry_payload)
    if require_meeting_projection and not entry.meeting_projection_capabilities.available:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "projection_unavailable",
                "message": "Meeting attachment is unavailable for this object kind.",
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                },
            },
        )

    fallback_summary = _build_catalog_summary(entry=entry, ref=ref)
    summary = await _resolve_runtime_summary(
        entry_payload=entry_payload,
        workspace_id=workspace_id,
        ref=ref,
        fallback_summary=fallback_summary,
    )

    return entry, summary


def _select_materializer_backend(
    entry_payload: Dict[str, Any],
    *,
    verb: str,
    write_mode: str,
) -> str | None:
    candidates = list(entry_payload.get("materializer_backends") or [])

    for materializer in candidates:
        verbs = list(materializer.get("verbs") or [])
        candidate_write_mode = _text(materializer.get("write_mode"))
        backend = _text(materializer.get("backend"))
        if (
            backend
            and verb in verbs
            and candidate_write_mode
            and candidate_write_mode == write_mode
        ):
            return backend

    for materializer in candidates:
        verbs = list(materializer.get("verbs") or [])
        backend = _text(materializer.get("backend"))
        if backend and verb in verbs:
            return backend

    return None


def _select_meeting_projection_backend(
    entry_payload: Dict[str, Any],
    *,
    verb: str,
) -> str | None:
    for projection in list(entry_payload.get("meeting_projection_backends") or []):
        verbs = list(projection.get("verbs") or [])
        backend = _text(projection.get("projection_backend"))
        if backend and verb in verbs:
            return backend

    for projection in list(entry_payload.get("meeting_projection_backends") or []):
        backend = _text(projection.get("projection_backend"))
        if backend:
            return backend

    return None


def _select_graph_projection_backend(entry_payload: Dict[str, Any]) -> str | None:
    for projection in list(entry_payload.get("graph_projection_backends") or []):
        backend = _text(projection.get("backend"))
        if backend:
            return backend
    return None


async def _invoke_backend_callable(backend_path: str, **kwargs: Any) -> Any:
    module_path, attr_name = backend_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    target = getattr(module, attr_name)
    signature = inspect.signature(target)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        invocation_kwargs = kwargs
    else:
        invocation_kwargs = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
    result = target(**invocation_kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _build_materializer_context_objects(
    context_records: List[ObjectMeetingContextRecord],
    *,
    roles: set[str] | None = None,
) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    for record in context_records:
        if roles is not None and record.role not in roles:
            continue
        payload = {
            "role": record.role,
            "owner_pack": record.ref.owner_pack,
            "object_kind": record.ref.object_kind,
            "object_id": record.ref.object_id,
            "object_ref": record.ref.model_dump(exclude_none=True),
            "object_summary": {
                "title": record.summary.title,
                "subtitle": record.summary.subtitle,
                "summary_text": record.summary.summary_text,
                "status": record.summary.status,
                "labels": list(record.summary.labels or []),
                "owner_surface_url": record.summary.owner_surface_url,
            },
        }
        if isinstance(record.meeting_projection, dict) and record.meeting_projection:
            payload["meeting_projection"] = dict(record.meeting_projection)

        payloads.append(
            {
                **payload,
            }
        )
    return payloads


async def _resolve_meeting_projection_payload(
    *,
    entry_payload: Dict[str, Any],
    workspace_id: str,
    ref: ObjectRef,
    summary: ObjectSummary,
    verb: str,
) -> Dict[str, Any]:
    backend_path = _select_meeting_projection_backend(entry_payload, verb=verb)
    if not backend_path:
        return _default_meeting_projection_payload(ref=ref, summary=summary, verb=verb)

    try:
        result = await _invoke_backend_callable(
            backend_path,
            workspace_id=workspace_id,
            object_id=ref.object_id,
            verb=verb,
        )
    except Exception:
        logger.exception(
            "Addressable Object Layer meeting projection failed for %s.%s",
            ref.owner_pack,
            ref.object_kind,
        )
        return _default_meeting_projection_payload(ref=ref, summary=summary, verb=verb)

    if isinstance(result, dict) and result:
        return result

    return _default_meeting_projection_payload(ref=ref, summary=summary, verb=verb)


def _coerce_materialized_ref_payload(
    payload: Dict[str, Any],
    *,
    workspace_id: str,
) -> ObjectRef:
    owner_pack = _text(payload.get("owner_pack"))
    object_kind = _text(payload.get("object_kind"))
    object_id = _text(payload.get("object_id"))
    if not owner_pack or not object_kind or not object_id:
        raise ValueError("materializer_ref_identity_incomplete")

    return ObjectRef(
        uri=_text(payload.get("uri")) or f"mindscape://{owner_pack}/{object_kind}/{object_id}",
        owner_pack=owner_pack,
        object_kind=object_kind,
        object_id=object_id,
        workspace_id=_text(payload.get("workspace_id")) or workspace_id,
        version=_text(payload.get("version")) or None,
        selector=payload.get("selector"),
        source_surface=_text(payload.get("source_surface")) or None,
    )


def _coerce_materializer_errors(result: Dict[str, Any]) -> List[SelectionResolveError]:
    errors: List[SelectionResolveError] = []
    for raw_error in list(result.get("errors") or []):
        if not isinstance(raw_error, dict):
            continue
        code = _text(raw_error.get("code")) or "materializer_error"
        message = _text(raw_error.get("message")) or "Owner-pack materializer reported an error."
        errors.append(SelectionResolveError(code=code, message=message))
    return errors


def _coerce_route_list(
    result: Dict[str, Any],
    *,
    single_key: str,
    plural_key: str,
) -> List[str]:
    routes: List[str] = []
    single_route = _text(result.get(single_key))
    if single_route:
        routes.append(single_route)
    for raw_route in list(result.get(plural_key) or []):
        normalized_route = _text(raw_route)
        if normalized_route and normalized_route not in routes:
            routes.append(normalized_route)
    return routes


def _coerce_request_plan(result: Dict[str, Any]) -> Dict[str, Any] | None:
    raw_request_plan = result.get("request_plan")
    if isinstance(raw_request_plan, dict) and raw_request_plan:
        return dict(raw_request_plan)

    endpoint = _text(result.get("endpoint") or result.get("path"))
    request_template = result.get("request_template")
    if not endpoint and request_template in (None, {}, []):
        return None

    request_plan: Dict[str, Any] = {}
    method = _text(result.get("method")) or "POST"
    if method:
        request_plan["method"] = method
    if endpoint:
        request_plan["path"] = endpoint
    if request_template is not None:
        request_plan["body"] = request_template
    return request_plan or None


async def _execute_materializer_backend(
    *,
    workspace_id: str,
    object_ref: ObjectRef,
    entry_payload: Dict[str, Any],
    meeting_id: str | None,
    verb: str,
    write_mode: str,
    source_objects: List[Dict[str, Any]],
    context_objects: List[Dict[str, Any]],
    intent_summary: str,
    request_context: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    backend_path = _select_materializer_backend(
        entry_payload,
        verb=verb,
        write_mode=write_mode,
    )
    if not backend_path:
        return None

    return await _invoke_backend_callable(
        backend_path,
        workspace_id=workspace_id,
        object_id=object_ref.object_id,
        meeting_id=meeting_id,
        verb=verb,
        write_mode=write_mode,
        source_objects=source_objects,
        context_objects=context_objects,
        intent_summary=intent_summary,
        request_context=dict(request_context or {}),
    )


def _normalize_materializer_outcome(
    *,
    result: Dict[str, Any],
    workspace_id: str,
    allowed_statuses: set[str],
    default_status: str,
) -> Tuple[
    str,
    List[ObjectRef],
    List[str],
    List[str],
    Dict[str, Any] | None,
    List[SelectionResolveError],
]:
    staged_refs: List[ObjectRef] = []
    raw_staged_ref = result.get("staged_ref")
    if isinstance(raw_staged_ref, dict):
        staged_refs.append(
            _coerce_materialized_ref_payload(raw_staged_ref, workspace_id=workspace_id)
        )
    for raw_staged in list(result.get("staged_refs") or []):
        if isinstance(raw_staged, dict):
            staged_refs.append(
                _coerce_materialized_ref_payload(raw_staged, workspace_id=workspace_id)
            )

    review_routes = _coerce_route_list(
        result,
        single_key="review_route",
        plural_key="review_routes",
    )
    canonical_routes = _coerce_route_list(
        result,
        single_key="canonical_route",
        plural_key="canonical_routes",
    )
    canonical_storyboard_route = _text(result.get("canonical_storyboard_route"))
    if canonical_storyboard_route and canonical_storyboard_route not in canonical_routes:
        canonical_routes.append(canonical_storyboard_route)

    request_plan = _coerce_request_plan(result)
    errors = _coerce_materializer_errors(result)
    normalized_status = _text(result.get("status"))
    if normalized_status not in allowed_statuses:
        if request_plan or review_routes or canonical_routes:
            normalized_status = "planned" if "planned" in allowed_statuses else default_status
        elif staged_refs:
            normalized_status = "materialized" if "materialized" in allowed_statuses else default_status
        elif errors:
            normalized_status = "rejected" if "rejected" in allowed_statuses else default_status
        else:
            normalized_status = default_status

    if errors and normalized_status not in {"rejected", "planned"}:
        normalized_status = "rejected" if "rejected" in allowed_statuses else default_status

    return (
        normalized_status,
        staged_refs,
        review_routes,
        canonical_routes,
        request_plan,
        errors,
    )


async def _materialize_target_outcome(
    *,
    workspace_id: str,
    meeting_id: str,
    request: ObjectMeetingAttachRequest,
    target_ref: ObjectRef,
    target_entry_payload: Dict[str, Any],
    context_records: List[ObjectMeetingContextRecord],
) -> Tuple[str, List[ObjectRef], List[str], List[SelectionResolveError], Dict[str, Any] | None]:
    try:
        result = await _execute_materializer_backend(
            workspace_id=workspace_id,
            object_ref=target_ref,
            entry_payload=target_entry_payload,
            meeting_id=meeting_id,
            verb="attach",
            write_mode=request.write_mode,
            source_objects=_build_materializer_context_objects(
                context_records,
                roles={"source"},
            ),
            context_objects=_build_materializer_context_objects(context_records),
            intent_summary=request.intent_summary,
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer materializer failed for %s.%s",
            target_ref.owner_pack,
            target_ref.object_kind,
        )
        return (
            "rejected",
            [],
            [],
            [
                SelectionResolveError(
                    code="materializer_failed",
                    message=(
                        "Owner-pack materializer failed while staging the attach outcome: "
                        f"{exc}"
                    ),
                )
            ],
            None,
        )
    if result is None:
        return "attached", [], [], [], None

    if not isinstance(result, dict):
        return (
            "rejected",
            [],
            [],
            [
                SelectionResolveError(
                    code="invalid_materializer_result",
                    message="Owner-pack materializer returned a non-object payload.",
                )
            ],
            None,
        )

    try:
        (
            normalized_status,
            staged_refs,
            review_routes,
            _canonical_routes,
            _request_plan,
            errors,
        ) = _normalize_materializer_outcome(
            result=result,
            workspace_id=workspace_id,
            allowed_statuses={"attached", "materialized", "rejected"},
            default_status="attached",
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer materializer normalization failed for %s.%s",
            target_ref.owner_pack,
            target_ref.object_kind,
        )
        return (
            "rejected",
            [],
            [],
            [
                SelectionResolveError(
                    code="materializer_failed",
                    message=(
                        "Owner-pack materializer failed while staging the attach outcome: "
                        f"{exc}"
                    ),
                )
            ],
            None,
        )

    return normalized_status, staged_refs, review_routes, errors, result


def _build_session_attachment_metadata(
    *,
    request: ObjectMeetingAttachRequest,
    handoff_payload: dict,
    response_status: str,
    staged_refs: List[ObjectRef],
    review_routes: List[str],
    materialization_result: Dict[str, Any] | None,
) -> dict:
    safe_handoff_payload = jsonable_encoder(handoff_payload)
    safe_materialization_result = (
        jsonable_encoder(materialization_result)
        if materialization_result is not None
        else None
    )
    return {
        "meeting_type": request.meeting_type,
        "intent_summary": request.intent_summary,
        "status": response_status,
        "write_mode": request.write_mode,
        "context_entries": [
            {
                "role": entry.role,
                "ref": entry.ref.model_dump(exclude_none=True),
            }
            for entry in request.entries
        ],
        "target_ref": (
            request.target_ref.model_dump(exclude_none=True)
            if request.target_ref
            else None
        ),
        "staged_refs": [ref.model_dump(exclude_none=True) for ref in staged_refs],
        "review_routes": list(review_routes),
        "materialization_result": safe_materialization_result,
        "handoff_in": safe_handoff_payload,
        "context_attachments": safe_handoff_payload.get("context_attachments") or [],
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _upsert_meeting_session_metadata(session: MeetingSession, attachment_metadata: dict) -> None:
    session.metadata = dict(session.metadata or {})
    session.metadata["addressable_object_layer"] = attachment_metadata


def _coerce_relation_target_ref(
    raw_relation: Dict[str, Any],
    *,
    workspace_id: str,
) -> ObjectRef | None:
    nested_target = raw_relation.get("target_ref")
    if not isinstance(nested_target, dict):
        nested_target = raw_relation.get("to_ref")
    nested_target = dict(nested_target) if isinstance(nested_target, dict) else {}

    owner_pack = _text(
        nested_target.get("owner_pack")
        or nested_target.get("target_owner_pack")
        or nested_target.get("target_pack")
        or raw_relation.get("target_owner_pack")
        or raw_relation.get("target_pack")
    )
    object_kind = _text(
        nested_target.get("object_kind")
        or nested_target.get("target_object_kind")
        or nested_target.get("target_kind")
        or raw_relation.get("target_object_kind")
        or raw_relation.get("target_kind")
    )
    object_id = _text(
        nested_target.get("object_id")
        or nested_target.get("target_object_id")
        or raw_relation.get("target_object_id")
    )
    uri = _text(nested_target.get("uri") or raw_relation.get("target_uri"))
    parsed_owner_pack, parsed_object_kind, parsed_object_id = _parse_mindscape_uri(uri)
    owner_pack = owner_pack or (parsed_owner_pack or "")
    object_kind = object_kind or (parsed_object_kind or "")
    object_id = object_id or (parsed_object_id or "")
    if not owner_pack or not object_kind or not object_id:
        return None
    return ObjectRef(
        uri=uri or f"mindscape://{owner_pack}/{object_kind}/{object_id}",
        owner_pack=owner_pack,
        object_kind=object_kind,
        object_id=object_id,
        workspace_id=workspace_id,
        version=_text(nested_target.get("version")) or None,
        selector=nested_target.get("selector"),
        source_surface=_text(nested_target.get("source_surface")) or None,
    )


def _normalize_graph_relations(
    raw_relations: Any,
    *,
    workspace_id: str,
) -> List[ObjectGraphRelation]:
    normalized_relations: List[ObjectGraphRelation] = []
    relation_items = list(raw_relations or []) if isinstance(raw_relations, list) else []
    known_keys = {
        "relation_kind",
        "kind",
        "direction",
        "target_ref",
        "to_ref",
        "target_uri",
        "target_owner_pack",
        "target_pack",
        "target_object_kind",
        "target_kind",
        "target_object_id",
    }
    for raw_relation in relation_items:
        if not isinstance(raw_relation, dict):
            continue
        relation_kind = _text(raw_relation.get("relation_kind") or raw_relation.get("kind"))
        target_ref = _coerce_relation_target_ref(raw_relation, workspace_id=workspace_id)
        if not relation_kind or target_ref is None:
            continue
        direction = _text(raw_relation.get("direction")) or "outbound"
        if direction not in {"outbound", "inbound", "bidirectional"}:
            direction = "outbound"
        metadata = {
            key: value
            for key, value in raw_relation.items()
            if key not in known_keys and value is not None
        }
        normalized_relations.append(
            ObjectGraphRelation(
                relation_kind=relation_kind,
                direction=direction,
                target_ref=target_ref,
                metadata=metadata,
            )
        )
    return normalized_relations


async def _resolve_graph_projection(
    *,
    entry_payload: Dict[str, Any],
    workspace_id: str,
    ref: ObjectRef,
) -> Dict[str, Any]:
    backend_path = _select_graph_projection_backend(entry_payload)
    if not backend_path:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "projection_unavailable",
                "message": "Graph projection is unavailable for this object kind.",
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                },
            },
        )

    try:
        result = await _invoke_backend_callable(
            backend_path,
            workspace_id=workspace_id,
            object_id=ref.object_id,
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer graph projection failed for %s.%s",
            ref.owner_pack,
            ref.object_kind,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "graph_projection_failed",
                "message": (
                    "Owner-pack graph projection failed while building the runtime graph."
                ),
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                    "error": str(exc),
                },
            },
        ) from exc

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_graph_projection",
                "message": "Owner-pack graph projection returned a non-object payload.",
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                },
            },
        )
    return result


@router.get(
    "/{workspace_id}/object-catalog",
    response_model=ObjectCatalogResponse,
)
async def get_workspace_object_catalog(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    owner_pack: str | None = Query(None, description="Filter by owner pack"),
    object_kind: str | None = Query(None, description="Filter by object kind"),
    supports: str | None = Query(None, description="Filter by declared support flag"),
    include_examples: bool = Query(
        False,
        description="Reserved for future example object refs when available.",
    ),
) -> ObjectCatalogResponse:
    del include_examples

    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()
    entries = [
        _to_catalog_entry(entry)
        for entry in registry.list_entries(
            owner_pack=owner_pack,
            object_kind=object_kind,
            supports=supports,
        )
    ]

    return ObjectCatalogResponse(
        workspace_id=workspace_id,
        catalog_version=registry.get_catalog_version(),
        entries=entries,
    )


@router.post(
    "/{workspace_id}/selection/resolve",
    response_model=SelectionResolveResponse,
)
async def resolve_workspace_selection(
    request: SelectionResolveRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> SelectionResolveResponse:
    await _ensure_workspace_exists(workspace_id)
    _validate_selection_hints(request)

    if not request.hints or not (
        request.hints.owner_pack
        and request.hints.object_kind
        and request.hints.object_id
    ):
        return SelectionResolveResponse(
            workspace_id=workspace_id,
            selection_id=request.selection_id,
            status="unresolved",
            errors=[
                SelectionResolveError(
                    code="insufficient_hints",
                    message=(
                        "Selection did not provide enough addressable object hints "
                        "to resolve an ObjectRef."
                    ),
                )
            ],
        )

    registry = _get_object_catalog_registry()
    entry_payload = registry.get_entry(
        request.hints.owner_pack,
        request.hints.object_kind,
    )
    if not entry_payload:
        return SelectionResolveResponse(
            workspace_id=workspace_id,
            selection_id=request.selection_id,
            status="unresolved",
            errors=[
                SelectionResolveError(
                    code="object_not_found",
                    message=(
                        "No addressable object could be resolved from the supplied "
                        "selection hints."
                    ),
                )
            ],
        )

    entry = _to_catalog_entry(entry_payload)
    ref = _build_object_ref(
        workspace_id=workspace_id,
        owner_pack=request.hints.owner_pack,
        object_kind=request.hints.object_kind,
        object_id=request.hints.object_id,
        version=request.hints.version,
        selector=request.hints.selector,
        source_surface=request.hints.source_surface or request.surface.surface_id,
    )
    fallback_summary = _build_object_summary(entry=entry, ref=ref, request=request)
    summary = await _resolve_runtime_summary(
        entry_payload=entry_payload,
        workspace_id=workspace_id,
        ref=ref,
        fallback_summary=fallback_summary,
    )
    actions, warnings = _build_actions(entry=entry, request=request)

    return SelectionResolveResponse(
        workspace_id=workspace_id,
        selection_id=request.selection_id,
        status="resolved",
        resolved_objects=[
            ResolvedSelectionObject(ref=ref, summary=summary, actions=actions)
        ],
        errors=warnings,
    )


@router.post(
    "/{workspace_id}/object-meeting-attach",
    response_model=ObjectMeetingAttachResponse,
)
async def attach_objects_to_meeting(
    request: ObjectMeetingAttachRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectMeetingAttachResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()

    target_entries = [entry for entry in request.entries if entry.role == "target"]
    if len(target_entries) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "multiple_targets_not_supported",
                "message": "Attach requests currently support at most one target object.",
            },
        )
    if len(request.entries) == len(target_entries):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "source_required",
                "message": "Attach requests require at least one non-target context object.",
            },
        )

    context_records: List[ObjectMeetingContextRecord] = []
    for request_entry in request.entries:
        ref = request_entry.ref
        require_meeting_projection = request_entry.role != "target"
        catalog_entry, summary = await _resolve_attach_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=ref,
            require_meeting_projection=require_meeting_projection,
            error_code=(
                "target_ref_invalid"
                if request_entry.role == "target"
                else "object_not_found"
            ),
        )
        entry_payload = registry.get_entry(ref.owner_pack, ref.object_kind) or {}
        meeting_projection = None
        if catalog_entry.meeting_projection_capabilities.available:
            meeting_projection = await _resolve_meeting_projection_payload(
                entry_payload=entry_payload,
                workspace_id=workspace_id,
                ref=ref,
                summary=summary,
                verb="attach",
            )
        context_records.append(
            ObjectMeetingContextRecord(
                role=request_entry.role,
                ref=ref,
                summary=summary,
                meeting_projection=meeting_projection,
            )
        )

    target_ref = target_entries[0].ref if target_entries else None

    session_store = _get_meeting_session_store()
    if request.meeting_id:
        session = session_store.get_by_id(request.meeting_id)
        if not session or session.workspace_id != workspace_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "meeting_not_found",
                    "message": "Meeting session was not found for this workspace.",
                    "details": {"meeting_id": request.meeting_id},
                },
            )
        if not session.is_active:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "meeting_closed",
                    "message": "Meeting session is no longer active.",
                    "details": {"meeting_id": request.meeting_id},
                },
            )
    else:
        session = MeetingSession.new(
            workspace_id=workspace_id,
            meeting_type=request.meeting_type,
            agenda=[request.intent_summary],
        )
        session.start()
        session_store.create(session)

    attachment_service = _get_object_meeting_attachment_service()
    handoff_result = attachment_service.build_handoff(
        workspace_id=workspace_id,
        meeting_id=session.id,
        meeting_type=request.meeting_type,
        intent_summary=request.intent_summary,
        write_mode=request.write_mode,
        context_objects=context_records,
    )
    response_status = "attached"
    staged_refs: List[ObjectRef] = []
    review_routes: List[str] = []
    response_errors: List[SelectionResolveError] = []
    materialization_result: Dict[str, Any] | None = None

    if target_ref:
        target_entry_payload = registry.get_entry(
            target_ref.owner_pack,
            target_ref.object_kind,
        )
        if target_entry_payload:
            (
                response_status,
                staged_refs,
                review_routes,
                response_errors,
                materialization_result,
            ) = await _materialize_target_outcome(
                workspace_id=workspace_id,
                meeting_id=session.id,
                request=request,
                target_ref=target_ref,
                target_entry_payload=target_entry_payload,
                context_records=context_records,
            )

    _upsert_meeting_session_metadata(
        session,
        _build_session_attachment_metadata(
            request=request,
            handoff_payload=handoff_result.handoff_in.model_dump(exclude_none=True),
            response_status=response_status,
            staged_refs=staged_refs,
            review_routes=review_routes,
            materialization_result=materialization_result,
        ),
    )
    session_store.update(session)

    attachment_summaries = [
        MeetingAttachmentSummary(
            role=record.role,
            ref=record.ref,
            projection_level="meeting",
        )
        for record in context_records
    ]

    return ObjectMeetingAttachResponse(
        workspace_id=workspace_id,
        meeting_id=session.id,
        status=response_status,
        attachments=attachment_summaries,
        target_ref=target_ref,
        staged_refs=staged_refs,
        review_routes=review_routes,
        errors=response_errors,
    )


@router.post(
    "/{workspace_id}/object-materialize",
    response_model=ObjectMaterializeResponse,
)
async def materialize_object_outcome(
    request: ObjectMaterializeRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectMaterializeResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()
    entry, _summary = await _resolve_attach_ref(
        registry=registry,
        workspace_id=workspace_id,
        ref=request.object_ref,
        require_meeting_projection=False,
        error_code="object_not_found",
    )
    entry_payload = registry.get_entry(
        request.object_ref.owner_pack,
        request.object_ref.object_kind,
    ) or {}
    if not _select_materializer_backend(
        entry_payload,
        verb=request.verb,
        write_mode=request.write_mode,
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "materializer_unavailable",
                "message": "Materialization is unavailable for this object kind and verb.",
                "details": {
                    "owner_pack": request.object_ref.owner_pack,
                    "object_kind": request.object_ref.object_kind,
                    "verb": request.verb,
                    "write_mode": request.write_mode,
                },
            },
        )

    context_records: List[ObjectMeetingContextRecord] = []
    for context_entry in request.context_entries:
        context_ref = context_entry.ref
        _context_entry, context_summary = await _resolve_attach_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=context_ref,
            require_meeting_projection=False,
            error_code="object_not_found",
        )
        context_entry_payload = registry.get_entry(
            context_ref.owner_pack,
            context_ref.object_kind,
        ) or {}
        meeting_projection = None
        if _context_entry.meeting_projection_capabilities.available:
            meeting_projection = await _resolve_meeting_projection_payload(
                entry_payload=context_entry_payload,
                workspace_id=workspace_id,
                ref=context_ref,
                summary=context_summary,
                verb=request.verb,
            )
        context_records.append(
            ObjectMeetingContextRecord(
                role=context_entry.role,
                ref=context_ref,
                summary=context_summary,
                meeting_projection=meeting_projection,
            )
        )

    try:
        result = await _execute_materializer_backend(
            workspace_id=workspace_id,
            object_ref=request.object_ref,
            entry_payload=entry_payload,
            meeting_id=request.meeting_id,
            verb=request.verb,
            write_mode=request.write_mode,
            source_objects=_build_materializer_context_objects(
                context_records,
                roles={"source"},
            ),
            context_objects=_build_materializer_context_objects(context_records),
            intent_summary=request.intent_summary,
            request_context=request.request_context,
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer materializer failed for %s.%s",
            request.object_ref.owner_pack,
            request.object_ref.object_kind,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "materializer_failed",
                "message": "Owner-pack materializer failed while planning the requested outcome.",
                "details": {
                    "owner_pack": request.object_ref.owner_pack,
                    "object_kind": request.object_ref.object_kind,
                    "verb": request.verb,
                    "error": str(exc),
                },
            },
        ) from exc

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_materializer_result",
                "message": "Owner-pack materializer returned a non-object payload.",
                "details": {
                    "owner_pack": request.object_ref.owner_pack,
                    "object_kind": request.object_ref.object_kind,
                    "verb": request.verb,
                },
            },
        )

    (
        response_status,
        staged_refs,
        review_routes,
        canonical_routes,
        request_plan,
        response_errors,
    ) = _normalize_materializer_outcome(
        result=result,
        workspace_id=workspace_id,
        allowed_statuses={"planned", "materialized", "rejected"},
        default_status="planned",
    )

    return ObjectMaterializeResponse(
        workspace_id=workspace_id,
        status=response_status,
        verb=request.verb,
        object_ref=request.object_ref,
        staged_refs=staged_refs,
        review_routes=review_routes,
        canonical_routes=canonical_routes,
        request_plan=request_plan,
        errors=response_errors,
    )


@router.post(
    "/{workspace_id}/object-graph/project",
    response_model=ObjectGraphProjectResponse,
)
async def project_object_graph(
    request: ObjectGraphProjectRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectGraphProjectResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()
    projections: List[ObjectGraphProjection] = []

    for ref in request.objects:
        entry, fallback_summary = await _resolve_attach_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=ref,
            require_meeting_projection=False,
            error_code="object_not_found",
        )
        entry_payload = registry.get_entry(ref.owner_pack, ref.object_kind) or {}
        raw_projection = await _resolve_graph_projection(
            entry_payload=entry_payload,
            workspace_id=workspace_id,
            ref=ref,
        )
        metadata = {
            "projection_source": "owner_pack_graph_projection",
            **{
                key: value
                for key, value in raw_projection.items()
                if key not in {"node_kind", "relations", "display_label", "summary_text"}
                and value is not None
            },
        }
        projection_summary = fallback_summary if request.include_summaries else None
        projections.append(
            ObjectGraphProjection(
                ref=ref,
                summary=projection_summary,
                node_kind=_text(raw_projection.get("node_kind")) or entry.object_kind,
                relations=(
                    _normalize_graph_relations(
                        raw_projection.get("relations"),
                        workspace_id=workspace_id,
                    )
                    if request.include_relations
                    else []
                ),
                metadata=metadata,
            )
        )

    return ObjectGraphProjectResponse(
        workspace_id=workspace_id,
        projections=projections,
    )
