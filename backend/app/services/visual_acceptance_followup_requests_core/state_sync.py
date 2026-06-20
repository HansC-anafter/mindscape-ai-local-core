"""State synchronization helpers for visual follow-up request transitions."""

import json
from pathlib import Path
from typing import Any, Dict, List

from .dependencies import Artifact
from .identifiers import _utc_now_iso


def _write_bundle_manifest(bundle: Dict[str, Any], manifest_path: str) -> None:
    candidate = Path(str(manifest_path or "").strip())
    if not candidate:
        return
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")


def _state_counts(refs: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        state = str(ref.get("request_state") or "").strip()
        if not state:
            continue
        counts[state] = counts.get(state, 0) + 1
    return counts


def _sync_followup_request_state_to_bundle(
    *,
    request_artifact: Artifact,
    request_content: Dict[str, Any],
    transition_event: Dict[str, Any],
    artifacts_store: Any,
) -> None:
    review_bundle_id = str(request_content.get("review_bundle_id") or "").strip()
    if not review_bundle_id:
        return
    bundle_artifact = artifacts_store.get_artifact(review_bundle_id)
    if not bundle_artifact:
        return
    bundle_content = (
        dict(bundle_artifact.content or {})
        if isinstance(bundle_artifact.content, dict)
        else {}
    )
    bundle_metadata = (
        dict(bundle_artifact.metadata or {})
        if isinstance(bundle_artifact.metadata, dict)
        else {}
    )
    request_refs = [
        dict(item)
        for item in (bundle_content.get("followup_request_refs") or [])
        if isinstance(item, dict)
    ]
    updated_refs: List[Dict[str, Any]] = []
    for ref in request_refs:
        item = dict(ref)
        if str(item.get("artifact_id") or "").strip() == request_artifact.id:
            item["request_state"] = request_content.get("request_state")
            item["blocking_reason"] = request_content.get("blocking_reason")
            item["last_transition"] = transition_event
        updated_refs.append(item)
    bundle_content["followup_request_refs"] = updated_refs
    latest_review = (
        dict(bundle_content.get("latest_review_decision") or {})
        if isinstance(bundle_content.get("latest_review_decision"), dict)
        else {}
    )
    if latest_review:
        latest_review["followup_request_refs"] = updated_refs
        bundle_content["latest_review_decision"] = latest_review
    history = bundle_content.get("review_decisions")
    if isinstance(history, list) and history:
        last_item = history[-1]
        if isinstance(last_item, dict):
            updated_last = dict(last_item)
            updated_last["followup_request_refs"] = updated_refs
            history[-1] = updated_last
            bundle_content["review_decisions"] = history
    bundle_metadata["followup_request_count"] = len(updated_refs)
    bundle_metadata["followup_request_state_counts"] = _state_counts(updated_refs)
    manifest_path = str(bundle_metadata.get("manifest_path") or "").strip()
    if manifest_path:
        _write_bundle_manifest(bundle_content, manifest_path)
    artifacts_store.update_artifact(
        bundle_artifact.id,
        content=bundle_content,
        metadata=bundle_metadata,
    )


def _sync_followup_request_state_to_run(
    *,
    request_artifact: Artifact,
    request_content: Dict[str, Any],
    transition_event: Dict[str, Any],
) -> None:
    tenant_id = "default"
    run_id = str(request_content.get("run_id") or "").strip()
    scene_id = str(request_content.get("scene_id") or "").strip()
    if not run_id or not scene_id:
        return
    try:
        try:
            from app.capabilities.multi_media_studio.models import production_run
        except ImportError:
            from backend.app.capabilities.multi_media_studio.models import production_run
        run = production_run.find_run(tenant_id, run_id)
        if not run:
            return
        scene_results = run.get("scene_results") if isinstance(run.get("scene_results"), list) else []
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
            request_refs = [
                dict(item)
                for item in (provider_metadata.get("followup_request_refs") or [])
                if isinstance(item, dict)
            ]
            updated_refs: List[Dict[str, Any]] = []
            for ref in request_refs:
                item = dict(ref)
                if str(item.get("artifact_id") or "").strip() == request_artifact.id:
                    item["request_state"] = request_content.get("request_state")
                    item["blocking_reason"] = request_content.get("blocking_reason")
                    item["last_transition"] = transition_event
                updated_refs.append(item)
            provider_metadata["followup_request_refs"] = updated_refs
            review_decision_ref = (
                dict(provider_metadata.get("review_decision_ref") or {})
                if isinstance(provider_metadata.get("review_decision_ref"), dict)
                else {}
            )
            if review_decision_ref:
                review_decision_ref["followup_request_refs"] = updated_refs
                provider_metadata["review_decision_ref"] = review_decision_ref
            bundle_refs = provider_metadata.get("review_bundle_refs")
            updated_bundle_refs: List[Dict[str, Any]] = []
            for bundle_ref in bundle_refs or []:
                if not isinstance(bundle_ref, dict):
                    continue
                item = dict(bundle_ref)
                item["followup_request_refs"] = updated_refs
                review_decision = (
                    dict(item.get("review_decision") or {})
                    if isinstance(item.get("review_decision"), dict)
                    else {}
                )
                if review_decision:
                    review_decision["followup_request_refs"] = updated_refs
                    item["review_decision"] = review_decision
                updated_bundle_refs.append(item)
            if updated_bundle_refs:
                provider_metadata["review_bundle_refs"] = updated_bundle_refs
            scene_result["provider_metadata"] = provider_metadata
            updated = True
            break
        if updated:
            run["updated_at"] = _utc_now_iso()
            production_run._save_run(tenant_id, run["project_id"], run)  # type: ignore[attr-defined]
    except Exception:
        return
