from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sys

from fastapi import FastAPI
import httpx
import pytest

LOCAL_CORE_ROOT = Path("/Users/shock/Projects_local/workspace/mindscape-ai-local-core")
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from backend.app.capabilities.multi_media_studio.api.production_runs_api import (
    router as mms_router,
)
from backend.app.capabilities.multi_media_studio.tools.storyboard_patch import (
    apply_storyboard_scene_patch as apply_mms_storyboard_scene_patch,
)
from backend.app.capabilities.performance_direction.api import router as pd_router
from backend.app.capabilities.performance_direction.tools.storyboard_patch import (
    apply_scene_patch_to_storyboard,
    apply_storyboard_scene_patch,
)


def test_apply_scene_patch_to_storyboard_merges_object_contract():
    storyboard = {
        "workspace_id": "ws_demo",
        "scenes": [
            {
                "scene_id": "sc01",
                "object_assets": [
                    {
                        "object_target_id": "subject_main",
                        "object_instance_id": "obj_subject_main",
                        "asset_ref": {"storage_key": "storage/subject_main.png"},
                    }
                ],
            }
        ],
    }

    patched = apply_scene_patch_to_storyboard(
        storyboard=storyboard,
        scene_id="sc01",
        storyboard_scene_patch={
            "object_assets": [
                {
                    "object_target_id": "dress_form",
                    "object_instance_id": "obj_dress_form",
                    "asset_ref": {"storage_key": "storage/dress_form.png"},
                }
            ],
            "object_reuse_plan": {"usage_scene_ids": ["A01"]},
            "object_workload_snapshot": {
                "source_scene_id": "SC_SOURCE_01",
                "usage_scene_ids": ["A01"],
            },
        },
    )

    scene = patched["scenes"][0]
    assert [asset["object_instance_id"] for asset in scene["object_assets"]] == [
        "obj_subject_main",
        "obj_dress_form",
    ]
    assert scene["object_reuse_plan"]["usage_bindings"][0]["scene_id"] == "A01"
    assert scene["object_workload_snapshot"]["source_scene_id"] == "SC_SOURCE_01"


def test_apply_storyboard_scene_patch_persists_new_storyboard_artifact(monkeypatch):
    stored_artifacts = []

    class _Artifact:
        def __init__(self, artifact_id, content_json):
            self.artifact_id = artifact_id
            self.content_json = content_json

        def to_dict(self):
            return {"artifact_id": self.artifact_id, "content_json": self.content_json}

    class _Session:
        session_id = "ds_demo"

    class _Store:
        async def get_session(self, session_id):
            assert session_id == "ds_demo"
            return _Session()

        async def get_artifacts(self, session_id, artifact_type=None):
            assert artifact_type == "storyboard_manifest"
            return [
                _Artifact(
                    "da_storyboard_1",
                    {
                        "source_type": "generative",
                        "storyboard": {
                            "workspace_id": "ws_demo",
                            "scenes": [{"scene_id": "sc01"}],
                        },
                    },
                )
            ]

        async def store_artifact(
            self,
            session_id,
            artifact_type,
            content_json=None,
            asset_path=None,
        ):
            stored_artifacts.append(
                {
                    "session_id": session_id,
                    "artifact_type": artifact_type,
                    "content_json": content_json,
                }
            )
            return _Artifact("da_storyboard_2", content_json)

    class _DB:
        async def commit(self):
            return None

    @asynccontextmanager
    async def _fake_db():
        yield _DB()

    monkeypatch.setitem(
        __import__("sys").modules,
        "app.database",
        type("dbmod", (), {"get_async_session": _fake_db}),
    )
    monkeypatch.setattr(
        "backend.app.capabilities.performance_direction.services.session_store.DirectionSessionStore",
        lambda db: _Store(),
    )

    result = __import__("asyncio").run(
        apply_storyboard_scene_patch(
            session_id="ds_demo",
            scene_id="sc01",
            storyboard_scene_patch={
                "object_assets": [
                    {
                        "object_target_id": "chair_main",
                        "object_instance_id": "obj_chair_main",
                        "asset_ref": {"storage_key": "storage/chair.png"},
                    }
                ]
            },
        )
    )

    assert result["success"] is True
    assert result["patched_from_artifact_id"] == "da_storyboard_1"
    assert stored_artifacts[0]["artifact_type"] == "storyboard_manifest"
    assert (
        stored_artifacts[0]["content_json"]["storyboard"]["scenes"][0]["object_assets"][0]["object_instance_id"]
        == "obj_chair_main"
    )


