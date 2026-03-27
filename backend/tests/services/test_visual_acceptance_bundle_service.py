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

from backend.app.models.workspace import Artifact
from backend.app.capabilities.multi_media_studio.models import production_run
from backend.app.services.artifact_review_decision import (
    REVIEW_DECISION_ACCEPTED,
    build_artifact_review_decision,
    build_review_checklist_template,
)
from backend.app.services import visual_acceptance_bundle
from shared.schemas.storyboard import ObjectAssetRef, ObjectWorkloadSnapshot, Scene


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


def test_publish_visual_acceptance_bundle_lands_manifest_and_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    fake_store = _FakeArtifactsStore()
    monkeypatch.setattr(
        visual_acceptance_bundle,
        "get_visual_acceptance_artifacts_store",
        lambda: fake_store,
    )

    scene = Scene(
        scene_id="A01",
        scene_manifest={"shot": "close_up"},
        object_assets=[
            ObjectAssetRef(
                asset_ref={"storage_key": "exports/layers/held_prop.png"},
                object_target_id="held_prop",
                object_instance_id="obj_held_prop",
                metadata={
                    "mask_storage_key": "exports/masks/held_prop_mask.png",
                    "alpha_storage_key": "exports/alpha/held_prop_alpha.png",
                },
            )
        ],
        object_workload_snapshot=ObjectWorkloadSnapshot(
            source_scene_id="SC_SOURCE_01",
            source_image_ref={"storage_key": "refs/source_a01.png"},
            impact_region_mode="contact_zone",
            impact_region_bbox={"x": 18, "y": 32, "width": 126, "height": 188},
            affected_object_instance_ids=["obj_held_prop", "obj_person_main"],
            quality_gate_state="auto_approved",
        ),
    )

    bundle_ref = visual_acceptance_bundle.publish_visual_acceptance_bundle(
        tenant_id="default",
        project_id="proj_demo",
        run_id="run_demo",
        workspace_id="ws_demo",
        scene=scene,
        source_kind=visual_acceptance_bundle.SOURCE_KIND_VR_RENDER,
        render_status="completed",
        renderer="video_renderer",
        clip_refs=[
            {
                "storage_key": "renders/a01.mp4",
                "metadata": {
                    "vr_commit_id": "commit_demo",
                    "prompt_id": "prompt_demo",
                    "package_id": "charpkg_demo",
                    "preset_id": "preset_hybrid_demo",
                    "artifact_ids": ["artifact_lora_demo"],
                    "binding_mode": "hybrid",
                },
            }
        ],
        context_metadata={
            "vr_commit_id": "commit_demo",
            "prompt_id": "prompt_demo",
            "package_id": "charpkg_demo",
            "preset_id": "preset_hybrid_demo",
            "artifact_ids": ["artifact_lora_demo"],
            "binding_mode": "hybrid",
            "owning_capability_code": "character_training",
            "source_type": "generative",
            "render_profile": {"profile_id": "vr_preview_local"},
        },
    )

    manifest_path = Path(bundle_ref["manifest_path"])
    assert bundle_ref["artifact_id"] == bundle_ref["review_bundle_id"]
    assert manifest_path.exists()

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["scene_id"] == "A01"
    assert payload["owning_capability_code"] == "character_training"
    assert payload["package_id"] == "charpkg_demo"
    assert payload["preset_id"] == "preset_hybrid_demo"
    assert payload["binding_mode"] == "hybrid"
    assert payload["artifact_ids"] == ["artifact_lora_demo"]
    assert [item["check_id"] for item in payload["checklist_template"]] == [
        "identity_consistency",
        "prompt_following",
        "family_fit",
        "artifact_contamination",
    ]
    assert {slot["slot"] for slot in payload["slots"]} == {"final_layer", "final_render"}
    assert payload["scene_context"]["scene_payload"]["scene_id"] == "A01"
    assert payload["scene_context"]["scene_payload"]["scene_manifest"] == {"shot": "close_up"}
    assert payload["scene_context"]["scene_payload"]["object_workload_snapshot"][
        "source_image_ref"
    ] == {"storage_key": "refs/source_a01.png"}
    assert payload["scene_context"]["object_workload_snapshot"]["impact_region_mode"] == "contact_zone"
    assert payload["source_metadata"]["source_type"] == "generative"
    assert payload["source_metadata"]["render_profile"] == {"profile_id": "vr_preview_local"}
    layer_slot = next(slot for slot in payload["slots"] if slot["slot"] == "final_layer")
    render_slot = next(slot for slot in payload["slots"] if slot["slot"] == "final_render")
    assert layer_slot["preview_url"] == "/api/v1/capabilities/layer_asset_forge/storage/default/exports/layers/held_prop.png"
    assert layer_slot["preview_kind"] == "image"
    assert layer_slot["mask_preview_url"] == "/api/v1/capabilities/layer_asset_forge/storage/default/exports/masks/held_prop_mask.png"
    assert layer_slot["alpha_preview_url"] == "/api/v1/capabilities/layer_asset_forge/storage/default/exports/alpha/held_prop_alpha.png"
    assert render_slot["preview_url"] == "/api/v1/capabilities/video_renderer/storage/default/renders/a01.mp4"
    assert render_slot["preview_kind"] == "video"

    stored_artifact = fake_store.get_artifact(bundle_ref["artifact_id"])
    assert stored_artifact is not None
    assert stored_artifact.metadata["kind"] == visual_acceptance_bundle.VISUAL_ACCEPTANCE_ARTIFACT_KIND
    assert stored_artifact.metadata["owning_capability_code"] == "character_training"
    assert stored_artifact.content["review_bundle_id"] == bundle_ref["review_bundle_id"]


