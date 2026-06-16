from artifact_review_route_test_common import (
    Artifact,
    ArtifactType,
    FastAPI,
    PrimaryActionType,
    SimpleNamespace,
    _FakeArtifactsStore,
    httpx,
    importlib,
    json,
    mindscape_store,
    production_run,
    sys,
)

async def run_laf_patch_dispatch_scenario(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))

    fake_artifacts = _FakeArtifactsStore()
    fake_store = SimpleNamespace(
        artifacts=fake_artifacts,
        get_workspace=lambda workspace_id: {"id": workspace_id},
    )
    monkeypatch.setattr(mindscape_store, "MindscapeStore", lambda *args, **kwargs: fake_store)

    async def _fake_extract_object_assets(*, request, tenant_id):
        assert tenant_id == "default"
        assert request.image_ref == {"storage_key": "refs/source_scene.png"}
        assert request.selection_mode == "targets"
        assert request.object_targets[0]["object_target_id"] == "held_prop"
        return {
            "job": {
                "job_id": "laf_followup_route_demo",
                "status": "completed",
                "storyboard_scene_patch": {
                    "object_assets": [
                        {
                            "object_target_id": "held_prop",
                            "object_instance_id": "obj_held_prop",
                            "asset_ref": {
                                "storage_key": "layer_asset_forge/jobs/laf_followup_route_demo/exports/layers/held_prop.png"
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
        assert project_id == "proj_demo"
        assert source_type == "generative"
        assert tenant_id == "default"
        assert storyboard["scenes"][0]["object_assets"][0]["object_target_id"] == "held_prop"
        return {
            "success": True,
            "run_id": "run_laf_patch_route_demo",
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

    sys.modules.pop("backend.app.routes.core.artifacts", None)
    artifacts_routes = importlib.import_module("backend.app.routes.core.artifacts")

    run = production_run.create_run(
        tenant_id="default",
        project_id="proj_demo",
        storyboard_id="sb_demo",
        source_type="generative",
    )
    manifest_path = tmp_path / "vrb_dispatch_laf_demo.json"
    manifest_path.write_text(
        json.dumps(
            {
                "review_bundle_id": "vrb_dispatch_laf_demo",
                "workspace_id": "ws_demo",
                "tenant_id": "default",
                "project_id": "proj_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "status": "needs_tune",
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_laf_demo_laf_patch",
                        "lane_id": "laf_patch",
                        "consumer_kind": "layer_asset_forge_patch",
                        "request_state": "ready",
                    }
                ],
                "latest_review_decision": {
                    "decision": "needs_tune",
                    "followup_request_refs": [
                        {
                            "artifact_id": "vafreq_vrb_dispatch_laf_demo_laf_patch",
                            "lane_id": "laf_patch",
                            "consumer_kind": "layer_asset_forge_patch",
                            "request_state": "ready",
                        }
                    ],
                },
                "review_decisions": [
                    {
                        "decision": "needs_tune",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_laf_demo_laf_patch",
                                "lane_id": "laf_patch",
                                "consumer_kind": "layer_asset_forge_patch",
                                "request_state": "ready",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    production_run.update_scene_result(
        "default",
        "proj_demo",
        run["run_id"],
        "A01",
        renderer="video_renderer",
        status="completed",
        provider_metadata={
            "followup_request_refs": [
                {
                    "artifact_id": "vafreq_vrb_dispatch_laf_demo_laf_patch",
                    "lane_id": "laf_patch",
                    "consumer_kind": "layer_asset_forge_patch",
                    "request_state": "ready",
                }
            ],
            "review_decision_ref": {
                "artifact_id": "vrb_dispatch_laf_demo",
                "decision": "needs_tune",
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_laf_demo_laf_patch",
                        "lane_id": "laf_patch",
                        "consumer_kind": "layer_asset_forge_patch",
                        "request_state": "ready",
                    }
                ],
            },
            "review_bundle_refs": [
                {
                    "artifact_id": "vrb_dispatch_laf_demo",
                    "review_bundle_id": "vrb_dispatch_laf_demo",
                    "status": "needs_tune",
                    "followup_request_refs": [
                        {
                            "artifact_id": "vafreq_vrb_dispatch_laf_demo_laf_patch",
                            "lane_id": "laf_patch",
                            "consumer_kind": "layer_asset_forge_patch",
                            "request_state": "ready",
                        }
                    ],
                    "review_decision": {
                        "decision": "needs_tune",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_laf_demo_laf_patch",
                                "lane_id": "laf_patch",
                                "consumer_kind": "layer_asset_forge_patch",
                                "request_state": "ready",
                            }
                        ],
                    },
                }
            ],
        },
    )

    fake_artifacts.create_artifact(
        Artifact(
            id="vrb_dispatch_laf_demo",
            workspace_id="ws_demo",
            execution_id="visual_acceptance:run:A01",
            playbook_code="visual_acceptance_review",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Bundle: A01",
            summary="bundle",
            content=json.loads(manifest_path.read_text(encoding="utf-8")),
            storage_ref=str(manifest_path),
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": "visual_acceptance_bundle",
                "review_bundle_id": "vrb_dispatch_laf_demo",
                "manifest_path": str(manifest_path),
            },
        )
    )
    fake_artifacts.create_artifact(
        Artifact(
            id="vafreq_vrb_dispatch_laf_demo_laf_patch",
            workspace_id="ws_demo",
            execution_id=f"visual_acceptance_followup:{run['run_id']}:A01:laf_patch",
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / laf_patch",
            summary="laf patch request",
            content={
                "request_id": "vafreq_vrb_dispatch_laf_demo_laf_patch",
                "review_bundle_id": "vrb_dispatch_laf_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "laf_patch",
                "consumer_kind": "layer_asset_forge_patch",
                "request_state": "ready",
                "action_ids": ["rebuild_contact_zone_mask"],
                "target_ref": {"project_id": "proj_demo", "scene_id": "A01"},
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
                        "source_type": "generative",
                        "render_profile": {"profile_id": "vr_preview_local"},
                        "project_id": "proj_demo",
                    },
                    "slots": [],
                },
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": "visual_acceptance_followup_request",
                "review_bundle_id": "vrb_dispatch_laf_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "laf_patch",
                "consumer_kind": "layer_asset_forge_patch",
                "request_state": "ready",
            },
        )
    )

    app = FastAPI()
    app.include_router(artifacts_routes.router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/workspaces/ws_demo/artifacts/vafreq_vrb_dispatch_laf_demo_laf_patch/dispatch-followup",
            json={
                "actor_id": "operator_demo",
                "notes": "Dispatch laf patch",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["dispatch_status"] == "completed"
    assert payload["artifact"]["metadata"]["request_state"] == "completed"
    assert payload["dispatch_artifact"]["metadata"]["kind"] == "visual_acceptance_followup_dispatch"
    assert payload["dispatch_artifact"]["metadata"]["dispatch_status"] == "completed"
    assert payload["dispatch_result"]["run_id"] == "run_laf_patch_route_demo"
    assert payload["dispatch_result"]["laf_extract_job_id"] == "laf_followup_route_demo"

    updated_request_artifact = fake_artifacts.get_artifact("vafreq_vrb_dispatch_laf_demo_laf_patch")
    assert updated_request_artifact is not None
    assert updated_request_artifact.metadata["request_state"] == "completed"

    updated_bundle = fake_artifacts.get_artifact("vrb_dispatch_laf_demo")
    assert updated_bundle is not None
    assert updated_bundle.content["followup_request_refs"][0]["request_state"] == "completed"
