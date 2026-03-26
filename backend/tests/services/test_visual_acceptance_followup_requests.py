from pathlib import Path
import json
import sys

import pytest

LOCAL_CORE_ROOT = Path("/Users/shock/Projects_local/workspace/mindscape-ai-local-core")
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


def test_materialize_followup_request_artifacts_creates_and_supersedes_requests():
    store = _FakeArtifactsStore()
    bundle = {
        "review_bundle_id": "vrb_demo",
        "workspace_id": "ws_demo",
        "run_id": "run_demo",
        "scene_id": "A01",
        "source_kind": "vr_render",
        "package_id": "charpkg_demo",
        "preset_id": "preset_alpha",
        "artifact_ids": ["artifact_alpha"],
        "binding_mode": "hybrid",
        "scene_context": {
            "scene_manifest": {"scene_id": "A01", "shot_type": "medium"},
            "object_workload_snapshot": {
                "impact_region_mode": "contact_zone",
                "source_image_ref": {"storage_key": "refs/source_demo.png"},
            },
        },
        "source_metadata": {
            "prompt_id": "prompt_demo",
            "renderer": "video_renderer",
        },
        "slots": [
            {
                "slot": "final_render",
                "storage_key": "video_renderer/renders/a01.mp4",
                "preview_url": "/api/v1/capabilities/video_renderer/storage/default/video_renderer/renders/a01.mp4",
            }
        ],
    }

    first_refs = visual_acceptance_followup_requests.materialize_followup_request_artifacts(
        bundle=bundle,
        decision_payload={
            "decision": "accepted",
            "reviewed_at": "2026-03-27T01:00:00+00:00",
            "downstream_action_plan": {
                "lanes": [
                    {
                        "lane_id": "rerender",
                        "consumer_kind": "scene_rerender",
                        "dispatch_state": "ready",
                        "blocking_reason": None,
                        "action_ids": ["rerender_same_preset"],
                        "target_ref": {"run_id": "run_demo", "scene_id": "A01"},
                    },
                    {
                        "lane_id": "pack_consumer_handoff",
                        "consumer_kind": "pack_owned_consumer",
                        "dispatch_state": "ready",
                        "blocking_reason": None,
                        "action_ids": ["pack_consumer_handoff"],
                        "target_ref": {"package_id": "charpkg_demo", "preset_id": "preset_alpha"},
                    },
                ]
            },
            "pack_consumer_handoff_gate": {
                "gate_state": "ready",
                "accepted_review_count": 1,
            },
        },
        artifacts_store=store,
    )

    assert {item["lane_id"] for item in first_refs} == {"rerender", "pack_consumer_handoff"}
    publish_request = next(
        item for item in first_refs if item["lane_id"] == "pack_consumer_handoff"
    )
    assert publish_request["request_state"] == "ready"
    publish_artifact = store.get_artifact("vafreq_vrb_demo_pack_consumer_handoff")
    assert publish_artifact is not None
    assert publish_artifact.content["package_id"] == "charpkg_demo"
    assert publish_artifact.content["preset_id"] == "preset_alpha"
    assert publish_artifact.content["artifact_ids"] == ["artifact_alpha"]
    assert publish_artifact.content["target_ref"] == {
        "package_id": "charpkg_demo",
        "preset_id": "preset_alpha",
    }
    assert "character_package_capability_request" not in publish_artifact.content
    assert "character_package_promotion_gate_request" not in publish_artifact.content
    assert "character_package_publish_request_patch" not in publish_artifact.content
    rerender_artifact = store.get_artifact("vafreq_vrb_demo_rerender")
    assert rerender_artifact is not None
    assert rerender_artifact.content["dispatch_context"]["scene_context"] == {
        "scene_manifest": {"scene_id": "A01", "shot_type": "medium"},
        "object_workload_snapshot": {
            "impact_region_mode": "contact_zone",
            "source_image_ref": {"storage_key": "refs/source_demo.png"},
        },
    }
    assert rerender_artifact.content["dispatch_context"]["source_metadata"]["prompt_id"] == "prompt_demo"
    assert rerender_artifact.content["dispatch_context"]["slots"][0]["slot"] == "final_render"

    second_refs = visual_acceptance_followup_requests.materialize_followup_request_artifacts(
        bundle=bundle,
        decision_payload={
            "decision": "needs_tune",
            "reviewed_at": "2026-03-27T02:00:00+00:00",
            "downstream_action_plan": {
                "lanes": [
                    {
                        "lane_id": "laf_patch",
                        "consumer_kind": "layer_asset_forge_patch",
                        "dispatch_state": "ready",
                        "blocking_reason": None,
                        "action_ids": ["rebuild_contact_zone_mask"],
                        "target_ref": {"run_id": "run_demo", "scene_id": "A01"},
                    }
                ]
            },
            "pack_consumer_handoff_gate": {
                "gate_state": "blocked",
                "accepted_review_count": 0,
            },
        },
        artifacts_store=store,
    )

    assert [item["lane_id"] for item in second_refs] == ["laf_patch"]
    rerender_artifact = store.get_artifact("vafreq_vrb_demo_rerender")
    publish_artifact = store.get_artifact("vafreq_vrb_demo_pack_consumer_handoff")
    laf_patch_artifact = store.get_artifact("vafreq_vrb_demo_laf_patch")
    assert rerender_artifact is not None
    assert publish_artifact is not None
    assert laf_patch_artifact is not None
    assert rerender_artifact.metadata["request_state"] == "superseded"
    assert publish_artifact.metadata["request_state"] == "superseded"
    assert laf_patch_artifact.metadata["request_state"] == "ready"


