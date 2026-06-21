from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import backend.app as backend_app

sys.modules["app"] = backend_app

from backend.app.models.meeting_session import MeetingSession
from backend.app.models.object_runtime import ObjectMeetingAttachRequest, ObjectRef
from backend.app.services.object_catalog_registry import ObjectCatalogRegistry


def _load_object_runtime_module():
    workspace_dir = REPO_ROOT / "backend" / "app" / "routes" / "core" / "workspace"
    package_name = "backend.app.routes.core.workspace"
    if package_name not in sys.modules:
        workspace_package = types.ModuleType(package_name)
        workspace_package.__path__ = [str(workspace_dir)]
        sys.modules[package_name] = workspace_package

    module_path = workspace_dir / "object_runtime.py"
    module_name = "backend.app.routes.core.workspace.object_runtime_attach_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    loaded_module = importlib.util.module_from_spec(spec)
    loaded_module.__package__ = package_name
    spec.loader.exec_module(loaded_module)
    return loaded_module


module = _load_object_runtime_module()


class StubWorkspaceStore:
    async def get_workspace(self, workspace_id: str):
        return SimpleNamespace(id=workspace_id)


class StubMeetingSessionStore:
    def __init__(self, existing: MeetingSession | None = None):
        self.created: list[MeetingSession] = []
        self.updated: list[MeetingSession] = []
        self.by_id = {}
        if existing is not None:
            self.by_id[existing.id] = existing

    def get_by_id(self, session_id: str):
        return self.by_id.get(session_id)

    def create(self, session: MeetingSession):
        self.by_id[session.id] = session
        self.created.append(session)
        return session

    def update(self, session: MeetingSession):
        self.by_id[session.id] = session
        self.updated.append(session)
        return session


class ASGIAsyncTestClient:
    def __init__(self, app):
        self.app = app
        self.base_url = "http://testserver"

    def request(self, method, url, **kwargs):
        async def _request():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_request())

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    return app


def _seed_registry(
    tmp_path: Path,
    *,
    include_source_projection: bool = True,
    include_source_summary: bool = True,
):
    registry = ObjectCatalogRegistry(tmp_path)
    registry.sync_pack_objects(
        "ig",
        {
            "object_exports": [
                {
                    "kind": "reference",
                    "display_name": "IG Reference",
                    "id_field": "reference_id",
                    "supports": ["summary", "meeting_projection"],
                }
            ],
            "meeting_projections": (
                [
                    {
                        "kind": "reference",
                        "projection_backend": (
                            "capabilities.ig.object_layer.reference_resolver:build_meeting_projection"
                        ),
                        "verbs": ["attach", "recommend"],
                    }
                ]
                if include_source_projection
                else []
            ),
            "object_resolvers": (
                [
                    {
                        "kind": "reference",
                        "summary_backend": (
                            "capabilities.ig.object_layer.reference_resolver:resolve_summary"
                        ),
                    }
                ]
                if include_source_summary
                else []
            ),
        },
    )
    registry.sync_pack_objects(
        "performance_direction",
        {
            "object_exports": [
                {
                    "kind": "storyboard_scene",
                    "display_name": "Storyboard Scene",
                    "id_field": "scene_id",
                    "supports": ["summary", "materializer"],
                }
            ],
            "materializers": [
                {
                    "kind": "storyboard_scene",
                    "backend": (
                        "capabilities.performance_direction.object_layer.storyboard_materializer:materialize"
                    ),
                    "verbs": ["stage", "review"],
                    "output_types": ["proposal_artifact"],
                    "write_mode": "proposal_only",
                }
            ],
        },
    )
    registry.sync_pack_objects(
        "public_persona_studio",
        {
            "object_exports": [
                {
                    "kind": "foundation_snapshot",
                    "display_name": "PPS Foundation Snapshot",
                    "id_field": "artifact_id",
                    "supports": ["summary", "meeting_projection"],
                },
                {
                    "kind": "pd_workflow_handoff",
                    "display_name": "PPS PD Workflow Handoff",
                    "id_field": "handoff_id",
                    "supports": ["summary", "meeting_projection"],
                },
            ],
            "object_resolvers": [
                {
                    "kind": "foundation_snapshot",
                    "summary_backend": (
                        "capabilities.public_persona_studio.services.object_layer.foundation_snapshot_runtime:resolve_foundation_snapshot_summary"
                    ),
                },
                {
                    "kind": "pd_workflow_handoff",
                    "summary_backend": (
                        "capabilities.public_persona_studio.services.object_layer.pd_workflow_handoff_runtime:resolve_pd_workflow_handoff_summary"
                    ),
                },
            ],
            "meeting_projections": [
                {
                    "kind": "foundation_snapshot",
                    "projection_backend": (
                        "capabilities.public_persona_studio.services.object_layer.foundation_snapshot_runtime:project_foundation_snapshot_for_meeting"
                    ),
                    "verbs": ["attach", "preview"],
                },
                {
                    "kind": "pd_workflow_handoff",
                    "projection_backend": (
                        "capabilities.public_persona_studio.services.object_layer.pd_workflow_handoff_runtime:project_pd_workflow_handoff_for_meeting"
                    ),
                    "verbs": ["attach", "preview"],
                },
            ],
        },
    )
    return registry