def test_publish_visual_acceptance_bundle_requires_explicit_owner_metadata(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    fake_store = _FakeArtifactsStore()
    monkeypatch.setattr(
        visual_acceptance_bundle,
        "get_visual_acceptance_artifacts_store",
        lambda: fake_store,
    )

    scene = Scene(scene_id="A01", scene_manifest={"shot": "close_up"})

    bundle_ref = visual_acceptance_bundle.publish_visual_acceptance_bundle(
        tenant_id="default",
        project_id="proj_demo",
        run_id="run_demo",
        workspace_id="ws_demo",
        scene=scene,
        source_kind=visual_acceptance_bundle.SOURCE_KIND_CHARACTER_TRAINING_EVAL,
        render_status="completed",
        renderer="video_renderer",
        clip_refs=[
            {
                "storage_key": "renders/a01.png",
                "metadata": {
                    "package_id": "charpkg_demo",
                    "preset_id": "preset_demo",
                    "binding_mode": "reference_only",
                },
            }
        ],
        context_metadata={
            "package_id": "charpkg_demo",
            "preset_id": "preset_demo",
            "binding_mode": "reference_only",
        },
    )

    stored_artifact = fake_store.get_artifact(bundle_ref["artifact_id"])
    assert stored_artifact is not None
    assert bundle_ref["owning_capability_code"] is None
    assert stored_artifact.metadata["owning_capability_code"] is None
    assert stored_artifact.content["owning_capability_code"] is None


def test_publish_visual_acceptance_bundle_bounds_review_bundle_id(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    fake_store = _FakeArtifactsStore()
    monkeypatch.setattr(
        visual_acceptance_bundle,
        "get_visual_acceptance_artifacts_store",
        lambda: fake_store,
    )

    scene = Scene(
        scene_id="A01",
        scene_manifest={"shot": "close_up"},
    )

    bundle_ref = visual_acceptance_bundle.publish_visual_acceptance_bundle(
        tenant_id="default",
        project_id="proj_demo",
        run_id="run_" + ("verylongsegment_" * 6),
        workspace_id="ws_demo",
        scene=scene,
        source_kind=visual_acceptance_bundle.SOURCE_KIND_CHARACTER_TRAINING_EVAL,
        render_status="completed",
        renderer="video_renderer",
        clip_refs=[{"storage_key": "renders/a01.png"}],
        context_metadata={
            "owning_capability_code": "character_training",
            "package_id": "charpkg_demo",
            "artifact_ids": ["artifact_demo"],
            "binding_mode": "reference_only",
        },
    )

    assert len(bundle_ref["review_bundle_id"]) <= 64
    assert bundle_ref["artifact_id"] == bundle_ref["review_bundle_id"]
    stored_artifact = fake_store.get_artifact(bundle_ref["artifact_id"])
    assert stored_artifact is not None
    assert len(str(stored_artifact.execution_id or "")) <= 64


def test_build_artifact_review_decision_validates_decision():
    decision = build_artifact_review_decision(
        review_bundle_id="vrb_run_scene",
        decision=REVIEW_DECISION_ACCEPTED,
        reviewer_id="reviewer_demo",
        notes="Looks usable.",
        checklist_scores={"identity_consistency": 1.0},
        followup_actions=["pack_consumer_handoff"],
    )

    assert decision["review_bundle_id"] == "vrb_run_scene"
    assert decision["decision"] == REVIEW_DECISION_ACCEPTED
    assert decision["followup_actions"] == ["capability_consumer_handoff"]

    with pytest.raises(ValueError):
        build_artifact_review_decision(
            review_bundle_id="vrb_run_scene",
            decision="ship_it",
        )


def test_persist_visual_acceptance_review_decision_normalizes_checklist_scores(monkeypatch, tmp_path):
    manifest_path = tmp_path / "vrb_review.json"
    fake_store = _FakeArtifactsStore()
    monkeypatch.setattr(
        visual_acceptance_bundle,
        "get_visual_acceptance_artifacts_store",
        lambda: fake_store,
    )

    bundle = {
        "review_bundle_id": "vrb_review",
        "tenant_id": "default",
        "project_id": "proj_demo",
        "run_id": "run_demo",
        "scene_id": "A01",
        "source_kind": visual_acceptance_bundle.SOURCE_KIND_LAF_PATCH,
        "status": visual_acceptance_bundle.REVIEW_STATUS_PENDING,
        "checklist_template": build_review_checklist_template(
            visual_acceptance_bundle.SOURCE_KIND_LAF_PATCH
        ),
        "slots": [],
    }
    manifest_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    artifact = Artifact(
        id="vrb_review",
        workspace_id="ws_demo",
        execution_id="visual_acceptance:run_demo:A01",
        playbook_code=visual_acceptance_bundle.VISUAL_ACCEPTANCE_PLAYBOOK_CODE,
        artifact_type=visual_acceptance_bundle.ArtifactType.DATA,
        title="Visual Acceptance Bundle: A01",
        summary="bundle",
        content=bundle,
        storage_ref=str(manifest_path),
        primary_action_type=visual_acceptance_bundle.PrimaryActionType.DOWNLOAD,
        metadata={
            "kind": visual_acceptance_bundle.VISUAL_ACCEPTANCE_ARTIFACT_KIND,
            "review_bundle_id": "vrb_review",
            "manifest_path": str(manifest_path),
            "visual_acceptance_state": visual_acceptance_bundle.REVIEW_STATUS_PENDING,
        },
    )
    fake_store.create_artifact(artifact)

    decision = build_artifact_review_decision(
        review_bundle_id="vrb_review",
        decision=REVIEW_DECISION_ACCEPTED,
        checklist_scores={
            "edge_cleanliness": "1",
            "contact_zone_naturalness": 0.5,
            "identity_consistency": 9,
            "extra_field": 0.2,
        },
        followup_actions=["rebuild_contact_zone_mask", "capability_consumer_handoff"],
    )
    updated = visual_acceptance_bundle.persist_visual_acceptance_review_decision(
        artifact=artifact,
        decision_payload=decision,
        artifacts_store=fake_store,
    )

    latest = updated.content["latest_review_decision"]
    assert latest["checklist_scores"] == {
        "edge_cleanliness": 1.0,
        "contact_zone_naturalness": 0.5,
        "identity_consistency": 1.0,
    }
    assert latest["checklist_summary"] == {
        "scored_checks": 3,
        "average_score": 0.833,
    }
    assert latest["followup_actions"] == [
        "rebuild_contact_zone_mask",
        "capability_consumer_handoff",
    ]


def test_persist_visual_acceptance_review_decision_syncs_downstream_action_plan_to_run(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))

    manifest_path = tmp_path / "vrb_review_sync.json"
    fake_store = _FakeArtifactsStore()
    monkeypatch.setattr(
        visual_acceptance_bundle,
        "get_visual_acceptance_artifacts_store",
        lambda: fake_store,
    )

    run = production_run.create_run(
        tenant_id="default",
        project_id="proj_demo",
        storyboard_id="sb_demo",
        source_type="generative",
    )
    production_run.update_scene_result(
        "default",
        "proj_demo",
        run["run_id"],
        "A01",
        status="completed",
        provider_metadata={
            "visual_acceptance_state": visual_acceptance_bundle.REVIEW_STATUS_PENDING,
            "package_id": "charpkg_demo",
            "preset_id": "preset_hybrid_demo",
            "artifact_ids": ["artifact_lora_demo"],
            "binding_mode": "hybrid",
            "review_bundle_refs": [
                {
                    "artifact_id": "vrb_review_sync",
                    "review_bundle_id": "vrb_review_sync",
                    "source_kind": visual_acceptance_bundle.SOURCE_KIND_VR_RENDER,
                    "status": visual_acceptance_bundle.REVIEW_STATUS_PENDING,
                }
            ],
        },
    )

    bundle = {
        "review_bundle_id": "vrb_review_sync",
        "tenant_id": "default",
        "project_id": "proj_demo",
        "run_id": run["run_id"],
        "scene_id": "A01",
        "source_kind": visual_acceptance_bundle.SOURCE_KIND_VR_RENDER,
        "status": visual_acceptance_bundle.REVIEW_STATUS_PENDING,
        "package_id": "charpkg_demo",
        "preset_id": "preset_hybrid_demo",
        "artifact_ids": ["artifact_lora_demo"],
        "binding_mode": "hybrid",
        "checklist_template": build_review_checklist_template(
            visual_acceptance_bundle.SOURCE_KIND_VR_RENDER
        ),
        "slots": [],
    }
    manifest_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    artifact = Artifact(
        id="vrb_review_sync",
        workspace_id="ws_demo",
        execution_id=f"visual_acceptance:{run['run_id']}:A01",
        playbook_code=visual_acceptance_bundle.VISUAL_ACCEPTANCE_PLAYBOOK_CODE,
        artifact_type=visual_acceptance_bundle.ArtifactType.DATA,
        title="Visual Acceptance Bundle: A01",
        summary="bundle",
        content=bundle,
        storage_ref=str(manifest_path),
        primary_action_type=visual_acceptance_bundle.PrimaryActionType.DOWNLOAD,
        metadata={
            "kind": visual_acceptance_bundle.VISUAL_ACCEPTANCE_ARTIFACT_KIND,
            "review_bundle_id": "vrb_review_sync",
            "manifest_path": str(manifest_path),
            "visual_acceptance_state": visual_acceptance_bundle.REVIEW_STATUS_PENDING,
        },
    )
    fake_store.create_artifact(artifact)

    decision = build_artifact_review_decision(
        review_bundle_id="vrb_review_sync",
        decision=REVIEW_DECISION_ACCEPTED,
        followup_actions=[
            "capability_consumer_handoff",
            "rerender_same_preset",
            "unknown_action_should_drop",
        ],
    )
    updated = visual_acceptance_bundle.persist_visual_acceptance_review_decision(
        artifact=artifact,
        decision_payload=decision,
        artifacts_store=fake_store,
    )

    plan = updated.content["downstream_action_plan"]
    assert plan["action_ids"] == ["capability_consumer_handoff", "rerender_same_preset"]
    assert set(plan["lane_ids"]) == {"capability_consumer_handoff", "rerender"}
    assert plan["capability_consumer_handoff_ready"] is True
    assert "publish_candidate_gate" not in updated.content

    latest = updated.content["latest_review_decision"]
    assert latest["downstream_action_plan"]["capability_consumer_handoff_ready"] is True
    assert "publish_candidate_gate" not in latest
    assert latest["followup_request_refs"][0]["lane_id"] == "capability_consumer_handoff"

    synced_run = production_run.get_run("default", "proj_demo", run["run_id"])
    assert synced_run is not None
    provider_metadata = synced_run["scene_results"][0]["provider_metadata"]
    assert provider_metadata["downstream_action_plan"]["capability_consumer_handoff_ready"] is True
    assert "publish_candidate_gate" not in provider_metadata
    assert {item["lane_id"] for item in provider_metadata["followup_request_refs"]} == {
        "capability_consumer_handoff",
        "rerender",
    }
    assert provider_metadata["review_decision_ref"]["downstream_action_plan"]["action_ids"] == [
        "capability_consumer_handoff",
        "rerender_same_preset",
    ]
    review_bundle_ref = provider_metadata["review_bundle_refs"][0]
    assert (
        review_bundle_ref["downstream_action_plan"]["capability_consumer_handoff_ready"]
        is True
    )
    assert "publish_candidate_gate" not in review_bundle_ref