def test_persist_followup_request_state_syncs_bundle_and_run(tmp_path):
    manifest_path = tmp_path / "vrb_demo.json"
    store = _FakeArtifactsStore()

    run = production_run.create_run(
        tenant_id="default",
        project_id="proj_followup_demo",
        storyboard_id="sb_followup_demo",
        source_type="generative",
    )

    followup_ref = {
        "artifact_id": "vafreq_vrb_demo_pack_consumer_handoff",
        "lane_id": "pack_consumer_handoff",
        "consumer_kind": "pack_owned_consumer",
        "request_state": "ready",
        "blocking_reason": None,
    }
    production_run.update_scene_result(
        "default",
        "proj_followup_demo",
        run["run_id"],
        "A01",
        status="completed",
        provider_metadata={
            "visual_acceptance_state": "accepted",
            "followup_request_refs": [dict(followup_ref)],
            "review_decision_ref": {
                "artifact_id": "vrb_demo",
                "decision": "accepted",
                "followup_request_refs": [dict(followup_ref)],
            },
            "review_bundle_refs": [
                {
                    "artifact_id": "vrb_demo",
                    "review_bundle_id": "vrb_demo",
                    "status": "accepted",
                    "followup_request_refs": [dict(followup_ref)],
                    "review_decision": {
                        "decision": "accepted",
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
        "status": "accepted",
        "latest_review_decision": {
            "decision": "accepted",
            "followup_request_refs": [dict(followup_ref)],
        },
        "review_decisions": [
            {
                "decision": "accepted",
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
    store.create_artifact(
        Artifact(
            id="vafreq_vrb_demo_pack_consumer_handoff",
            workspace_id="ws_demo",
            execution_id=(
                f"visual_acceptance_followup:{run['run_id']}:A01:pack_consumer_handoff"
            ),
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / pack_consumer_handoff",
            summary="pack_consumer_handoff request for scene A01 (ready)",
            content={
                "request_id": "vafreq_vrb_demo_pack_consumer_handoff",
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "pack_consumer_handoff",
                "consumer_kind": "pack_owned_consumer",
                "request_state": "ready",
                "blocking_reason": None,
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": visual_acceptance_followup_requests.VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "pack_consumer_handoff",
                "consumer_kind": "pack_owned_consumer",
                "request_state": "ready",
            },
        )
    )

    updated = visual_acceptance_followup_requests.persist_followup_request_state(
        artifact=store.get_artifact("vafreq_vrb_demo_pack_consumer_handoff"),
        request_state="completed",
        actor_id="publisher_demo",
        notes="Handed off to pack-owned consumer.",
        execution_ref={"publish_job_id": "pub_demo_001"},
        artifacts_store=store,
    )

    assert updated.metadata["request_state"] == "completed"
    assert updated.content["last_transition"]["actor_id"] == "publisher_demo"
    assert updated.content["request_events"][-1]["execution_ref"] == {
        "publish_job_id": "pub_demo_001"
    }

    updated_bundle = store.get_artifact("vrb_demo")
    assert updated_bundle is not None
    assert updated_bundle.content["followup_request_refs"][0]["request_state"] == "completed"
    assert updated_bundle.content["latest_review_decision"]["followup_request_refs"][0][
        "last_transition"
    ]["notes"] == "Handed off to pack-owned consumer."
    assert updated_bundle.metadata["followup_request_state_counts"] == {"completed": 1}

    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted_manifest["review_decisions"][-1]["followup_request_refs"][0][
        "request_state"
    ] == "completed"

    synced_run = production_run.get_run("default", "proj_followup_demo", run["run_id"])
    assert synced_run is not None
    provider_metadata = synced_run["scene_results"][0]["provider_metadata"]
    assert provider_metadata["followup_request_refs"][0]["request_state"] == "completed"
    assert provider_metadata["review_decision_ref"]["followup_request_refs"][0][
        "last_transition"
    ]["actor_id"] == "publisher_demo"
    assert provider_metadata["review_bundle_refs"][0]["followup_request_refs"][0][
        "last_transition"
    ]["execution_ref"]["publish_job_id"] == "pub_demo_001"


@pytest.mark.asyncio
async def test_dispatch_followup_request_executes_rerender_and_completes_request(
    monkeypatch,
    tmp_path,
):
    store = _FakeArtifactsStore()
    run, manifest_path = _seed_followup_bundle_and_run(
        store=store,
        tmp_path=tmp_path,
        lane_id="rerender",
        consumer_kind="scene_rerender",
    )

    store.create_artifact(
        Artifact(
            id="vafreq_vrb_demo_rerender",
            workspace_id="ws_demo",
            execution_id=f"visual_acceptance_followup:{run['run_id']}:A01:rerender",
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / rerender",
            summary="rerender request for scene A01 (ready)",
            content={
                "request_id": "vafreq_vrb_demo_rerender",
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "rerender",
                "consumer_kind": "scene_rerender",
                "request_state": "ready",
                "action_ids": ["rerender_same_preset"],
                "target_ref": {"project_id": "proj_followup_demo", "scene_id": "A01"},
                "dispatch_context": {
                    "scene_context": {
                        "scene_payload": {
                            "scene_id": "A01",
                            "scene_manifest": {"shot": "close_up"},
                            "object_workload_snapshot": {
                                "source_scene_id": "SC_SOURCE_01",
                                "impact_region_mode": "contact_zone",
                                "quality_gate_state": "auto_approved",
                            },
                        },
                        "scene_manifest": {"shot": "close_up"},
                        "object_workload_snapshot": {
                            "source_scene_id": "SC_SOURCE_01",
                            "impact_region_mode": "contact_zone",
                            "quality_gate_state": "auto_approved",
                        },
                    },
                    "source_metadata": {
                        "source_type": "generative",
                        "render_profile": {"profile_id": "vr_preview_local"},
                        "project_id": "proj_followup_demo",
                    },
                    "slots": [],
                },
                "blocking_reason": None,
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": visual_acceptance_followup_requests.VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "rerender",
                "consumer_kind": "scene_rerender",
                "request_state": "ready",
            },
        )
    )

    async def _fake_execute_storyboard(*, project_id, storyboard, source_type, tenant_id):
        assert project_id == "proj_followup_demo"
        assert source_type == "generative"
        assert tenant_id == "default"
        assert storyboard["workspace_id"] == "ws_demo"
        assert storyboard["render_profile"] == {"profile_id": "vr_preview_local"}
        assert storyboard["scenes"][0]["scene_id"] == "A01"
        assert storyboard["scenes"][0]["scene_manifest"] == {"shot": "close_up"}
        return {
            "success": True,
            "run_id": "run_rerender_demo",
            "status": "preview_done",
            "timeline_items_synced": 1,
        }

    monkeypatch.setattr(
        "backend.app.capabilities.multi_media_studio.tools.storyboard_execution.execute_storyboard",
        _fake_execute_storyboard,
    )
    monkeypatch.setattr(
        "app.capabilities.multi_media_studio.tools.storyboard_execution.execute_storyboard",
        _fake_execute_storyboard,
        raising=False,
    )

    result = await visual_acceptance_followup_requests.dispatch_followup_request(
        artifact=store.get_artifact("vafreq_vrb_demo_rerender"),
        actor_id="operator_demo",
        notes="rerender same preset",
        artifacts_store=store,
    )

    assert result["dispatch_status"] == "completed"
    request_artifact = result["request_artifact"]
    dispatch_artifact = result["dispatch_artifact"]
    assert request_artifact.metadata["request_state"] == "completed"
    assert request_artifact.content["last_transition"]["execution_ref"]["run_id"] == "run_rerender_demo"
    assert dispatch_artifact.metadata["kind"] == "visual_acceptance_followup_dispatch"
    assert dispatch_artifact.metadata["dispatch_status"] == "completed"
    assert dispatch_artifact.content["storyboard"]["scenes"][0]["scene_id"] == "A01"
    assert dispatch_artifact.content["dispatch_result"]["status"] == "preview_done"

    updated_bundle = store.get_artifact("vrb_demo")
    assert updated_bundle is not None
    assert updated_bundle.content["followup_request_refs"][0]["request_state"] == "completed"

    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted_manifest["followup_request_refs"][0]["request_state"] == "completed"

    synced_run = production_run.get_run("default", "proj_followup_demo", run["run_id"])
    assert synced_run is not None
    provider_metadata = synced_run["scene_results"][0]["provider_metadata"]
    assert provider_metadata["followup_request_refs"][0]["request_state"] == "completed"
    assert provider_metadata["followup_request_refs"][0]["last_transition"]["execution_ref"][
        "artifact_id"
    ] == dispatch_artifact.id


@pytest.mark.asyncio
async def test_dispatch_followup_request_handoffs_pack_consumer_handoff_to_pack_owned_consumer(
    tmp_path,
):
    store = _FakeArtifactsStore()
    run, _manifest_path = _seed_followup_bundle_and_run(
        store=store,
        tmp_path=tmp_path,
        lane_id="pack_consumer_handoff",
        consumer_kind="pack_owned_consumer",
    )

    store.create_artifact(
        Artifact(
            id="vafreq_vrb_demo_pack_consumer_handoff",
            workspace_id="ws_demo",
            execution_id=(
                f"visual_acceptance_followup:{run['run_id']}:A01:pack_consumer_handoff"
            ),
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / pack_consumer_handoff",
            summary="pack_consumer_handoff request for scene A01 (ready)",
            content={
                "request_id": "vafreq_vrb_demo_pack_consumer_handoff",
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "pack_consumer_handoff",
                "consumer_kind": "pack_owned_consumer",
                "request_state": "ready",
                "action_ids": ["pack_consumer_handoff"],
                "target_ref": {"package_id": "charpkg_demo", "preset_id": "preset_alpha"},
                "package_id": "charpkg_demo",
                "preset_id": "preset_alpha",
                "artifact_ids": ["artifact_alpha"],
                "binding_mode": "hybrid",
                "blocking_reason": None,
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": visual_acceptance_followup_requests.VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "pack_consumer_handoff",
                "consumer_kind": "pack_owned_consumer",
                "request_state": "ready",
            },
        )
    )

    result = await visual_acceptance_followup_requests.dispatch_followup_request(
        artifact=store.get_artifact("vafreq_vrb_demo_pack_consumer_handoff"),
        actor_id="operator_demo",
        notes="handoff pack consumer",
        artifacts_store=store,
    )

    assert result["dispatch_status"] == "pending_worker"
    request_artifact = result["request_artifact"]
    dispatch_artifact = result["dispatch_artifact"]
    assert request_artifact.metadata["request_state"] == "dispatched"
    assert dispatch_artifact.content["dispatch_mode"] == "consumer_handoff"
    assert dispatch_artifact.content["dispatch_result"]["execution_strategy"] == "workspace_artifact_handoff"
    assert dispatch_artifact.content["dispatch_result"]["handoff_reason"] == "pack_owned_consumer_required"
    assert dispatch_artifact.content["dispatch_result"]["package_id"] == "charpkg_demo"
    assert dispatch_artifact.content["dispatch_result"]["preset_id"] == "preset_alpha"
    assert dispatch_artifact.content["dispatch_result"]["artifact_ids"] == ["artifact_alpha"]


@pytest.mark.asyncio
async def test_dispatch_followup_request_executes_laf_patch_and_completes_request(
    monkeypatch,
    tmp_path,
):
    store = _FakeArtifactsStore()
    run, manifest_path = _seed_followup_bundle_and_run(
        store=store,
        tmp_path=tmp_path,
        lane_id="laf_patch",
        consumer_kind="layer_asset_forge_patch",
    )

    store.create_artifact(
        Artifact(
            id="vafreq_vrb_demo_laf_patch",
            workspace_id="ws_demo",
            execution_id=f"visual_acceptance_followup:{run['run_id']}:A01:laf_patch",
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / laf_patch",
            summary="laf patch request for scene A01 (ready)",
            content={
                "request_id": "vafreq_vrb_demo_laf_patch",
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "laf_patch",
                "consumer_kind": "layer_asset_forge_patch",
                "request_state": "ready",
                "action_ids": ["rebuild_contact_zone_mask"],
                "target_ref": {"project_id": "proj_followup_demo", "scene_id": "A01"},
                "dispatch_context": {
                    "scene_context": {
                        "scene_payload": {
                            "scene_id": "A01",
                            "scene_manifest": {"shot": "close_up"},
                            "direction_ir": {
                                "object_targets": [
                                    {
                                        "object_id": "held_prop",
                                        "object_instance_id": "obj_held_prop",
                                        "label": "Held Prop",
                                        "source_reference_fingerprint": "ref_scene_a",
                                    }
                                ]
                            },
                            "object_assets": [
                                {
                                    "object_target_id": "held_prop",
                                    "object_instance_id": "obj_held_prop",
                                    "source_reference_fingerprint": "ref_scene_a",
                                }
                            ],
                            "object_workload_snapshot": {
                                "source_scene_id": "SC_SOURCE_01",
                                "source_image_ref": {
                                    "storage_key": "refs/source_scene.png"
                                },
                                "selection_mode": "named",
                                "impact_region_mode": "contact_zone",
                                "quality_gate_state": "auto_approved",
                                "usage_bindings": [
                                    {
                                        "scene_id": "A01",
                                        "purpose": "prop",
                                        "placement_policy": "inherit",
                                    }
                                ],
                                "affected_object_instance_ids": [
                                    "obj_held_prop",
                                    "obj_person_main",
                                ],
                            },
                        }
                    },
                    "source_metadata": {
                        "project_id": "proj_followup_demo",
                        "source_type": "generative",
                        "render_profile": {"profile_id": "vr_preview_local"},
                    },
                    "slots": [],
                },
                "blocking_reason": None,
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": visual_acceptance_followup_requests.VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "laf_patch",
                "consumer_kind": "layer_asset_forge_patch",
                "request_state": "ready",
            },
        )
    )

    async def _fake_extract_object_assets(*, request, tenant_id):
        assert tenant_id == "default"
        assert request.image_ref == {"storage_key": "refs/source_scene.png"}
        assert request.selection_mode == "targets"
        assert request.source_scene_ref == {"scene_id": "SC_SOURCE_01"}
        assert request.object_targets[0]["object_target_id"] == "held_prop"
        assert request.object_targets[0]["usage_bindings"][0]["scene_id"] == "A01"
        return {
            "job": {
                "job_id": "laf_followup_demo",
                "status": "completed",
                "storyboard_scene_patch": {
                    "object_assets": [
                        {
                            "object_target_id": "held_prop",
                            "object_instance_id": "obj_held_prop",
                            "asset_ref": {
                                "storage_key": "layer_asset_forge/jobs/laf_followup_demo/exports/layers/held_prop.png"
                            },
                        }
                    ],
                    "object_workload_snapshot": {
                        "source_scene_id": "SC_SOURCE_01",
                        "source_image_ref": {
                            "storage_key": "refs/source_scene.png"
                        },
                        "impact_region_mode": "contact_zone",
                        "quality_gate_state": "auto_approved",
                    },
                },
            }
        }

    async def _fake_apply_storyboard_scene_patch(
        *, storyboard, scene_id, storyboard_scene_patch, tenant_id="default"
    ):
        assert tenant_id == "default"
        assert scene_id == "A01"
        assert storyboard["scenes"][0]["scene_id"] == "A01"
        assert storyboard_scene_patch["object_assets"][0]["object_target_id"] == "held_prop"
        patched_storyboard = dict(storyboard)
        patched_scene = dict(patched_storyboard["scenes"][0])
        patched_scene["object_assets"] = list(storyboard_scene_patch["object_assets"])
        patched_scene["object_workload_snapshot"] = dict(
            storyboard_scene_patch["object_workload_snapshot"]
        )
        patched_storyboard["scenes"] = [patched_scene]
        return {
            "success": True,
            "storyboard": patched_storyboard,
            "patched_scene_id": scene_id,
        }

    async def _fake_execute_storyboard(*, project_id, storyboard, source_type, tenant_id):
        assert project_id == "proj_followup_demo"
        assert source_type == "generative"
        assert tenant_id == "default"
        assert storyboard["scenes"][0]["object_assets"][0]["object_target_id"] == "held_prop"
        return {
            "success": True,
            "run_id": "run_laf_patch_demo",
            "status": "preview_done",
            "timeline_items_synced": 1,
        }

    monkeypatch.setattr(
        "backend.app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints.extract_object_assets",
        _fake_extract_object_assets,
    )
    monkeypatch.setattr(
        "app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints.extract_object_assets",
        _fake_extract_object_assets,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.capabilities.multi_media_studio.tools.storyboard_patch.apply_storyboard_scene_patch",
        _fake_apply_storyboard_scene_patch,
    )
    monkeypatch.setattr(
        "app.capabilities.multi_media_studio.tools.storyboard_patch.apply_storyboard_scene_patch",
        _fake_apply_storyboard_scene_patch,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.app.capabilities.multi_media_studio.tools.storyboard_execution.execute_storyboard",
        _fake_execute_storyboard,
    )
    monkeypatch.setattr(
        "app.capabilities.multi_media_studio.tools.storyboard_execution.execute_storyboard",
        _fake_execute_storyboard,
        raising=False,
    )

    result = await visual_acceptance_followup_requests.dispatch_followup_request(
        artifact=store.get_artifact("vafreq_vrb_demo_laf_patch"),
        actor_id="operator_demo",
        notes="rebuild contact zone mask",
        artifacts_store=store,
    )

    assert result["dispatch_status"] == "completed"
    request_artifact = result["request_artifact"]
    dispatch_artifact = result["dispatch_artifact"]
    assert request_artifact.metadata["request_state"] == "completed"
    assert request_artifact.content["last_transition"]["execution_ref"]["laf_extract_job_id"] == (
        "laf_followup_demo"
    )
    assert dispatch_artifact.metadata["dispatch_status"] == "completed"
    assert dispatch_artifact.content["dispatch_mode"] == "extract_patch_execute_storyboard"
    assert dispatch_artifact.content["laf_extract_request"]["image_ref"] == {
        "storage_key": "refs/source_scene.png"
    }
    assert dispatch_artifact.content["storyboard_scene_patch"]["object_assets"][0][
        "object_target_id"
    ] == "held_prop"
    assert dispatch_artifact.content["dispatch_result"]["run_id"] == "run_laf_patch_demo"

    updated_bundle = store.get_artifact("vrb_demo")
    assert updated_bundle is not None
    assert updated_bundle.content["followup_request_refs"][0]["request_state"] == "completed"

    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted_manifest["followup_request_refs"][0]["request_state"] == "completed"


@pytest.mark.asyncio
async def test_dispatch_followup_request_queues_local_scene_review_artifact(tmp_path):
    store = _FakeArtifactsStore()
    run, manifest_path = _seed_followup_bundle_and_run(
        store=store,
        tmp_path=tmp_path,
        lane_id="local_scene_review",
        consumer_kind="manual_scene_review",
        review_status="manual_required",
        review_decision="manual_required",
        review_notes="Need local scene review for contact-zone cleanup.",
    )

    store.create_artifact(
        Artifact(
            id="vafreq_vrb_demo_local_scene_review",
            workspace_id="ws_demo",
            execution_id=(
                f"visual_acceptance_followup:{run['run_id']}:A01:local_scene_review"
            ),
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / local_scene_review",
            summary="local scene review request for scene A01 (ready)",
            content={
                "request_id": "vafreq_vrb_demo_local_scene_review",
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "local_scene_review",
                "consumer_kind": "manual_scene_review",
                "request_state": "ready",
                "action_ids": ["escalate_local_scene_review"],
                "target_ref": {"project_id": "proj_followup_demo", "scene_id": "A01"},
                "dispatch_context": {
                    "scene_context": {
                        "scene_payload": {
                            "scene_id": "A01",
                            "scene_manifest": {"shot": "close_up"},
                            "object_workload_snapshot": {
                                "source_scene_id": "SC_SOURCE_01",
                                "source_image_ref": {
                                    "storage_key": "refs/source_scene.png"
                                },
                                "impact_region_mode": "local_scene",
                                "quality_gate_state": "escalate_local_scene",
                            },
                        }
                    },
                    "source_metadata": {
                        "project_id": "proj_followup_demo",
                        "source_type": "generative",
                    },
                    "slots": [
                        {
                            "slot": "final_render",
                            "storage_key": "video_renderer/renders/a01.mp4",
                            "preview_url": "/api/v1/capabilities/video_renderer/storage/default/video_renderer/renders/a01.mp4",
                        }
                    ],
                },
                "blocking_reason": None,
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": visual_acceptance_followup_requests.VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "local_scene_review",
                "consumer_kind": "manual_scene_review",
                "request_state": "ready",
            },
        )
    )

    result = await visual_acceptance_followup_requests.dispatch_followup_request(
        artifact=store.get_artifact("vafreq_vrb_demo_local_scene_review"),
        actor_id="operator_demo",
        notes="queue local review lane",
        artifacts_store=store,
    )

    assert result["dispatch_status"] == "queued"
    request_artifact = result["request_artifact"]
    dispatch_artifact = result["dispatch_artifact"]
    consumer_artifact = result["consumer_artifact"]
    assert request_artifact.metadata["request_state"] == "dispatched"
    assert dispatch_artifact.metadata["dispatch_status"] == "queued"
    assert dispatch_artifact.content["dispatch_mode"] == "manual_scene_review_queue"
    assert dispatch_artifact.content["dispatch_result"]["mode"] == "manual_scene_review_queue"
    assert dispatch_artifact.content["dispatch_result"]["scene_review_artifact_id"] == (
        consumer_artifact.id
    )
    assert consumer_artifact.metadata["kind"] == (
        visual_acceptance_followup_requests.VISUAL_ACCEPTANCE_SCENE_REVIEW_ARTIFACT_KIND
    )
    assert consumer_artifact.content["review_decision"]["decision"] == "manual_required"
    assert consumer_artifact.content["quality_gate"]["quality_gate_state"] == (
        "escalate_local_scene"
    )
    assert consumer_artifact.content["slots"][0]["slot"] == "final_render"

    updated_bundle = store.get_artifact("vrb_demo")
    assert updated_bundle is not None
    assert updated_bundle.content["followup_request_refs"][0]["request_state"] == "dispatched"

    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted_manifest["followup_request_refs"][0]["request_state"] == "dispatched"