async def _fake_scenario_3_invoke_backend_callable(backend_path, **kwargs):
    assert kwargs["workspace_id"] == "ws_demo"
    object_id = kwargs["object_id"]

    if backend_path == (
        "capabilities.public_persona_studio.services.object_layer.foundation_snapshot_runtime:resolve_foundation_snapshot_summary"
    ):
        return {
            "artifact_id": object_id,
            "display_label": "PPS Foundation Snapshot",
            "summary_text": "Brand baseline with governance constraints.",
            "owner_surface_url": "/api/v1/capabilities/public_persona_studio/workbench/state?workspace_id=ws_demo",
        }
    if backend_path == (
        "capabilities.public_persona_studio.services.object_layer.foundation_snapshot_runtime:project_foundation_snapshot_for_meeting"
    ):
        return {
            "verb": "attach",
            "title": "PPS Foundation Snapshot",
            "summary_text": "Brand baseline with governance constraints.",
            "object_context": {
                "artifact_id": object_id,
                "foundation_mode": "brand_foundation",
                "memory_scope": "workspace",
            },
            "preview": {
                "owner_surface_url": "/api/v1/capabilities/public_persona_studio/workbench/state?workspace_id=ws_demo"
            },
        }
    if backend_path == (
        "capabilities.public_persona_studio.services.object_layer.pd_workflow_handoff_runtime:resolve_pd_workflow_handoff_summary"
    ):
        return {
            "handoff_id": object_id,
            "display_label": "weekly_beans_drop",
            "summary_text": "PD handoff with scene intent and preview seed.",
            "owner_surface_url": "/api/v1/capabilities/public_persona_studio/workbench/state?workspace_id=ws_demo",
        }
    if backend_path == (
        "capabilities.public_persona_studio.services.object_layer.pd_workflow_handoff_runtime:project_pd_workflow_handoff_for_meeting"
    ):
        return {
            "verb": "attach",
            "title": "weekly_beans_drop",
            "summary_text": "PD handoff with scene intent and preview seed.",
            "object_context": {
                "handoff_id": object_id,
                "scene_intent": "Coffee shelf reveal with editorial pacing.",
                "preview_route_hint": "performance_direction.storyboard_scene",
                "governance_constraints": {
                    "safety_tier": "brand_safe",
                    "avoid": ["graphic violence"],
                },
                "spatial_schedule_artifact_ref": {
                    "owner_pack": "public_persona_studio",
                    "object_kind": "spatial_schedule_artifact",
                    "object_id": "ssa_demo_001",
                },
            },
            "preview": {
                "owner_surface_url": "/api/v1/capabilities/public_persona_studio/workbench/state?workspace_id=ws_demo"
            },
        }
    if backend_path == (
        "capabilities.ig.object_layer.reference_resolver:resolve_summary"
    ):
        return {
            "reference_id": object_id,
            "display_label": f"@demo_handle #{object_id}",
            "source_handle": "@demo_handle",
            "source_shortcode": object_id,
            "analysis_status": "ready",
            "scene_summary": f"Reference summary for {object_id}",
            "owner_surface_url": f"/api/v1/ig/references/{object_id}?workspace_id=ws_demo",
        }
    if backend_path == (
        "capabilities.ig.object_layer.reference_resolver:build_meeting_projection"
    ):
        return {
            "verb": "attach",
            "title": f"@demo_handle #{object_id}",
            "summary_text": f"Reference summary for {object_id}",
            "object_context": {
                "reference_id": object_id,
                "source_handle": "@demo_handle",
            },
            "preview": {
                "image_url": f"/api/v1/ig/references/{object_id}/image?workspace_id=ws_demo"
            },
        }
    if backend_path == (
        "capabilities.performance_direction.object_layer.storyboard_runtime:resolve_storyboard_scene_summary"
    ):
        return {
            "scene_locator_id": object_id,
            "display_label": "Opening shelf reveal",
            "summary_text": "Canonical scene ready for proposal staging.",
            "owner_surface_url": "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard",
        }

    raise AssertionError(f"Unexpected backend path: {backend_path}")
