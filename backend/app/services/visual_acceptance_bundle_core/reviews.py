"""Review decision persistence for visual acceptance bundles."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .artifacts import (
    load_visual_acceptance_bundle_for_artifact,
    write_bundle_manifest,
)
from .dependencies import (
    Artifact,
    FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
    PostgresArtifactsStore,
    build_followup_action_plan,
    materialize_followup_request_artifacts,
    normalize_review_checklist_scores,
)
from .normalizers import get_visual_acceptance_artifacts_store, utc_now_iso

logger = logging.getLogger("backend.app.services.visual_acceptance_bundle")


def sync_review_decision_to_run(
    *,
    bundle: Dict[str, Any],
    artifact_id: str,
    decision_payload: Dict[str, Any],
) -> None:
    tenant_id = str(bundle.get("tenant_id") or "").strip() or "default"
    project_id = str(bundle.get("project_id") or "").strip()
    run_id = str(bundle.get("run_id") or "").strip()
    scene_id = str(bundle.get("scene_id") or "").strip()
    if not project_id or not run_id or not scene_id:
        return

    try:
        try:
            from app.capabilities.multi_media_studio.models import production_run
        except ImportError:
            from backend.app.capabilities.multi_media_studio.models import (
                production_run,
            )

        followup_actions = [
            str(item or "").strip()
            for item in (decision_payload.get("followup_actions") or [])
            if str(item or "").strip()
        ]
        followup_request_refs = [
            dict(item)
            for item in (decision_payload.get("followup_request_refs") or [])
            if isinstance(item, dict)
        ]
        downstream_action_plan = (
            dict(decision_payload.get("downstream_action_plan") or {})
            if isinstance(decision_payload.get("downstream_action_plan"), dict)
            else build_followup_action_plan(
                review_bundle_id=str(bundle.get("review_bundle_id") or artifact_id),
                decision=str(decision_payload.get("decision") or ""),
                run_id=run_id,
                scene_id=scene_id,
                source_kind=str(bundle.get("source_kind") or ""),
                package_id=str(bundle.get("package_id") or ""),
                preset_id=str(bundle.get("preset_id") or ""),
                artifact_ids=bundle.get("artifact_ids") or [],
                binding_mode=str(bundle.get("binding_mode") or ""),
                followup_actions=followup_actions,
            )
        )
        run = production_run.get_run(tenant_id, project_id, run_id)
        if not run:
            return
        scene_results = (
            run.get("scene_results") if isinstance(run.get("scene_results"), list) else []
        )
        updated = False
        for scene_result in scene_results:
            if not isinstance(scene_result, dict):
                continue
            if str(scene_result.get("scene_id") or "").strip() != scene_id:
                continue
            provider_metadata = (
                dict(scene_result.get("provider_metadata") or {})
                if isinstance(scene_result.get("provider_metadata"), dict)
                else {}
            )
            provider_metadata["visual_acceptance_state"] = decision_payload["decision"]
            provider_metadata["review_decision_ref"] = {
                "artifact_id": artifact_id,
                "decision": decision_payload["decision"],
                "reviewed_at": decision_payload["reviewed_at"],
                "reviewer_id": str(decision_payload.get("reviewer_id") or "").strip()
                or None,
                "followup_actions": followup_actions,
                "downstream_action_plan": downstream_action_plan,
                "followup_request_refs": followup_request_refs,
            }
            provider_metadata["downstream_action_plan"] = downstream_action_plan
            provider_metadata["followup_request_refs"] = followup_request_refs
            bundle_refs = provider_metadata.get("review_bundle_refs")
            updated_refs: List[Dict[str, Any]] = []
            for bundle_ref in bundle_refs or []:
                if not isinstance(bundle_ref, dict):
                    continue
                item = dict(bundle_ref)
                if str(item.get("artifact_id") or "").strip() == artifact_id:
                    item["status"] = decision_payload["decision"]
                    item["review_decision"] = {
                        "decision": decision_payload["decision"],
                        "reviewed_at": decision_payload["reviewed_at"],
                        "reviewer_id": str(
                            decision_payload.get("reviewer_id") or ""
                        ).strip()
                        or None,
                        "followup_actions": followup_actions,
                        "downstream_action_plan": downstream_action_plan,
                        "followup_request_refs": followup_request_refs,
                    }
                    item["downstream_action_plan"] = downstream_action_plan
                    item["followup_request_refs"] = followup_request_refs
                updated_refs.append(item)
            if updated_refs:
                provider_metadata["review_bundle_refs"] = updated_refs
            scene_result["provider_metadata"] = provider_metadata
            updated = True
            break
        if updated:
            run["updated_at"] = utc_now_iso()
            production_run._save_run(tenant_id, project_id, run)  # type: ignore[attr-defined]
    except Exception:
        logger.warning(
            "failed to sync visual acceptance review decision to run run=%s scene=%s",
            run_id,
            scene_id,
            exc_info=True,
        )


def persist_visual_acceptance_review_decision(
    *,
    artifact: Artifact,
    decision_payload: Dict[str, Any],
    artifacts_store: Optional[PostgresArtifactsStore] = None,
) -> Artifact:
    """Persist a review decision into artifact content/metadata and bundle manifest."""
    bundle = load_visual_acceptance_bundle_for_artifact(artifact)
    metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
    content = dict(bundle or {})
    content["workspace_id"] = str(
        content.get("workspace_id") or artifact.workspace_id or ""
    ).strip()
    checklist_template = content.get("checklist_template")
    normalized_scores = normalize_review_checklist_scores(
        decision_payload.get("checklist_scores")
        if isinstance(decision_payload, dict)
        else None,
        checklist_template=checklist_template
        if isinstance(checklist_template, list)
        else None,
    )
    decision_payload = dict(decision_payload)
    decision_payload["checklist_scores"] = normalized_scores
    decision_payload["checklist_summary"] = {
        "scored_checks": len(normalized_scores),
        "average_score": (
            round(sum(normalized_scores.values()) / len(normalized_scores), 3)
            if normalized_scores
            else None
        ),
    }
    downstream_action_plan = build_followup_action_plan(
        review_bundle_id=str(
            content.get("review_bundle_id")
            or decision_payload.get("review_bundle_id")
            or artifact.id
        ),
        decision=str(decision_payload.get("decision") or ""),
        run_id=str(content.get("run_id") or ""),
        scene_id=str(content.get("scene_id") or ""),
        source_kind=str(content.get("source_kind") or ""),
        package_id=str(content.get("package_id") or ""),
        preset_id=str(content.get("preset_id") or ""),
        artifact_ids=content.get("artifact_ids") or [],
        binding_mode=str(content.get("binding_mode") or ""),
        followup_actions=decision_payload.get("followup_actions"),
    )
    decision_payload["downstream_action_plan"] = downstream_action_plan
    history = content.get("review_decisions")
    history_items = (
        [dict(item) for item in history if isinstance(item, dict)]
        if isinstance(history, list)
        else []
    )
    history_items.append(dict(decision_payload))
    content["review_decisions"] = history_items
    content["latest_review_decision"] = dict(decision_payload)
    content["status"] = decision_payload["decision"]
    content["downstream_action_plan"] = dict(downstream_action_plan)

    metadata["visual_acceptance_state"] = decision_payload["decision"]
    metadata["review_decision"] = dict(decision_payload)
    metadata["review_decision_count"] = len(history_items)
    metadata["followup_action_ids"] = list(downstream_action_plan.get("action_ids") or [])
    metadata["downstream_lane_ids"] = list(downstream_action_plan.get("lane_ids") or [])
    metadata[FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY] = bool(
        downstream_action_plan.get(FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY)
    )

    manifest_path = str(metadata.get("manifest_path") or "").strip()
    if manifest_path:
        write_bundle_manifest(content, Path(manifest_path))

    store = artifacts_store or get_visual_acceptance_artifacts_store()
    store.update_artifact(
        artifact.id,
        content=content,
        metadata=metadata,
    )
    updated_artifact = store.get_artifact(artifact.id)
    final_artifact = updated_artifact or artifact.model_copy(
        update={"content": content, "metadata": metadata}
    )
    followup_request_refs = materialize_followup_request_artifacts(
        bundle=content,
        decision_payload=decision_payload,
        artifacts_store=store,
    )
    decision_payload["followup_request_refs"] = followup_request_refs
    content["latest_review_decision"] = dict(decision_payload)
    content["review_decisions"][-1] = dict(decision_payload)
    content["followup_request_refs"] = followup_request_refs
    metadata["followup_request_count"] = len(followup_request_refs)
    if manifest_path:
        write_bundle_manifest(content, Path(manifest_path))
    store.update_artifact(
        artifact.id,
        content=content,
        metadata=metadata,
    )
    updated_artifact = store.get_artifact(artifact.id)
    final_artifact = updated_artifact or artifact.model_copy(
        update={"content": content, "metadata": metadata}
    )
    sync_review_decision_to_run(
        bundle=content,
        artifact_id=artifact.id,
        decision_payload=decision_payload,
    )
    return final_artifact
