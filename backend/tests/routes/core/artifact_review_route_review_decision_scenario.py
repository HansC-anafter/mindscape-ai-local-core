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

async def run_review_decision_scenario(monkeypatch, tmp_path):
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
    manifest_path = tmp_path / "default" / "multi_media_studio" / "projects" / "proj_demo" / "visual_acceptance" / run["run_id"] / "A01" / "vrb_demo.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "review_bundle_id": "vrb_demo",
                "tenant_id": "default",
                "project_id": "proj_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "source_kind": "vr_render",
                "status": "pending_review",
                "slots": [{"slot": "final_render", "storage_key": "renders/a01.mp4"}],
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
        clip_refs=[{"storage_key": "renders/a01.mp4"}],
        provider_metadata={
            "visual_acceptance_state": "pending_review",
            "review_bundle_refs": [
                {
                    "artifact_id": "vrb_demo",
                    "review_bundle_id": "vrb_demo",
                    "manifest_path": str(manifest_path),
                    "status": "pending_review",
                    "source_kind": "vr_render",
                }
            ],
        },
    )

    fake_artifacts.create_artifact(
        Artifact(
            id="vrb_demo",
            workspace_id="ws_demo",
            execution_id="visual_acceptance:run:A01",
            playbook_code="visual_acceptance_review",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Bundle: A01",
            summary="bundle",
            content={
                "review_bundle_id": "vrb_demo",
                "tenant_id": "default",
                "project_id": "proj_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "status": "pending_review",
                "slots": [{"slot": "final_render", "storage_key": "renders/a01.mp4"}],
            },
            storage_ref=str(manifest_path),
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "kind": "visual_acceptance_bundle",
                "review_bundle_id": "vrb_demo",
                "manifest_path": str(manifest_path),
                "visual_acceptance_state": "pending_review",
            },
        )
    )

    app = FastAPI()
    app.include_router(artifacts_routes.router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/workspaces/ws_demo/artifacts/vrb_demo/review-decision",
            json={
                "decision": "accepted",
                "reviewer_id": "reviewer_demo",
                "notes": "Looks good.",
                "checklist_scores": {"identity_consistency": 1.0},
                "followup_actions": ["capability_consumer_handoff"],
            },
        )
        followup_response = await client.post(
            "/api/v1/workspaces/ws_demo/artifacts/vafreq_vrb_demo_capability_consumer_handoff/followup-request-state",
            json={
                "request_state": "dispatched",
                "actor_id": "worker_demo",
                "notes": "Queued into capability consumer handoff lane.",
                "execution_ref": {
                    "execution_id": "publish_job_demo",
                    "lane_id": "capability_consumer_handoff",
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["review_decision"]["decision"] == "accepted"
    assert payload["artifact"]["metadata"]["visual_acceptance_state"] == "accepted"
    assert payload["artifact"]["content"]["latest_review_decision"]["decision"] == "accepted"
    assert payload["artifact"]["content"]["latest_review_decision"]["followup_actions"] == [
        "capability_consumer_handoff"
    ]
    assert payload["artifact"]["content"]["followup_request_refs"][0]["lane_id"] == "capability_consumer_handoff"
    assert payload["artifact"]["content"]["followup_request_refs"][0]["request_state"] == "ready"

    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest["status"] == "accepted"
    assert updated_manifest["latest_review_decision"]["reviewer_id"] == "reviewer_demo"
    assert updated_manifest["latest_review_decision"]["followup_actions"] == [
        "capability_consumer_handoff"
    ]
    assert updated_manifest["followup_request_refs"][0]["lane_id"] == "capability_consumer_handoff"

    updated_run = production_run.get_run("default", "proj_demo", run["run_id"])
    assert updated_run is not None
    scene_result = updated_run["scene_results"][0]
    assert scene_result["provider_metadata"]["visual_acceptance_state"] == "accepted"
    assert scene_result["provider_metadata"]["review_decision_ref"]["artifact_id"] == "vrb_demo"
    assert scene_result["provider_metadata"]["review_decision_ref"]["followup_actions"] == [
        "capability_consumer_handoff"
    ]
    assert scene_result["provider_metadata"]["review_bundle_refs"][0]["status"] == "accepted"
    assert scene_result["provider_metadata"]["review_bundle_refs"][0]["review_decision"][
        "followup_actions"
    ] == ["capability_consumer_handoff"]
    assert scene_result["provider_metadata"]["followup_request_refs"][0]["lane_id"] == "capability_consumer_handoff"

    followup_request_artifact = fake_artifacts.get_artifact("vafreq_vrb_demo_capability_consumer_handoff")
    assert followup_request_artifact is not None
    assert followup_request_artifact.metadata["kind"] == "visual_acceptance_followup_request"
    assert followup_request_artifact.metadata["request_state"] == "dispatched"

    assert followup_response.status_code == 200
    followup_payload = followup_response.json()
    assert followup_payload["success"] is True
    assert followup_payload["request_state"] == "dispatched"
    assert followup_payload["transition"]["actor_id"] == "worker_demo"
    assert followup_payload["transition"]["execution_ref"] == {
        "execution_id": "publish_job_demo",
        "lane_id": "capability_consumer_handoff",
    }
    assert followup_payload["artifact"]["metadata"]["request_state"] == "dispatched"
    assert (
        followup_payload["artifact"]["content"]["request_events"][-1]["request_state"]
        == "dispatched"
    )

    dispatched_request_artifact = fake_artifacts.get_artifact(
        "vafreq_vrb_demo_capability_consumer_handoff"
    )
    assert dispatched_request_artifact is not None
    assert dispatched_request_artifact.metadata["request_state"] == "dispatched"
    assert dispatched_request_artifact.content["last_transition"]["actor_id"] == "worker_demo"

    dispatched_bundle = fake_artifacts.get_artifact("vrb_demo")
    assert dispatched_bundle is not None
    assert dispatched_bundle.content["followup_request_refs"][0]["request_state"] == "dispatched"
    assert (
        dispatched_bundle.content["latest_review_decision"]["followup_request_refs"][0][
            "last_transition"
        ]["execution_ref"]["execution_id"]
        == "publish_job_demo"
    )

    dispatched_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert dispatched_manifest["followup_request_refs"][0]["request_state"] == "dispatched"
    assert (
        dispatched_manifest["latest_review_decision"]["followup_request_refs"][0][
            "last_transition"
        ]["actor_id"]
        == "worker_demo"
    )

    dispatched_run = production_run.get_run("default", "proj_demo", run["run_id"])
    assert dispatched_run is not None
    dispatched_provider_metadata = dispatched_run["scene_results"][0]["provider_metadata"]
    assert (
        dispatched_provider_metadata["followup_request_refs"][0]["request_state"]
        == "dispatched"
    )
    assert (
        dispatched_provider_metadata["review_decision_ref"]["followup_request_refs"][0][
            "last_transition"
        ]["notes"]
        == "Queued into capability consumer handoff lane."
    )
    assert (
        dispatched_provider_metadata["review_bundle_refs"][0]["followup_request_refs"][0][
            "request_state"
        ]
        == "dispatched"
    )
