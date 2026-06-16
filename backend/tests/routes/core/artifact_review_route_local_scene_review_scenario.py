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

async def run_local_scene_review_scenario(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))

    fake_artifacts = _FakeArtifactsStore()
    fake_store = SimpleNamespace(
        artifacts=fake_artifacts,
        get_workspace=lambda workspace_id: {"id": workspace_id},
    )
    monkeypatch.setattr(mindscape_store, "MindscapeStore", lambda *args, **kwargs: fake_store)

    sys.modules.pop("backend.app.routes.core.artifacts", None)
    artifacts_routes = importlib.import_module("backend.app.routes.core.artifacts")

    run = production_run.create_run(
        tenant_id="default",
        project_id="proj_demo",
        storyboard_id="sb_demo",
        source_type="generative",
    )
    manifest_path = tmp_path / "vrb_dispatch_local_scene_demo.json"
    manifest_path.write_text(
        json.dumps(
            {
                "review_bundle_id": "vrb_dispatch_local_scene_demo",
                "workspace_id": "ws_demo",
                "tenant_id": "default",
                "project_id": "proj_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "status": "manual_required",
                "checklist_template": [
                    {"check_id": "contact_zone_naturalness", "label": "Contact Zone Naturalness"}
                ],
                "latest_review_decision": {
                    "decision": "manual_required",
                    "notes": "Need local scene review.",
                    "checklist_scores": {"contact_zone_naturalness": 0.1},
                    "followup_request_refs": [
                        {
                            "artifact_id": "vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
                            "lane_id": "local_scene_review",
                            "consumer_kind": "manual_scene_review",
                            "request_state": "ready",
                        }
                    ],
                },
                "review_decisions": [
                    {
                        "decision": "manual_required",
                        "notes": "Need local scene review.",
                        "checklist_scores": {"contact_zone_naturalness": 0.1},
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
                                "lane_id": "local_scene_review",
                                "consumer_kind": "manual_scene_review",
                                "request_state": "ready",
                            }
                        ],
                    }
                ],
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
                        "lane_id": "local_scene_review",
                        "consumer_kind": "manual_scene_review",
                        "request_state": "ready",
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
        status="blocked",
        provider_metadata={
            "followup_request_refs": [
                {
                    "artifact_id": "vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
                    "lane_id": "local_scene_review",
                    "consumer_kind": "manual_scene_review",
                    "request_state": "ready",
                }
            ],
            "review_decision_ref": {
                "artifact_id": "vrb_dispatch_local_scene_demo",
                "decision": "manual_required",
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
                        "lane_id": "local_scene_review",
                        "consumer_kind": "manual_scene_review",
                        "request_state": "ready",
                    }
                ],
            },
            "review_bundle_refs": [
                {
                    "artifact_id": "vrb_dispatch_local_scene_demo",
                    "review_bundle_id": "vrb_dispatch_local_scene_demo",
                    "status": "manual_required",
                    "followup_request_refs": [
                        {
                            "artifact_id": "vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
                            "lane_id": "local_scene_review",
                            "consumer_kind": "manual_scene_review",
                            "request_state": "ready",
                        }
                    ],
                    "review_decision": {
                        "decision": "manual_required",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
                                "lane_id": "local_scene_review",
                                "consumer_kind": "manual_scene_review",
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
            id="vrb_dispatch_local_scene_demo",
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
                "review_bundle_id": "vrb_dispatch_local_scene_demo",
                "manifest_path": str(manifest_path),
            },
        )
    )
    fake_artifacts.create_artifact(
        Artifact(
            id="vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
            workspace_id="ws_demo",
            execution_id=(
                f"visual_acceptance_followup:{run['run_id']}:A01:local_scene_review"
            ),
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / local_scene_review",
            summary="local scene review request",
            content={
                "request_id": "vafreq_vrb_dispatch_local_scene_demo_local_scene_review",
                "review_bundle_id": "vrb_dispatch_local_scene_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "local_scene_review",
                "consumer_kind": "manual_scene_review",
                "request_state": "ready",
                "source_kind": "laf_patch",
                "source_decision": "manual_required",
                "reviewed_at": "2026-03-27T03:00:00+00:00",
                "action_ids": ["escalate_local_scene_review"],
                "target_ref": {"project_id": "proj_demo", "scene_id": "A01"},
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
                                "affected_object_instance_ids": [
                                    "obj_held_prop",
                                    "obj_person_main",
                                ],
                            },
                        }
                    },
                    "source_metadata": {
                        "project_id": "proj_demo",
                        "source_type": "generative",
                    },
                    "slots": [
                        {
                            "slot": "final_layer",
                            "storage_key": "layer_asset_forge/jobs/demo/exports/layers/held_prop.png",
                        }
                    ],
                },
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": "visual_acceptance_followup_request",
                "review_bundle_id": "vrb_dispatch_local_scene_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "local_scene_review",
                "consumer_kind": "manual_scene_review",
                "request_state": "ready",
            },
        )
    )

    app = FastAPI()
    app.include_router(artifacts_routes.router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/workspaces/ws_demo/artifacts/vafreq_vrb_dispatch_local_scene_demo_local_scene_review/dispatch-followup",
            json={
                "actor_id": "operator_demo",
                "notes": "Queue local scene review",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["dispatch_status"] == "queued"
    assert payload["artifact"]["metadata"]["request_state"] == "dispatched"
    assert payload["dispatch_artifact"]["metadata"]["kind"] == "visual_acceptance_followup_dispatch"
    assert payload["dispatch_artifact"]["metadata"]["dispatch_status"] == "queued"
    assert payload["dispatch_result"]["mode"] == "manual_scene_review_queue"
    assert payload["consumer_artifact"]["metadata"]["kind"] == "visual_acceptance_scene_review_request"
    assert payload["consumer_artifact"]["content"]["review_decision"]["decision"] == "manual_required"
    assert payload["consumer_artifact"]["content"]["quality_gate"]["quality_gate_state"] == (
        "escalate_local_scene"
    )

    updated_request_artifact = fake_artifacts.get_artifact(
        "vafreq_vrb_dispatch_local_scene_demo_local_scene_review"
    )
    assert updated_request_artifact is not None
    assert updated_request_artifact.metadata["request_state"] == "dispatched"

    scene_review_artifact = fake_artifacts.get_artifact(
        payload["consumer_artifact"]["id"]
    )
    assert scene_review_artifact is not None
    assert scene_review_artifact.metadata["kind"] == "visual_acceptance_scene_review_request"
