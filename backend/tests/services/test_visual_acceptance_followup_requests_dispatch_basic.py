import json

import pytest

from visual_acceptance_followup_requests_test_support import (
    Artifact,
    ArtifactType,
    PrimaryActionType,
    _FakeArtifactsStore,
    _seed_followup_bundle_and_run,
    production_run,
    visual_acceptance_followup_requests,
)


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
async def test_dispatch_followup_request_handoffs_capability_consumer_handoff_to_capability_owned_consumer(
    tmp_path,
):
    store = _FakeArtifactsStore()
    run, _manifest_path = _seed_followup_bundle_and_run(
        store=store,
        tmp_path=tmp_path,
        lane_id="capability_consumer_handoff",
        consumer_kind="capability_owned_consumer",
    )

    store.create_artifact(
        Artifact(
            id="vafreq_vrb_demo_capability_consumer_handoff",
            workspace_id="ws_demo",
            execution_id=(
                f"visual_acceptance_followup:{run['run_id']}:A01:capability_consumer_handoff"
            ),
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / capability_consumer_handoff",
            summary="capability_consumer_handoff request for scene A01 (ready)",
            content={
                "request_id": "vafreq_vrb_demo_capability_consumer_handoff",
                "review_bundle_id": "vrb_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "capability_consumer_handoff",
                "consumer_kind": "capability_owned_consumer",
                "request_state": "ready",
                "action_ids": ["capability_consumer_handoff"],
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
                "lane_id": "capability_consumer_handoff",
                "consumer_kind": "capability_owned_consumer",
                "request_state": "ready",
            },
        )
    )

    result = await visual_acceptance_followup_requests.dispatch_followup_request(
        artifact=store.get_artifact("vafreq_vrb_demo_capability_consumer_handoff"),
        actor_id="operator_demo",
        notes="handoff capability consumer",
        artifacts_store=store,
    )

    assert result["dispatch_status"] == "pending_worker"
    request_artifact = result["request_artifact"]
    dispatch_artifact = result["dispatch_artifact"]
    assert request_artifact.metadata["request_state"] == "dispatched"
    assert dispatch_artifact.content["dispatch_mode"] == "consumer_handoff"
    assert dispatch_artifact.content["dispatch_result"]["execution_strategy"] == "workspace_artifact_handoff"
    assert dispatch_artifact.content["dispatch_result"]["handoff_reason"] == "capability_owned_consumer_required"
    assert dispatch_artifact.content["dispatch_result"]["package_id"] == "charpkg_demo"
    assert dispatch_artifact.content["dispatch_result"]["preset_id"] == "preset_alpha"
    assert dispatch_artifact.content["dispatch_result"]["artifact_ids"] == ["artifact_alpha"]


@pytest.mark.asyncio
async def test_dispatch_followup_request_bounds_long_artifact_ids(tmp_path):
    store = _FakeArtifactsStore()
    review_bundle_id = "vrb_" + ("character_training_eval_" * 4)

    store.create_artifact(
        Artifact(
            id=review_bundle_id,
            workspace_id="ws_demo",
            execution_id="visual_acceptance:run_demo:A01",
            playbook_code="visual_acceptance_review",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Bundle: A01",
            summary="bundle",
            content={
                "review_bundle_id": review_bundle_id,
                "workspace_id": "ws_demo",
                "run_id": "run_demo",
                "scene_id": "A01",
                "source_kind": "character_training_eval",
                "status": "accepted",
                "artifact_ids": ["artifact_alpha"],
                "package_id": "charpkg_demo",
                "binding_mode": "reference_only",
                "latest_review_decision": {"decision": "accepted"},
                "followup_request_refs": [],
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": "visual_acceptance_bundle",
                "review_bundle_id": review_bundle_id,
            },
        )
    )

    refs = visual_acceptance_followup_requests.materialize_followup_request_artifacts(
        bundle={
            "review_bundle_id": review_bundle_id,
            "workspace_id": "ws_demo",
            "run_id": "run_demo",
            "scene_id": "A01",
            "source_kind": "character_training_eval",
            "package_id": "charpkg_demo",
            "artifact_ids": ["artifact_alpha"],
            "binding_mode": "reference_only",
            "slots": [],
        },
        decision_payload={
            "decision": "accepted",
            "reviewed_at": "2026-03-27T02:00:00+00:00",
            "downstream_action_plan": {
                "lanes": [
                    {
                        "lane_id": "capability_consumer_handoff",
                        "consumer_kind": "capability_owned_consumer",
                        "dispatch_state": "ready",
                        "blocking_reason": None,
                        "action_ids": ["capability_consumer_handoff"],
                        "target_ref": {"package_id": "charpkg_demo"},
                    }
                ]
            },
        },
        artifacts_store=store,
    )

    request_artifact_id = refs[0]["artifact_id"]
    assert len(request_artifact_id) <= 64
    assert len(str(store.get_artifact(request_artifact_id).execution_id or "")) <= 64

    result = await visual_acceptance_followup_requests.dispatch_followup_request(
        artifact=store.get_artifact(request_artifact_id),
        actor_id="operator_demo",
        notes="handoff capability consumer",
        artifacts_store=store,
    )

    assert len(result["dispatch_artifact"].id) <= 64
    assert len(str(result["dispatch_artifact"].execution_id or "")) <= 64
