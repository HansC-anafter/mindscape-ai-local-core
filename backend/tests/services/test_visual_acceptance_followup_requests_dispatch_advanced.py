import json

import pytest

from visual_acceptance_followup_requests_test_support import (
    Artifact,
    ArtifactType,
    PrimaryActionType,
    _FakeArtifactsStore,
    _seed_followup_bundle_and_run,
    visual_acceptance_followup_requests,
)


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
