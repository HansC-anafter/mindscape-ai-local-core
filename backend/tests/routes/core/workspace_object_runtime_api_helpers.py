from __future__ import annotations

import importlib.util
import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import backend.app as backend_app

sys.modules["app"] = backend_app

from backend.app.services.object_catalog_registry import ObjectCatalogRegistry


def _load_object_runtime_module():
    workspace_dir = (
        REPO_ROOT / "backend" / "app" / "routes" / "core" / "workspace"
    )
    package_name = "backend.app.routes.core.workspace"
    if package_name not in sys.modules:
        workspace_package = types.ModuleType(package_name)
        workspace_package.__path__ = [str(workspace_dir)]
        sys.modules[package_name] = workspace_package

    module_path = workspace_dir / "object_runtime.py"
    module_name = "backend.app.routes.core.workspace.object_runtime_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    loaded_module = importlib.util.module_from_spec(spec)
    loaded_module.__package__ = package_name
    spec.loader.exec_module(loaded_module)
    return loaded_module


module = _load_object_runtime_module()


class StubWorkspaceStore:
    def __init__(self, *, existing: bool = True):
        self.existing = existing

    async def get_workspace(self, workspace_id: str):
        if not self.existing:
            return None
        return SimpleNamespace(id=workspace_id)


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

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    return app


def seed_registry(tmp_path: Path) -> ObjectCatalogRegistry:
    registry = ObjectCatalogRegistry(tmp_path)
    registry.sync_pack_objects(
        "ig",
        {
            "object_exports": [
                {
                    "kind": "reference",
                    "display_name": "IG Reference",
                    "canonical_schema": "capabilities.ig.schema.reference",
                    "id_field": "reference_id",
                    "summary_fields": [
                        "reference_id",
                        "source_shortcode",
                        "thumbnail_url",
                    ],
                    "supports": ["summary", "relations", "meeting_projection"],
                }
            ],
            "object_resolvers": [
                {
                    "kind": "reference",
                    "summary_backend": (
                        "capabilities.ig.object_layer.reference_resolver:resolve_summary"
                    ),
                    "relations_backend": (
                        "capabilities.ig.object_layer.reference_resolver:resolve_relations"
                    ),
                    "actions_backend": (
                        "capabilities.ig.object_layer.reference_resolver:resolve_actions"
                    ),
                }
            ],
            "meeting_projections": [
                {
                    "kind": "reference",
                    "projection_backend": (
                        "capabilities.ig.object_layer.reference_resolver:build_meeting_projection"
                    ),
                    "verbs": ["attach", "recommend"],
                }
            ],
            "materializers": [
                {
                    "kind": "reference",
                    "backend": (
                        "capabilities.ig.object_layer.reference_materializer:materialize"
                    ),
                    "verbs": ["stage"],
                    "output_types": ["proposal_artifact"],
                    "write_mode": "proposal_only",
                }
            ],
        },
    )
    registry.sync_pack_objects(
        "performance_direction",
        {
            "object_exports": [
                {
                    "kind": "storyboard_proposal_artifact",
                    "display_name": "Storyboard Proposal Artifact",
                    "canonical_schema": "capabilities.performance_direction.schema.storyboard",
                    "id_field": "proposal_locator_id",
                    "summary_fields": [
                        "proposal_locator_id",
                        "artifact_id",
                        "patched_scene_id",
                    ],
                    "supports": ["summary", "materializer", "graph_projection"],
                }
            ],
            "object_resolvers": [
                {
                    "kind": "storyboard_proposal_artifact",
                    "summary_backend": (
                        "capabilities.performance_direction.object_layer.storyboard_runtime:resolve_storyboard_proposal_artifact_summary"
                    ),
                }
            ],
            "materializers": [
                {
                    "kind": "storyboard_proposal_artifact",
                    "backend": (
                        "capabilities.performance_direction.object_layer.storyboard_runtime:materialize_storyboard_proposal_review"
                    ),
                    "verbs": ["review", "promote"],
                    "output_types": [
                        "review_decision_request",
                        "canonical_storyboard_ref",
                    ],
                    "write_mode": "canonical_with_review",
                }
            ],
            "graph_projections": [
                {
                    "kind": "storyboard_proposal_artifact",
                    "backend": (
                        "capabilities.performance_direction.object_layer.storyboard_runtime:project_storyboard_proposal_for_graph"
                    ),
                    "node_kind": "storyboard_proposal_artifact",
                    "relation_kinds": [
                        "patches_storyboard_scene",
                        "derived_from_reference",
                        "derived_from_storyboard_artifact",
                    ],
                }
            ],
        },
    )
    return registry
