from pathlib import Path
import json
import sys

import pytest

LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from backend.app.capabilities.multi_media_studio.models import production_run
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services import visual_acceptance_followup_requests


class _FakeArtifactsStore:
    def __init__(self):
        self.artifacts: dict[str, Artifact] = {}

    def get_artifact(self, artifact_id: str):
        return self.artifacts.get(artifact_id)

    def create_artifact(self, artifact: Artifact):
        self.artifacts[artifact.id] = artifact
        return artifact

    def update_artifact(self, artifact_id: str, **kwargs):
        artifact = self.artifacts[artifact_id]
        self.artifacts[artifact_id] = artifact.model_copy(update=kwargs)
        return True

    def list_artifacts_by_workspace(self, workspace_id: str, limit=None, offset: int = 0):
        return [
            artifact
            for artifact in self.artifacts.values()
            if str(artifact.workspace_id or "").strip() == workspace_id
        ]


def _seed_followup_bundle_and_run(
    *,
    store: _FakeArtifactsStore,
    tmp_path: Path,
    lane_id: str,
    consumer_kind: str,
    request_state: str = "ready",
    review_status: str = "accepted",
    review_decision: str = "accepted",
    review_notes: str = "looks good",
):
    manifest_path = tmp_path / f"vrb_{lane_id}.json"
    run = production_run.create_run(
        tenant_id="default",
        project_id="proj_followup_demo",
        storyboard_id="sb_followup_demo",
        source_type="generative",
    )
    followup_ref = {
        "artifact_id": f"vafreq_vrb_demo_{lane_id}",
        "lane_id": lane_id,
        "consumer_kind": consumer_kind,
        "request_state": request_state,
        "blocking_reason": None,
    }
    production_run.update_scene_result(
        "default",
        "proj_followup_demo",
        run["run_id"],
        "A01",
        status="completed",
        provider_metadata={
            "visual_acceptance_state": review_status,
            "followup_request_refs": [dict(followup_ref)],
            "review_decision_ref": {
                "artifact_id": "vrb_demo",
                "decision": review_decision,
                "notes": review_notes,
                "followup_request_refs": [dict(followup_ref)],
            },
            "review_bundle_refs": [
                {
                    "artifact_id": "vrb_demo",
                    "review_bundle_id": "vrb_demo",
                    "status": review_status,
                    "followup_request_refs": [dict(followup_ref)],
                    "review_decision": {
                        "decision": review_decision,
                        "notes": review_notes,
                        "followup_request_refs": [dict(followup_ref)],
                    },
                }
            ],
        },
    )

    bundle = {
        "review_bundle_id": "vrb_demo",
        "workspace_id": "ws_demo",
        "tenant_id": "default",
        "project_id": "proj_followup_demo",
        "run_id": run["run_id"],
        "scene_id": "A01",
        "source_kind": "vr_render",
        "status": review_status,
        "latest_review_decision": {
            "decision": review_decision,
            "notes": review_notes,
            "checklist_scores": {"contact_zone_naturalness": 0.2},
            "followup_request_refs": [dict(followup_ref)],
        },
        "review_decisions": [
            {
                "decision": review_decision,
                "notes": review_notes,
                "checklist_scores": {"contact_zone_naturalness": 0.2},
                "followup_request_refs": [dict(followup_ref)],
            }
        ],
        "followup_request_refs": [dict(followup_ref)],
    }
    manifest_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    store.create_artifact(
        Artifact(
            id="vrb_demo",
            workspace_id="ws_demo",
            execution_id=f"visual_acceptance:{run['run_id']}:A01",
            playbook_code="visual_acceptance_review",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Bundle: A01",
            summary="bundle",
            content=bundle,
            storage_ref=str(manifest_path),
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": "visual_acceptance_bundle",
                "review_bundle_id": "vrb_demo",
                "manifest_path": str(manifest_path),
            },
        )
    )
    return run, manifest_path
