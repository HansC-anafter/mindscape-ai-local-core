from pathlib import Path
import importlib
import json
import sys
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
import pytest

LOCAL_CORE_ROOT = Path("/Users/shock/Projects_local/workspace/mindscape-ai-local-core")
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from backend.app.capabilities.multi_media_studio.models import production_run
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services import mindscape_store, visual_acceptance_followup_requests


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


@pytest.mark.asyncio
async def test_artifact_review_route_persists_decision_and_syncs_run(monkeypatch, tmp_path):
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
                "followup_actions": ["pack_consumer_handoff"],
            },
        )
        followup_response = await client.post(
            "/api/v1/workspaces/ws_demo/artifacts/vafreq_vrb_demo_pack_consumer_handoff/followup-request-state",
            json={
                "request_state": "dispatched",
                "actor_id": "worker_demo",
                "notes": "Queued into pack consumer handoff lane.",
                "execution_ref": {
                    "execution_id": "publish_job_demo",
                    "lane_id": "pack_consumer_handoff",
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
        "pack_consumer_handoff"
    ]
    assert payload["artifact"]["content"]["followup_request_refs"][0]["lane_id"] == "pack_consumer_handoff"
    assert payload["artifact"]["content"]["followup_request_refs"][0]["request_state"] == "ready"

    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest["status"] == "accepted"
    assert updated_manifest["latest_review_decision"]["reviewer_id"] == "reviewer_demo"
    assert updated_manifest["latest_review_decision"]["followup_actions"] == [
        "pack_consumer_handoff"
    ]
    assert updated_manifest["followup_request_refs"][0]["lane_id"] == "pack_consumer_handoff"

    updated_run = production_run.get_run("default", "proj_demo", run["run_id"])
    assert updated_run is not None
    scene_result = updated_run["scene_results"][0]
    assert scene_result["provider_metadata"]["visual_acceptance_state"] == "accepted"
    assert scene_result["provider_metadata"]["review_decision_ref"]["artifact_id"] == "vrb_demo"
    assert scene_result["provider_metadata"]["review_decision_ref"]["followup_actions"] == [
        "pack_consumer_handoff"
    ]
    assert scene_result["provider_metadata"]["review_bundle_refs"][0]["status"] == "accepted"
    assert scene_result["provider_metadata"]["review_bundle_refs"][0]["review_decision"][
        "followup_actions"
    ] == ["pack_consumer_handoff"]
    assert scene_result["provider_metadata"]["followup_request_refs"][0]["lane_id"] == "pack_consumer_handoff"

    followup_request_artifact = fake_artifacts.get_artifact("vafreq_vrb_demo_pack_consumer_handoff")
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
        "lane_id": "pack_consumer_handoff",
    }
    assert followup_payload["artifact"]["metadata"]["request_state"] == "dispatched"
    assert (
        followup_payload["artifact"]["content"]["request_events"][-1]["request_state"]
        == "dispatched"
    )

    dispatched_request_artifact = fake_artifacts.get_artifact(
        "vafreq_vrb_demo_pack_consumer_handoff"
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
        == "Queued into pack consumer handoff lane."
    )
    assert (
        dispatched_provider_metadata["review_bundle_refs"][0]["followup_request_refs"][0][
            "request_state"
        ]
        == "dispatched"
    )


@pytest.mark.asyncio
async def test_dispatch_followup_route_executes_rerender_request(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))

    fake_artifacts = _FakeArtifactsStore()
    fake_store = SimpleNamespace(
        artifacts=fake_artifacts,
        get_workspace=lambda workspace_id: {"id": workspace_id},
    )
    monkeypatch.setattr(mindscape_store, "MindscapeStore", lambda *args, **kwargs: fake_store)

    async def _fake_execute_storyboard(*, project_id, storyboard, source_type, tenant_id):
        assert project_id == "proj_demo"
        assert source_type == "generative"
        assert tenant_id == "default"
        assert storyboard["workspace_id"] == "ws_demo"
        assert storyboard["scenes"][0]["scene_id"] == "A01"
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

    sys.modules.pop("backend.app.routes.core.artifacts", None)
    artifacts_routes = importlib.import_module("backend.app.routes.core.artifacts")

    run = production_run.create_run(
        tenant_id="default",
        project_id="proj_demo",
        storyboard_id="sb_demo",
        source_type="generative",
    )
    manifest_path = tmp_path / "vrb_dispatch_demo.json"
    manifest_path.write_text(
        json.dumps(
            {
                "review_bundle_id": "vrb_dispatch_demo",
                "workspace_id": "ws_demo",
                "tenant_id": "default",
                "project_id": "proj_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "status": "accepted",
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_demo_rerender",
                        "lane_id": "rerender",
                        "consumer_kind": "scene_rerender",
                        "request_state": "ready",
                    }
                ],
                "latest_review_decision": {
                    "decision": "accepted",
                    "followup_request_refs": [
                        {
                            "artifact_id": "vafreq_vrb_dispatch_demo_rerender",
                            "lane_id": "rerender",
                            "consumer_kind": "scene_rerender",
                            "request_state": "ready",
                        }
                    ],
                },
                "review_decisions": [
                    {
                        "decision": "accepted",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_demo_rerender",
                                "lane_id": "rerender",
                                "consumer_kind": "scene_rerender",
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
                    "artifact_id": "vafreq_vrb_dispatch_demo_rerender",
                    "lane_id": "rerender",
                    "consumer_kind": "scene_rerender",
                    "request_state": "ready",
                }
            ],
            "review_decision_ref": {
                "artifact_id": "vrb_dispatch_demo",
                "decision": "accepted",
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_demo_rerender",
                        "lane_id": "rerender",
                        "consumer_kind": "scene_rerender",
                        "request_state": "ready",
                    }
                ],
            },
            "review_bundle_refs": [
                {
                    "artifact_id": "vrb_dispatch_demo",
                    "review_bundle_id": "vrb_dispatch_demo",
                    "status": "accepted",
                    "followup_request_refs": [
                        {
                            "artifact_id": "vafreq_vrb_dispatch_demo_rerender",
                            "lane_id": "rerender",
                            "consumer_kind": "scene_rerender",
                            "request_state": "ready",
                        }
                    ],
                    "review_decision": {
                        "decision": "accepted",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_demo_rerender",
                                "lane_id": "rerender",
                                "consumer_kind": "scene_rerender",
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
            id="vrb_dispatch_demo",
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
                "review_bundle_id": "vrb_dispatch_demo",
                "manifest_path": str(manifest_path),
            },
        )
    )
    fake_artifacts.create_artifact(
        Artifact(
            id="vafreq_vrb_dispatch_demo_rerender",
            workspace_id="ws_demo",
            execution_id=f"visual_acceptance_followup:{run['run_id']}:A01:rerender",
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / rerender",
            summary="rerender request",
            content={
                "request_id": "vafreq_vrb_dispatch_demo_rerender",
                "review_bundle_id": "vrb_dispatch_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "rerender",
                "consumer_kind": "scene_rerender",
                "request_state": "ready",
                "action_ids": ["rerender_same_preset"],
                "target_ref": {"project_id": "proj_demo", "scene_id": "A01"},
                "dispatch_context": {
                    "scene_context": {
                        "scene_payload": {
                            "scene_id": "A01",
                            "scene_manifest": {"shot": "close_up"},
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
                "review_bundle_id": "vrb_dispatch_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "lane_id": "rerender",
                "consumer_kind": "scene_rerender",
                "request_state": "ready",
            },
        )
    )

    app = FastAPI()
    app.include_router(artifacts_routes.router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/workspaces/ws_demo/artifacts/vafreq_vrb_dispatch_demo_rerender/dispatch-followup",
            json={
                "actor_id": "operator_demo",
                "notes": "Dispatch rerender",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["dispatch_status"] == "completed"
    assert payload["artifact"]["metadata"]["request_state"] == "completed"
    assert payload["dispatch_artifact"]["metadata"]["kind"] == "visual_acceptance_followup_dispatch"
    assert payload["dispatch_artifact"]["metadata"]["dispatch_status"] == "completed"
    assert payload["dispatch_result"]["run_id"] == "run_rerender_demo"

    updated_request_artifact = fake_artifacts.get_artifact("vafreq_vrb_dispatch_demo_rerender")
    assert updated_request_artifact is not None
    assert updated_request_artifact.metadata["request_state"] == "completed"

    updated_bundle = fake_artifacts.get_artifact("vrb_dispatch_demo")
    assert updated_bundle is not None
    assert updated_bundle.content["followup_request_refs"][0]["request_state"] == "completed"


@pytest.mark.asyncio
async def test_dispatch_followup_route_executes_laf_patch_request(monkeypatch, tmp_path):
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


@pytest.mark.asyncio
async def test_dispatch_followup_route_handoffs_pack_consumer_handoff_to_pack_owned_consumer(
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
                            "artifact_id": "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
                            "lane_id": "pack_consumer_handoff",
                            "consumer_kind": "pack_owned_consumer",
                            "request_state": "ready",
                        }
                    ],
                },
                "review_decisions": [
                    {
                        "decision": "accepted",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
                                "lane_id": "pack_consumer_handoff",
                                "consumer_kind": "pack_owned_consumer",
                                "request_state": "ready",
                            }
                        ],
                    }
                ],
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
                        "lane_id": "pack_consumer_handoff",
                        "consumer_kind": "pack_owned_consumer",
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
                    "artifact_id": "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
                    "lane_id": "pack_consumer_handoff",
                    "consumer_kind": "pack_owned_consumer",
                    "request_state": "ready",
                }
            ],
            "review_decision_ref": {
                "artifact_id": "vrb_dispatch_publish_demo",
                "decision": "accepted",
                "followup_request_refs": [
                    {
                        "artifact_id": "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
                        "lane_id": "pack_consumer_handoff",
                        "consumer_kind": "pack_owned_consumer",
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
                            "artifact_id": "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
                            "lane_id": "pack_consumer_handoff",
                            "consumer_kind": "pack_owned_consumer",
                            "request_state": "ready",
                        }
                    ],
                    "review_decision": {
                        "decision": "accepted",
                        "followup_request_refs": [
                            {
                                "artifact_id": "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
                                "lane_id": "pack_consumer_handoff",
                                "consumer_kind": "pack_owned_consumer",
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
            id="vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
            workspace_id="ws_demo",
            execution_id=(
                f"visual_acceptance_followup:{run['run_id']}:A01:pack_consumer_handoff"
            ),
            playbook_code="visual_acceptance_followup",
            artifact_type=ArtifactType.DATA,
            title="Visual Acceptance Follow-up: A01 / pack_consumer_handoff",
            summary="publish candidate request",
            content={
                "request_id": "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff",
                "review_bundle_id": "vrb_dispatch_publish_demo",
                "run_id": run["run_id"],
                "scene_id": "A01",
                "workspace_id": "ws_demo",
                "lane_id": "pack_consumer_handoff",
                "consumer_kind": "pack_owned_consumer",
                "request_state": "ready",
                "package_id": "charpkg_demo",
                "preset_id": "preset_alpha",
                "artifact_ids": ["artifact_alpha"],
                "binding_mode": "hybrid",
                "action_ids": ["pack_consumer_handoff"],
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
                "lane_id": "pack_consumer_handoff",
                "consumer_kind": "pack_owned_consumer",
                "request_state": "ready",
            },
        )
    )

    app = FastAPI()
    app.include_router(artifacts_routes.router)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/workspaces/ws_demo/artifacts/vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff/dispatch-followup",
            json={
                "actor_id": "operator_demo",
                "notes": "Dispatch pack consumer handoff",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["dispatch_status"] == "pending_worker"
    assert payload["artifact"]["metadata"]["request_state"] == "dispatched"
    assert payload["dispatch_artifact"]["metadata"]["dispatch_status"] == "pending_worker"
    assert payload["dispatch_artifact"]["content"]["dispatch_mode"] == "consumer_handoff"
    assert payload["dispatch_result"]["handoff_reason"] == "pack_owned_consumer_required"
    assert payload["dispatch_result"]["package_id"] == "charpkg_demo"

    updated_request_artifact = fake_artifacts.get_artifact(
        "vafreq_vrb_dispatch_publish_demo_pack_consumer_handoff"
    )
    assert updated_request_artifact is not None
    assert updated_request_artifact.metadata["request_state"] == "dispatched"

    updated_bundle = fake_artifacts.get_artifact("vrb_dispatch_publish_demo")
    assert updated_bundle is not None
    assert updated_bundle.content["followup_request_refs"][0]["request_state"] == "dispatched"


@pytest.mark.asyncio
async def test_dispatch_followup_route_queues_local_scene_review_artifact(
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
