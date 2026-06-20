"""Dispatch lanes for visual acceptance follow-up requests."""

from typing import Any, Dict, Optional

from .artifacts import (
    get_visual_acceptance_artifacts_store,
    _upsert_dispatch_artifact,
    _upsert_scene_review_artifact,
)
from .constants import (
    FOLLOWUP_REQUEST_STATE_BLOCKED,
    FOLLOWUP_REQUEST_STATE_COMPLETED,
    FOLLOWUP_REQUEST_STATE_DISPATCHED,
    FOLLOWUP_REQUEST_STATE_READY,
    VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
    VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
)
from .dependencies import (
    Artifact,
    FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
    normalize_followup_action_id,
    normalize_followup_consumer_kind,
    normalize_followup_lane_id,
)
from .dispatch_payloads import (
    _build_local_scene_review_request,
    _build_single_scene_storyboard,
    _bundle_content_from_request,
    _capability_owned_consumer_handoff_result,
    _dispatch_payload,
    _project_id_from_request,
    _source_type_from_request,
)
from .laf_payloads import _build_laf_patch_request
from .lifecycle import persist_followup_request_state


async def dispatch_followup_request(
    *,
    artifact: Artifact,
    actor_id: str = "",
    notes: str = "",
    artifacts_store: Optional[Any] = None,
) -> Dict[str, Any]:
    metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
    if metadata.get("kind") != VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND:
        raise ValueError("artifact_not_visual_acceptance_followup_request")

    content = dict(artifact.content or {}) if isinstance(artifact.content, dict) else {}
    request_state = str(content.get("request_state") or "").strip().lower()
    if request_state != FOLLOWUP_REQUEST_STATE_READY:
        raise ValueError(f"followup_request_not_ready:{request_state or 'missing'}")

    lane_id = normalize_followup_lane_id(content.get("lane_id"))
    content["lane_id"] = lane_id or None
    content["consumer_kind"] = (
        normalize_followup_consumer_kind(content.get("consumer_kind")) or None
    )
    content["action_ids"] = [
        normalize_followup_action_id(action_id)
        for action_id in (content.get("action_ids") or [])
        if normalize_followup_action_id(action_id)
    ]
    workspace_id = str(content.get("workspace_id") or "").strip()
    if not workspace_id:
        raise ValueError("followup_request_missing_workspace_id")

    store = artifacts_store or get_visual_acceptance_artifacts_store()

    if lane_id == "rerender":
        storyboard = _build_single_scene_storyboard(content)
        source_type = _source_type_from_request(content)
        dispatch_payload = _dispatch_payload(
            request_content=content,
            dispatch_mode="execute_storyboard",
            dispatch_status="running",
            actor_id=actor_id,
            notes=notes,
            storyboard=storyboard,
        )
        dispatch_artifact = _upsert_dispatch_artifact(
            workspace_id=workspace_id,
            payload=dispatch_payload,
            artifacts_store=store,
        )

        try:
            try:
                from app.capabilities.multi_media_studio.tools.storyboard_execution import (
                    execute_storyboard,
                )
            except ImportError:
                from backend.app.capabilities.multi_media_studio.tools.storyboard_execution import (
                    execute_storyboard,
                )

            result = await execute_storyboard(
                project_id=_project_id_from_request(content),
                storyboard=storyboard,
                source_type=source_type,
                tenant_id="default",
            )
            result_payload = dict(result or {})
            dispatch_status = "completed"
            request_transition_state = FOLLOWUP_REQUEST_STATE_COMPLETED
            if not result_payload.get("success", False):
                dispatch_status = "failed"
                request_transition_state = FOLLOWUP_REQUEST_STATE_BLOCKED
            elif str(result_payload.get("status") or "").strip().lower() == "blocked":
                dispatch_status = "blocked"
                request_transition_state = FOLLOWUP_REQUEST_STATE_BLOCKED

            finalized_dispatch = dict(dispatch_payload)
            finalized_dispatch["dispatch_status"] = dispatch_status
            finalized_dispatch["dispatch_result"] = result_payload
            dispatch_artifact = _upsert_dispatch_artifact(
                workspace_id=workspace_id,
                payload=finalized_dispatch,
                artifacts_store=store,
            )
            updated_request = persist_followup_request_state(
                artifact=artifact,
                request_state=request_transition_state,
                actor_id=actor_id,
                notes=notes or f"rerender_{dispatch_status}",
                execution_ref={
                    "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                    "artifact_id": dispatch_artifact.id,
                    "lane_id": lane_id,
                    "dispatch_status": dispatch_status,
                    "run_id": result_payload.get("run_id"),
                    "result_status": result_payload.get("status"),
                },
                artifacts_store=store,
            )
            return {
                "request_artifact": updated_request,
                "dispatch_artifact": dispatch_artifact,
                "dispatch_status": dispatch_status,
                "dispatch_result": result_payload,
            }
        except Exception as exc:
            failed_payload = dict(dispatch_payload)
            failed_payload["dispatch_status"] = "failed"
            failed_payload["dispatch_result"] = {"success": False, "error": str(exc)}
            dispatch_artifact = _upsert_dispatch_artifact(
                workspace_id=workspace_id,
                payload=failed_payload,
                artifacts_store=store,
            )
            updated_request = persist_followup_request_state(
                artifact=artifact,
                request_state=FOLLOWUP_REQUEST_STATE_BLOCKED,
                actor_id=actor_id,
                notes=notes or str(exc),
                execution_ref={
                    "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                    "artifact_id": dispatch_artifact.id,
                    "lane_id": lane_id,
                    "dispatch_status": "failed",
                    "error": str(exc),
                },
                artifacts_store=store,
            )
            return {
                "request_artifact": updated_request,
                "dispatch_artifact": dispatch_artifact,
                "dispatch_status": "failed",
                "dispatch_result": {"success": False, "error": str(exc)},
            }

    if lane_id == "laf_patch":
        storyboard = _build_single_scene_storyboard(content)
        source_type = _source_type_from_request(content)
        project_id = _project_id_from_request(content)
        extract_request = _build_laf_patch_request(content)
        dispatch_payload = _dispatch_payload(
            request_content=content,
            dispatch_mode="extract_patch_execute_storyboard",
            dispatch_status="running",
            actor_id=actor_id,
            notes=notes,
            dispatch_result={"laf_extract_request": dict(extract_request)},
            storyboard=storyboard,
        )
        dispatch_artifact = _upsert_dispatch_artifact(
            workspace_id=workspace_id,
            payload=dispatch_payload,
            artifacts_store=store,
        )

        try:
            try:
                from app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints import (
                    ObjectExtractRequest,
                    extract_object_assets,
                )
            except ImportError:
                from backend.app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints import (
                    ObjectExtractRequest,
                    extract_object_assets,
                )

            try:
                from app.capabilities.multi_media_studio.tools.storyboard_execution import (
                    execute_storyboard,
                )
            except ImportError:
                from backend.app.capabilities.multi_media_studio.tools.storyboard_execution import (
                    execute_storyboard,
                )

            try:
                from app.capabilities.multi_media_studio.tools.storyboard_patch import (
                    apply_storyboard_scene_patch,
                )
            except ImportError:
                from backend.app.capabilities.multi_media_studio.tools.storyboard_patch import (
                    apply_storyboard_scene_patch,
                )

            extract_result = await extract_object_assets(
                request=ObjectExtractRequest(**extract_request),
                tenant_id="default",
            )
            extract_job = dict((extract_result or {}).get("job") or {})
            storyboard_scene_patch = (
                dict(extract_job.get("storyboard_scene_patch") or {})
                if isinstance(extract_job.get("storyboard_scene_patch"), dict)
                else {}
            )
            if not storyboard_scene_patch:
                raise ValueError("followup_dispatch_missing_storyboard_scene_patch")

            patched_result = await apply_storyboard_scene_patch(
                storyboard=storyboard,
                scene_id=str(content.get("scene_id") or "").strip(),
                storyboard_scene_patch=storyboard_scene_patch,
                tenant_id="default",
            )
            if not bool(patched_result.get("success")):
                raise ValueError(
                    str(patched_result.get("error") or "followup_dispatch_patch_failed")
                )
            patched_storyboard = (
                dict(patched_result.get("storyboard") or {})
                if isinstance(patched_result.get("storyboard"), dict)
                else {}
            )
            if not patched_storyboard:
                raise ValueError("followup_dispatch_missing_patched_storyboard")

            result = await execute_storyboard(
                project_id=project_id,
                storyboard=patched_storyboard,
                source_type=source_type,
                tenant_id="default",
            )
            result_payload = {
                "laf_extract_job_id": extract_job.get("job_id"),
                "laf_extract_status": extract_job.get("status"),
                "patched_scene_id": patched_result.get("patched_scene_id"),
                **dict(result or {}),
            }
            dispatch_status = "completed"
            request_transition_state = FOLLOWUP_REQUEST_STATE_COMPLETED
            if not result_payload.get("success", False):
                dispatch_status = "failed"
                request_transition_state = FOLLOWUP_REQUEST_STATE_BLOCKED
            elif str(result_payload.get("status") or "").strip().lower() == "blocked":
                dispatch_status = "blocked"
                request_transition_state = FOLLOWUP_REQUEST_STATE_BLOCKED

            finalized_dispatch = dict(dispatch_payload)
            finalized_dispatch["dispatch_status"] = dispatch_status
            finalized_dispatch["dispatch_result"] = result_payload
            finalized_dispatch["storyboard"] = patched_storyboard
            finalized_dispatch["laf_extract_request"] = dict(extract_request)
            finalized_dispatch["storyboard_scene_patch"] = storyboard_scene_patch
            dispatch_artifact = _upsert_dispatch_artifact(
                workspace_id=workspace_id,
                payload=finalized_dispatch,
                artifacts_store=store,
            )
            updated_request = persist_followup_request_state(
                artifact=artifact,
                request_state=request_transition_state,
                actor_id=actor_id,
                notes=notes or f"laf_patch_{dispatch_status}",
                execution_ref={
                    "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                    "artifact_id": dispatch_artifact.id,
                    "lane_id": lane_id,
                    "dispatch_status": dispatch_status,
                    "laf_extract_job_id": extract_job.get("job_id"),
                    "run_id": result_payload.get("run_id"),
                    "result_status": result_payload.get("status"),
                },
                artifacts_store=store,
            )
            return {
                "request_artifact": updated_request,
                "dispatch_artifact": dispatch_artifact,
                "dispatch_status": dispatch_status,
                "dispatch_result": result_payload,
            }
        except Exception as exc:
            failed_payload = dict(dispatch_payload)
            failed_payload["dispatch_status"] = "failed"
            failed_payload["dispatch_result"] = {
                "success": False,
                "error": str(exc),
                "laf_extract_request": dict(extract_request),
            }
            dispatch_artifact = _upsert_dispatch_artifact(
                workspace_id=workspace_id,
                payload=failed_payload,
                artifacts_store=store,
            )
            updated_request = persist_followup_request_state(
                artifact=artifact,
                request_state=FOLLOWUP_REQUEST_STATE_BLOCKED,
                actor_id=actor_id,
                notes=notes or str(exc),
                execution_ref={
                    "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                    "artifact_id": dispatch_artifact.id,
                    "lane_id": lane_id,
                    "dispatch_status": "failed",
                    "error": str(exc),
                },
                artifacts_store=store,
            )
            return {
                "request_artifact": updated_request,
                "dispatch_artifact": dispatch_artifact,
                "dispatch_status": "failed",
                "dispatch_result": {
                    "success": False,
                    "error": str(exc),
                    "laf_extract_request": dict(extract_request),
                },
            }

    if lane_id == FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF:
        dispatch_result = _capability_owned_consumer_handoff_result(content)
        dispatch_payload = _dispatch_payload(
            request_content=content,
            dispatch_mode="consumer_handoff",
            dispatch_status="pending_worker",
            actor_id=actor_id,
            notes=notes,
            dispatch_result=dispatch_result,
        )
        dispatch_artifact = _upsert_dispatch_artifact(
            workspace_id=workspace_id,
            payload=dispatch_payload,
            artifacts_store=store,
        )
        updated_request = persist_followup_request_state(
            artifact=artifact,
            request_state=FOLLOWUP_REQUEST_STATE_DISPATCHED,
            actor_id=actor_id,
            notes=notes or "handoff_to_capability_owned_consumer",
            execution_ref={
                "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                "artifact_id": dispatch_artifact.id,
                "lane_id": lane_id,
                "dispatch_status": "pending_worker",
                "dispatch_mode": "consumer_handoff",
            },
            artifacts_store=store,
        )
        return {
            "request_artifact": updated_request,
            "dispatch_artifact": dispatch_artifact,
            "dispatch_status": "pending_worker",
            "dispatch_result": dispatch_result,
        }

    if lane_id == "local_scene_review":
        bundle_content = _bundle_content_from_request(content, store)
        scene_review_request = _build_local_scene_review_request(
            request_content=content,
            bundle_content=bundle_content,
        )
        scene_review_artifact = _upsert_scene_review_artifact(
            workspace_id=workspace_id,
            payload=scene_review_request,
            artifacts_store=store,
        )
        dispatch_payload = _dispatch_payload(
            request_content=content,
            dispatch_mode="manual_scene_review_queue",
            dispatch_status="queued",
            actor_id=actor_id,
            notes=notes,
            dispatch_result={
                "success": True,
                "mode": "manual_scene_review_queue",
                "scene_review_artifact_id": scene_review_artifact.id,
                "scene_review_request": scene_review_request,
                "execution_strategy": "workspace_artifact_manual_queue",
            },
        )
        dispatch_artifact = _upsert_dispatch_artifact(
            workspace_id=workspace_id,
            payload=dispatch_payload,
            artifacts_store=store,
        )
        updated_request = persist_followup_request_state(
            artifact=artifact,
            request_state=FOLLOWUP_REQUEST_STATE_DISPATCHED,
            actor_id=actor_id,
            notes=notes or "queued_to_local_scene_review",
            execution_ref={
                "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                "artifact_id": dispatch_artifact.id,
                "lane_id": lane_id,
                "dispatch_status": "queued",
                "dispatch_mode": "manual_scene_review_queue",
                "scene_review_artifact_id": scene_review_artifact.id,
            },
            artifacts_store=store,
        )
        return {
            "request_artifact": updated_request,
            "dispatch_artifact": dispatch_artifact,
            "consumer_artifact": scene_review_artifact,
            "dispatch_status": "queued",
            "dispatch_result": {
                "success": True,
                "mode": "manual_scene_review_queue",
                "scene_review_artifact_id": scene_review_artifact.id,
                "scene_review_request": scene_review_request,
                "execution_strategy": "workspace_artifact_manual_queue",
            },
        }

    raise ValueError(f"unsupported_followup_lane:{lane_id or 'missing'}")