@pytest.mark.asyncio
async def test_pd_storyboard_scene_patch_route_calls_tool(monkeypatch):
    app = FastAPI()
    app.include_router(pd_router, prefix="/api/v1/capabilities/performance_direction")

    async def _fake_apply_scene_patch(
        *, session_id, scene_id, storyboard_scene_patch, artifact_id=None
    ):
        assert session_id == "ds_demo"
        assert scene_id == "sc01"
        assert artifact_id == "da_storyboard_1"
        assert storyboard_scene_patch["object_assets"][0]["object_instance_id"] == "obj_prop"
        return {
            "success": True,
            "artifact": {"artifact_id": "da_storyboard_2"},
            "storyboard": {"scenes": []},
        }

    monkeypatch.setattr(
        "backend.app.capabilities.performance_direction.tools.storyboard_patch.apply_storyboard_scene_patch",
        _fake_apply_scene_patch,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/capabilities/performance_direction/sessions/ds_demo/storyboard/scene-patch",
            json={
                "scene_id": "sc01",
                "artifact_id": "da_storyboard_1",
                "storyboard_scene_patch": {
                    "object_assets": [
                        {
                            "object_target_id": "prop_main",
                            "object_instance_id": "obj_prop",
                            "asset_ref": {"storage_key": "storage/prop.png"},
                        }
                    ]
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["artifact"]["artifact_id"] == "da_storyboard_2"


@pytest.mark.asyncio
async def test_mms_apply_storyboard_scene_patch_route_returns_patched_storyboard(monkeypatch):
    app = FastAPI()
    app.include_router(mms_router, prefix="/api/v1/capabilities/multi_media_studio")

    async def _fake_apply_storyboard_scene_patch(
        *,
        storyboard,
        scene_id,
        storyboard_scene_patch,
        tenant_id,
    ):
        assert storyboard["workspace_id"] == "ws_demo"
        assert scene_id == "sc01"
        assert storyboard_scene_patch["object_assets"][0]["object_instance_id"] == "obj_prop"
        assert tenant_id == "tenant_demo"
        return {
            "success": True,
            "patched_scene_id": "sc01",
            "storyboard": {
                "workspace_id": "ws_demo",
                "scenes": [
                    {
                        "scene_id": "sc01",
                        "object_assets": [{"object_instance_id": "obj_prop"}],
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "backend.app.capabilities.multi_media_studio.tools.storyboard_patch.apply_storyboard_scene_patch",
        _fake_apply_storyboard_scene_patch,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"X-Tenant-Id": "tenant_demo"},
    ) as client:
        response = await client.post(
            "/api/v1/capabilities/multi_media_studio/production-runs/apply-storyboard-scene-patch",
            json={
                "storyboard": {"workspace_id": "ws_demo", "scenes": [{"scene_id": "sc01"}]},
                "scene_id": "sc01",
                "storyboard_scene_patch": {
                    "object_assets": [
                        {
                            "object_target_id": "prop_main",
                            "object_instance_id": "obj_prop",
                            "asset_ref": {"storage_key": "storage/prop.png"},
                        }
                    ]
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["patched_scene_id"] == "sc01"
    assert payload["storyboard"]["scenes"][0]["object_assets"][0]["object_instance_id"] == "obj_prop"
