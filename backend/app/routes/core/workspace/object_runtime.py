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
    ObjectGraphProjectionCapabilities,
    ObjectMeetingAttachRequest,
    ObjectMeetingAttachResponse,
    ObjectMaterializerCapabilities,
    ObjectMeetingProjectionCapabilities,
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


def _resolve_attach_ref(
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

    return entry, _build_catalog_summary(entry=entry, ref=ref)


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


async def _invoke_backend_callable(backend_path: str, **kwargs: Any) -> Any:
    module_path, attr_name = backend_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    target = getattr(module, attr_name)
    result = target(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _build_materializer_source_objects(
    source_records: List[Tuple[ObjectRef, ObjectSummary, Dict[str, Any] | None]],
) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    for ref, summary, meeting_projection in source_records:
        payload = {
            "owner_pack": ref.owner_pack,
            "object_kind": ref.object_kind,
            "object_id": ref.object_id,
            "object_ref": ref.model_dump(exclude_none=True),
            "object_summary": {
                "title": summary.title,
                "subtitle": summary.subtitle,
                "summary_text": summary.summary_text,
                "status": summary.status,
                "labels": list(summary.labels or []),
                "owner_surface_url": summary.owner_surface_url,
            },
        }
        if isinstance(meeting_projection, dict) and meeting_projection:
            payload["meeting_projection"] = dict(meeting_projection)

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


async def _materialize_target_outcome(
    *,
    workspace_id: str,
    meeting_id: str,
    request: ObjectMeetingAttachRequest,
    target_ref: ObjectRef,
    target_entry_payload: Dict[str, Any],
    source_records: List[Tuple[ObjectRef, ObjectSummary, Dict[str, Any] | None]],
) -> Tuple[str, List[ObjectRef], List[str], List[SelectionResolveError], Dict[str, Any] | None]:
    backend_path = _select_materializer_backend(
        target_entry_payload,
        verb="attach",
        write_mode=request.write_mode,
    )
    if not backend_path:
        return "attached", [], [], [], None

    try:
        result = await _invoke_backend_callable(
            backend_path,
            workspace_id=workspace_id,
            object_id=target_ref.object_id,
            meeting_id=meeting_id,
            verb="attach",
            write_mode=request.write_mode,
            source_objects=_build_materializer_source_objects(source_records),
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

    review_routes: List[str] = []
    single_review_route = _text(result.get("review_route"))
    if single_review_route:
        review_routes.append(single_review_route)
    for raw_route in list(result.get("review_routes") or []):
        normalized_route = _text(raw_route)
        if normalized_route and normalized_route not in review_routes:
            review_routes.append(normalized_route)

    errors = _coerce_materializer_errors(result)
    normalized_status = _text(result.get("status"))
    if not normalized_status:
        normalized_status = "materialized" if staged_refs or review_routes else "attached"
    if normalized_status not in {"attached", "materialized", "rejected"}:
        normalized_status = "materialized" if staged_refs or review_routes else "attached"
    if errors and normalized_status == "attached":
        normalized_status = "rejected"

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
    summary = _build_object_summary(entry=entry, ref=ref, request=request)
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

    source_records: List[Tuple[ObjectRef, ObjectSummary, Dict[str, Any] | None]] = []
    for ref in request.objects:
        entry, summary = _resolve_attach_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=ref,
            require_meeting_projection=True,
            error_code="object_not_found",
        )
        entry_payload = registry.get_entry(ref.owner_pack, ref.object_kind) or {}
        meeting_projection = await _resolve_meeting_projection_payload(
            entry_payload=entry_payload,
            workspace_id=workspace_id,
            ref=ref,
            summary=summary,
            verb="attach",
        )
        source_records.append((ref, summary, meeting_projection))

    target_pair: Tuple[ObjectRef, ObjectSummary, Dict[str, Any] | None] | None = None
    if request.target_ref:
        _target_entry, target_summary = _resolve_attach_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=request.target_ref,
            require_meeting_projection=False,
            error_code="target_ref_invalid",
        )
        target_entry_payload = (
            registry.get_entry(request.target_ref.owner_pack, request.target_ref.object_kind)
            or {}
        )
        target_projection = await _resolve_meeting_projection_payload(
            entry_payload=target_entry_payload,
            workspace_id=workspace_id,
            ref=request.target_ref,
            summary=target_summary,
            verb="attach",
        )
        target_pair = (request.target_ref, target_summary, target_projection)

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
        source_objects=source_records,
        target_object=target_pair,
    )
    response_status = "attached"
    staged_refs: List[ObjectRef] = []
    review_routes: List[str] = []
    response_errors: List[SelectionResolveError] = []
    materialization_result: Dict[str, Any] | None = None

    if target_pair:
        target_entry_payload = registry.get_entry(
            request.target_ref.owner_pack,
            request.target_ref.object_kind,
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
                target_ref=request.target_ref,
                target_entry_payload=target_entry_payload,
                source_records=source_records,
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
            role="source",
            ref=ref,
            projection_level="meeting",
        )
        for ref, _summary, _projection in source_records
    ]
    if target_pair:
        attachment_summaries.append(
            MeetingAttachmentSummary(
                role="target",
                ref=target_pair[0],
                projection_level="meeting",
            )
        )

    return ObjectMeetingAttachResponse(
        workspace_id=workspace_id,
        meeting_id=session.id,
        status=response_status,
        attachments=attachment_summaries,
        target_ref=request.target_ref,
        staged_refs=staged_refs,
        review_routes=review_routes,
        errors=response_errors,
    )
