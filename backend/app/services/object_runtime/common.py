"""Object runtime service helpers extracted from the route facade."""

from __future__ import annotations

import importlib
import inspect
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, Path as PathParam, Query
from fastapi.encoders import jsonable_encoder

from backend.app.models.meeting_session import MeetingSession
from backend.app.models.object_runtime import (
    MeetingAttachmentSummary,
    ObjectAction,
    ObjectActionClosureRequest,
    ObjectActionClosureResponse,
    ObjectActionInvokeRequest,
    ObjectActionInvokeResponse,
    ObjectActionPlanRequest,
    ObjectActionPlanResponse,
    ObjectAffordanceCapability,
    ObjectCatalogEntry,
    ObjectCatalogResponse,
    ObjectGraphProjectRequest,
    ObjectGraphProjectResponse,
    ObjectGraphProjection,
    ObjectGraphProjectionCapabilities,
    ObjectGraphRelation,
    ObjectGuidanceCard,
    ObjectInstanceIndexRequest,
    ObjectInstanceIndexResponse,
    ObjectInstanceRecord,
    ObjectInstanceSyncRequest,
    ObjectInstanceSyncResponse,
    ObjectMaterializeRequest,
    ObjectMaterializeResponse,
    ObjectMaterializerCapabilities,
    ObjectMeetingAttachRequest,
    ObjectMeetingAttachResponse,
    ObjectMeetingProjectionCapabilities,
    ObjectMentionCompletionItem,
    ObjectMentionCompletionResponse,
    ObjectReadRequest,
    ObjectReadResponse,
    ObjectRef,
    ObjectRelationIndexRequest,
    ObjectRelationIndexResponse,
    ObjectRelationRecord,
    ObjectRelationSearchResponse,
    ObjectResolverCapabilities,
    ObjectRoleEntry,
    ObjectSearchResponse,
    ObjectSummary,
    ResolvedSelectionObject,
    SelectionResolveError,
    SelectionResolveRequest,
    SelectionResolveResponse,
)
from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.object_catalog_registry import ObjectCatalogRegistry
from backend.app.services.object_index_sync_service import (
    get_object_index_sync_service,
    get_object_index_sync_status,
)
from backend.app.services.object_meeting_attachment_service import (
    ObjectMeetingAttachmentService,
    ObjectMeetingContextRecord,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.object_instance_registry_store import ObjectInstanceRegistryStore
from backend.app.services.stores.object_relation_registry_store import ObjectRelationRegistryStore
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


def _to_catalog_entry(entry: Dict[str, Any]) -> ObjectCatalogEntry:
    return ObjectCatalogEntry(
        owner_pack=entry.get("owner_pack", ""),
        object_kind=entry.get("object_kind", ""),
        display_name=entry.get("display_name", ""),
        canonical_schema=entry.get("canonical_schema"),
        id_field=entry.get("id_field", ""),
        summary_fields=list(entry.get("summary_fields") or []),
        supports=list(entry.get("supports") or []),
        granularity=entry.get("granularity"),
        selector_families=list(entry.get("selector_families") or []),
        indexer_backend=entry.get("indexer_backend"),
        mention_fields=list(entry.get("mention_fields") or []),
        owner_surface_patterns=list(entry.get("owner_surface_patterns") or []),
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
        affordances=list(entry.get("affordances") or []),
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

def _split_object_uri(uri: str) -> Tuple[str, str, str]:
    prefix = "mindscape://"
    if not uri.startswith(prefix):
        raise ValueError("uri must start with mindscape://")
    parts = uri[len(prefix):].split("/", 2)
    if len(parts) != 3 or not all(parts):
        raise ValueError("uri must use mindscape://<owner_pack>/<object_kind>/<object_id>")
    return parts[0], parts[1], parts[2]

def _coerce_read_object_ref(payload: Dict[str, Any], workspace_id: str) -> ObjectRef:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_object_ref",
                "message": "object_ref must be an object.",
            },
        )
    ref_payload = dict(payload)
    uri = _text(ref_payload.get("uri"))
    if uri:
        try:
            owner_pack, object_kind, object_id = _split_object_uri(uri)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_object_ref",
                    "message": str(exc),
                },
            ) from exc
        ref_payload.setdefault("owner_pack", owner_pack)
        ref_payload.setdefault("object_kind", object_kind)
        ref_payload.setdefault("object_id", object_id)
    elif ref_payload.get("owner_pack") and ref_payload.get("object_kind") and ref_payload.get("object_id"):
        ref_payload["uri"] = (
            f"mindscape://{ref_payload['owner_pack']}/"
            f"{ref_payload['object_kind']}/{ref_payload['object_id']}"
        )
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_object_ref",
                "message": "object_ref requires uri or owner_pack, object_kind, and object_id.",
            },
        )
    ref_payload["workspace_id"] = ref_payload.get("workspace_id") or workspace_id
    try:
        return ObjectRef(**ref_payload)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_object_ref",
                "message": str(exc),
            },
        ) from exc

def _validate_catalog_object_ref(
    *,
    registry: ObjectCatalogRegistry,
    workspace_id: str,
    ref: ObjectRef,
    error_code: str = "object_kind_not_declared",
) -> Dict[str, Any]:
    _validate_object_ref_identity(ref, workspace_id)
    entry_payload = registry.get_entry(ref.owner_pack, ref.object_kind)
    if not entry_payload:
        raise HTTPException(
            status_code=404,
            detail={
                "code": error_code,
                "message": "ObjectRef does not map to an installed addressable object kind.",
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                    "object_id": ref.object_id,
                },
            },
        )
    return entry_payload

async def _invoke_backend_callable(backend_path: str, **kwargs: Any) -> Any:
    module_path, attr_name = backend_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    try:
        target = getattr(module, attr_name)
    except AttributeError:
        importlib.invalidate_caches()
        module = importlib.reload(module)
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


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
