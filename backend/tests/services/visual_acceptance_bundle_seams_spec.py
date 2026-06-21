from __future__ import annotations

import json
import sys
from pathlib import Path

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

from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services import visual_acceptance_bundle
from backend.app.services.visual_acceptance_bundle_core import artifacts, reviews


class FakeArtifactsStore:
    def __init__(self) -> None:
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


def test_publish_visual_acceptance_bundle_preserves_manifest_and_artifact_path(
    tmp_path, monkeypatch
) -> None:
    store = FakeArtifactsStore()
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(artifacts, "get_visual_acceptance_artifacts_store", lambda: store)

    scene = {
        "scene_id": "A01",
        "scene_manifest": {"scene_id": "A01"},
        "object_assets": [
            {
                "object_target_id": "hero",
                "asset_ref": {"storage_key": "layer_asset_forge/assets/hero.png"},
                "metadata": {"mask_storage_key": "layer_asset_forge/masks/hero.png"},
            }
        ],
    }

    bundle_ref = visual_acceptance_bundle.publish_visual_acceptance_bundle(
        tenant_id="default",
        project_id="proj_demo",
        run_id="run_demo",
        workspace_id="ws_demo",
        scene=scene,
        source_kind=visual_acceptance_bundle.SOURCE_KIND_VR_RENDER,
        render_status="completed",
        renderer="video_renderer",
        clip_refs=[{"storage_key": "video_renderer/renders/a01.mp4"}],
        context_metadata={
            "package_id": "charpkg_demo",
            "preset_id": "preset_alpha",
            "artifact_id": "artifact_alpha",
            "binding_mode": "hybrid",
        },
    )

    assert bundle_ref["kind"] == visual_acceptance_bundle.VISUAL_ACCEPTANCE_ARTIFACT_KIND
    assert bundle_ref["artifact_id"] == bundle_ref["review_bundle_id"]
    assert bundle_ref["manifest_path"].startswith(str(tmp_path))
    assert bundle_ref["artifact_ids"] == ["artifact_alpha"]

    manifest = json.loads(Path(bundle_ref["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["scene_id"] == "A01"
    assert manifest["package_id"] == "charpkg_demo"
    assert len(manifest["slots"]) == 2
    assert manifest["slots"][0]["preview_url"].endswith(
        "/layer_asset_forge/assets/hero.png"
    )
    assert bundle_ref["artifact_id"] in store.artifacts


def test_persist_visual_acceptance_review_decision_uses_single_store_path(
    tmp_path, monkeypatch
) -> None:
    store = FakeArtifactsStore()
    monkeypatch.setattr(reviews, "get_visual_acceptance_artifacts_store", lambda: store)
    monkeypatch.setattr(
        reviews,
        "materialize_followup_request_artifacts",
        lambda *, bundle, decision_payload, artifacts_store: [],
    )
    monkeypatch.setattr(reviews, "sync_review_decision_to_run", lambda **kwargs: None)

    manifest_path = tmp_path / "bundle.json"
    bundle = {
        "review_bundle_id": "vrb_demo",
        "workspace_id": "ws_demo",
        "tenant_id": "default",
        "project_id": "proj_demo",
        "run_id": "run_demo",
        "scene_id": "A01",
        "source_kind": "vr_render",
        "package_id": "charpkg_demo",
        "preset_id": "preset_alpha",
        "artifact_ids": ["artifact_alpha"],
        "binding_mode": "hybrid",
        "checklist_template": [{"id": "composition", "weight": 1}],
    }
    manifest_path.write_text(json.dumps(bundle), encoding="utf-8")
    artifact = Artifact(
        id="vrb_demo",
        workspace_id="ws_demo",
        execution_id="visual_acceptance:run_demo:A01",
        playbook_code="visual_acceptance_review",
        artifact_type=ArtifactType.DATA,
        title="bundle",
        summary="bundle",
        content=bundle,
        storage_ref=str(manifest_path),
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata={
            "kind": "visual_acceptance_bundle",
            "manifest_path": str(manifest_path),
        },
    )
    store.create_artifact(artifact)

    updated = visual_acceptance_bundle.persist_visual_acceptance_review_decision(
        artifact=artifact,
        decision_payload={
            "decision": "accepted",
            "reviewed_at": "2026-03-27T00:00:00+00:00",
            "checklist_scores": {"composition": 0.9},
        },
        artifacts_store=store,
    )

    assert updated.metadata["visual_acceptance_state"] == "accepted"
    assert updated.metadata["review_decision_count"] == 1
    assert updated.content["status"] == "accepted"
    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted_manifest["latest_review_decision"]["decision"] == "accepted"
    assert persisted_manifest["followup_request_refs"] == []
