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

async def run_capability_handoff_scenario(
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
    manifest_path = tmp_path / "vrb_dispatch_publish_demo.json"
    manifest_path.write_text(
        json.dumps(
            {
                "review_bundle_id": "vrb_dispatch_publish_demo",
                "workspace_id": "ws_demo",
                "tenant_id": "default",
                "project_id": "proj_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "status": "accepted",
                "latest_review_decision": {
                    "decision": "accepted",
                    "followup_request_refs": [
                        {
                            "artifact_id": "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
                            "lane_id": "capability_consumer_handoff",
                            "consumer_kind": "capability_owned_consumer",
                            "request_state": "ready",
                        }
                    ],
                },
                "review_decisions": [
                    {
                        "decision": "accepted",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
                                "lane_id": "capability_consumer_handoff",
                                "consumer_kind": "capability_owned_consumer",
                                "request_state": "ready",
                            }
                        ],
                    }
                ],
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
                        "lane_id": "capability_consumer_handoff",
                        "consumer_kind": "capability_owned_consumer",
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
        status="completed",
        provider_metadata={
            "followup_request_refs": [
                {
                    "artifact_id": "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
                    "lane_id": "capability_consumer_handoff",
                    "consumer_kind": "capability_owned_consumer",
                    "request_state": "ready",
                }
            ],
            "review_decision_ref": {
                "artifact_id": "vrb_dispatch_publish_demo",
                "decision": "accepted",
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
                        "lane_id": "capability_consumer_handoff",
                        "consumer_kind": "capability_owned_consumer",
                        "request_state": "ready",
                    }
                ],
            },
            "review_bundle_refs": [
                {
                    "artifact_id": "vrb_dispatch_publish_demo",
                    "review_bundle_id": "vrb_dispatch_publish_demo",
                    "status": "accepted",
                    "followup_request_refs": [
                        {
                            "artifact_id": "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
                            "lane_id": "capability_consumer_handoff",
                            "consumer_kind": "capability_owned_consumer",
                            "request_state": "ready",
                        }
                    ],
                    "review_decision": {
                        "decision": "accepted",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
                                "lane_id": "capability_consumer_handoff",
                                "consumer_kind": "capability_owned_consumer",
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
            id="vrb_dispatch_publish_demo",
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
                "review_bundle_id": "vrb_dispatch_publish_demo",
                "manifest_path": str(manifest_path),
            },
        )
    )
    fake_artifacts.create_artifact(
        Artifact(
            id="vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
            workspace_id="ws_demo",
            execution_id=(
                f"visual_acceptance_followup:{run['run_id']}:A01:capability_consumer_handoff"
            ),
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / capability_consumer_handoff",
            summary="publish candidate request",
            content={
                "request_id": "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff",
                "review_bundle_id": "vrb_dispatch_publish_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "capability_consumer_handoff",
                "consumer_kind": "capability_owned_consumer",
                "request_state": "ready",
                "package_id": "charpkg_demo",
                "preset_id": "preset_alpha",
                "artifact_ids": ["artifact_alpha"],
                "binding_mode": "hybrid",
                "action_ids": ["capability_consumer_handoff"],
                "target_ref": {
                    "package_id": "charpkg_demo",
                    "preset_id": "preset_alpha",
                    "candidate_id": "cc_demo",
                    "default_display_name": "Soft Gaze",
                    "status": "published",
                },
            },
            storage_ref="",
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": "visual_acceptance_followup_request",
                "review_bundle_id": "vrb_dispatch_publish_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "capability_consumer_handoff",
                "consumer_kind": "capability_owned_consumer",
                "request_state": "ready",
            },
        )
    )

    app = FastAPI()
    app.include_router(artifacts_routes.router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/workspaces/ws_demo/artifacts/vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff/dispatch-followup",
            json={
                "actor_id": "operator_demo",
                "notes": "Dispatch capability consumer handoff",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["dispatch_status"] == "pending_worker"
    assert payload["artifact"]["metadata"]["request_state"] == "dispatched"
    assert payload["dispatch_artifact"]["metadata"]["dispatch_status"] == "pending_worker"
    assert payload["dispatch_artifact"]["content"]["dispatch_mode"] == "consumer_handoff"
    assert payload["dispatch_result"]["handoff_reason"] == "capability_owned_consumer_required"
    assert payload["dispatch_result"]["package_id"] == "charpkg_demo"

    updated_request_artifact = fake_artifacts.get_artifact(
        "vafreq_vrb_dispatch_publish_demo_capability_consumer_handoff"
    )
    assert updated_request_artifact is not None
    assert updated_request_artifact.metadata["request_state"] == "dispatched"

    updated_bundle = fake_artifacts.get_artifact("vrb_dispatch_publish_demo")
    assert updated_bundle is not None
    assert updated_bundle.content["followup_request_refs"][0]["request_state"] == "dispatched"
