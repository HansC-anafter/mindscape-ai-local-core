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


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    return app


def _seed_registry(tmp_path: Path) -> ObjectCatalogRegistry:
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


def test_get_workspace_object_catalog_returns_filtered_entries(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.get(
        "/api/v1/workspaces/ws_demo/object-catalog",
        params={"owner_pack": "ig", "supports": "summary"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws_demo"
    assert payload["catalog_version"].endswith("Z")
    assert payload["entries"] == [
        {
            "owner_pack": "ig",
            "object_kind": "reference",
            "display_name": "IG Reference",
            "canonical_schema": "capabilities.ig.schema.reference",
            "id_field": "reference_id",
            "summary_fields": [
                "reference_id",
                "source_shortcode",
                "thumbnail_url",
            ],
            "supports": ["summary", "relations", "meeting_projection"],
            "resolver_capabilities": {
                "summary": True,
                "detail": False,
                "relations": True,
                "actions": True,
            },
            "meeting_projection_capabilities": {
                "available": True,
                "verbs": ["attach", "recommend"],
            },
            "materializer_capabilities": {
                "available": True,
                "verbs": ["stage"],
                "write_modes": ["proposal_only"],
                "output_types": ["proposal_artifact"],
            },
            "graph_projection_capabilities": {
                "available": False,
                "node_kinds": [],
                "relation_kinds": [],
            },
        }
    ]


def test_get_workspace_object_catalog_returns_404_for_missing_workspace(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=False)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.get("/api/v1/workspaces/ws_missing/object-catalog")

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace 'ws_missing' not found"


def test_resolve_workspace_selection_returns_resolved_object(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    async def _fake_invoke_backend_callable(backend_path, **kwargs):
        assert backend_path == (
            "capabilities.ig.object_layer.reference_resolver:resolve_summary"
        )
        assert kwargs == {"workspace_id": "ws_demo", "object_id": "ref_abc123"}
        return {
            "reference_id": "ref_abc123",
            "display_label": "@demo_handle #short001",
            "source_handle": "@demo_handle",
            "source_shortcode": "short001",
            "analysis_status": "ready",
            "scene_summary": "Warm portrait reference with close-up potential.",
            "tags": ["portrait", "warm"],
            "auto_tags": ["close_up"],
            "image_url": "/api/v1/ig/references/ref_abc123/image?workspace_id=ws_demo",
            "owner_surface_url": "/api/v1/ig/references/ref_abc123?workspace_id=ws_demo",
            "updated_at": "2026-04-23T12:00:00Z",
        }

    monkeypatch.setattr(module, "_invoke_backend_callable", _fake_invoke_backend_callable)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/selection/resolve",
        json={
            "selection_id": "sel_001",
            "surface": {
                "surface_type": "installed_pack_ui",
                "pack_code": "ig",
                "surface_id": "ig.references_grid",
                "route": "/workspaces/ws_demo/capabilities/ig",
            },
            "element": {
                "element_id": "ref-card-abc123",
                "label": "Reference Card",
                "bounds": {"x": 812, "y": 224, "w": 216, "h": 216},
            },
            "hints": {
                "owner_pack": "ig",
                "object_kind": "reference",
                "object_id": "ref_abc123",
                "source_surface": "ig.references_grid",
            },
            "mode": "contextual_actions",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "resolved"
    assert payload["errors"] == []
    assert payload["candidate_objects"] == []
    resolved = payload["resolved_objects"][0]
    assert resolved["ref"] == {
        "uri": "mindscape://ig/reference/ref_abc123",
        "owner_pack": "ig",
        "object_kind": "reference",
        "object_id": "ref_abc123",
        "workspace_id": "ws_demo",
        "version": None,
        "selector": None,
        "source_surface": "ig.references_grid",
    }
    assert resolved["summary"] == {
        "ref": resolved["ref"],
        "title": "@demo_handle #short001",
        "subtitle": "@demo_handle / #short001",
        "summary_text": "Warm portrait reference with close-up potential.",
        "status": "ready",
        "labels": [
            "close_up",
            "ig",
            "portrait",
            "reference",
            "selection",
            "warm",
        ],
        "thumbnail_ref": "/api/v1/ig/references/ref_abc123/image?workspace_id=ws_demo",
        "owner_surface_url": "/api/v1/ig/references/ref_abc123?workspace_id=ws_demo",
        "updated_at": "2026-04-23T12:00:00Z",
    }
    assert [action["action_code"] for action in resolved["actions"]] == [
        "attach_to_meeting",
        "recommend_related_objects",
        "open_owner_surface",
    ]


def test_resolve_workspace_selection_returns_unresolved_for_missing_hints(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/selection/resolve",
        json={
            "selection_id": "sel_002",
            "surface": {
                "surface_type": "installed_pack_ui",
                "pack_code": "ig",
                "surface_id": "ig.references_grid",
            },
            "mode": "resolve_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unresolved"
    assert payload["resolved_objects"] == []
    assert payload["errors"] == [
        {
            "code": "insufficient_hints",
            "message": (
                "Selection did not provide enough addressable object hints to resolve "
                "an ObjectRef."
            ),
        }
    ]


def test_resolve_workspace_selection_rejects_invalid_hint_combination(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/selection/resolve",
        json={
            "selection_id": "sel_003",
            "surface": {
                "surface_type": "installed_pack_ui",
                "pack_code": "ig",
                "surface_id": "ig.references_grid",
            },
            "hints": {
                "owner_pack": "performance_direction",
                "object_kind": "reference",
                "object_id": "ref_abc123",
            },
            "mode": "resolve_only",
        },
    )

    assert response.status_code == 422
    assert "surface.pack_code and hints.owner_pack must match" in response.json()[
        "detail"
    ]


def test_materialize_object_outcome_returns_owner_review_plan(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    async def _fake_invoke_backend_callable(backend_path, **kwargs):
        if backend_path == (
            "capabilities.performance_direction.object_layer.storyboard_runtime:"
            "resolve_storyboard_proposal_artifact_summary"
        ):
            return {
                "proposal_locator_id": "ds_demo_001:da_storyboard_proposal_001",
                "artifact_id": "da_storyboard_proposal_001",
                "display_label": "Proposal da_storyboard_proposal_001",
                "patched_scene_id": "sc01",
                "editorial_status": "pending_review",
                "owner_surface_url": (
                    "/api/v1/capabilities/performance_direction/sessions/"
                    "ds_demo_001/storyboard"
                ),
            }
        assert backend_path == (
            "capabilities.performance_direction.object_layer.storyboard_runtime:"
            "materialize_storyboard_proposal_review"
        )
        assert kwargs["workspace_id"] == "ws_demo"
        assert kwargs["object_id"] == "ds_demo_001:da_storyboard_proposal_001"
        assert kwargs["meeting_id"] == "mtg_review_001"
        assert kwargs["verb"] == "promote"
        assert kwargs["write_mode"] == "canonical_with_review"
        assert kwargs["request_context"] == {"approval_state": "approved"}
        return {
            "status": "planned",
            "endpoint": (
                "/api/v1/capabilities/performance_direction/sessions/"
                "ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/promote"
            ),
            "request_template": {"approval_state": "approved"},
            "review_route": (
                "/api/v1/capabilities/performance_direction/sessions/"
                "ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
            ),
            "canonical_storyboard_route": (
                "/api/v1/capabilities/performance_direction/sessions/"
                "ds_demo_001/storyboard"
            ),
        }

    monkeypatch.setattr(module, "_invoke_backend_callable", _fake_invoke_backend_callable)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-materialize",
        json={
            "object_ref": {
                "uri": (
                    "mindscape://performance_direction/storyboard_proposal_artifact/"
                    "ds_demo_001:da_storyboard_proposal_001"
                ),
                "owner_pack": "performance_direction",
                "object_kind": "storyboard_proposal_artifact",
                "object_id": "ds_demo_001:da_storyboard_proposal_001",
                "workspace_id": "ws_demo",
            },
            "verb": "promote",
            "meeting_id": "mtg_review_001",
            "intent_summary": "Promote this approved proposal through the owner review lane.",
            "write_mode": "canonical_with_review",
            "request_context": {"approval_state": "approved"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws_demo"
    assert payload["status"] == "planned"
    assert payload["verb"] == "promote"
    assert payload["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
    ]
    assert payload["canonical_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard"
    ]
    assert payload["request_plan"] == {
        "method": "POST",
        "path": (
            "/api/v1/capabilities/performance_direction/sessions/"
            "ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/promote"
        ),
        "body": {"approval_state": "approved"},
    }


def test_materialize_object_outcome_preserves_role_bearing_context_entries(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    async def _fake_invoke_backend_callable(backend_path, **kwargs):
        if backend_path == (
            "capabilities.performance_direction.object_layer.storyboard_runtime:"
            "resolve_storyboard_proposal_artifact_summary"
        ):
            return {
                "proposal_locator_id": "ds_demo_001:da_storyboard_proposal_001",
                "artifact_id": "da_storyboard_proposal_001",
                "display_label": "Proposal da_storyboard_proposal_001",
                "patched_scene_id": "sc01",
                "editorial_status": "pending_review",
                "owner_surface_url": (
                    "/api/v1/capabilities/performance_direction/sessions/"
                    "ds_demo_001/storyboard"
                ),
            }
        if backend_path == (
            "capabilities.ig.object_layer.reference_resolver:resolve_summary"
        ):
            object_id = kwargs["object_id"]
            return {
                "reference_id": object_id,
                "display_label": f"IG {object_id}",
                "scene_summary": f"summary for {object_id}",
                "owner_surface_url": f"/api/v1/ig/references/{object_id}?workspace_id=ws_demo",
            }
        if backend_path == (
            "capabilities.ig.object_layer.reference_resolver:build_meeting_projection"
        ):
            object_id = kwargs["object_id"]
            return {
                "verb": kwargs["verb"],
                "title": f"IG {object_id}",
                "summary_text": f"summary for {object_id}",
                "object_context": {"reference_id": object_id},
            }

        assert backend_path == (
            "capabilities.performance_direction.object_layer.storyboard_runtime:"
            "materialize_storyboard_proposal_review"
        )
        assert [item["role"] for item in kwargs["source_objects"]] == ["source"]
        assert kwargs["source_objects"][0]["object_id"] == "ref_source_001"
        assert [item["role"] for item in kwargs["context_objects"]] == [
            "source",
            "evidence",
        ]
        assert kwargs["context_objects"][1]["object_id"] == "ref_evidence_001"
        return {
            "status": "planned",
            "endpoint": (
                "/api/v1/capabilities/performance_direction/sessions/"
                "ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/promote"
            ),
            "request_template": {"approval_state": "approved"},
            "review_route": (
                "/api/v1/capabilities/performance_direction/sessions/"
                "ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
            ),
        }

    monkeypatch.setattr(module, "_invoke_backend_callable", _fake_invoke_backend_callable)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-materialize",
        json={
            "object_ref": {
                "uri": (
                    "mindscape://performance_direction/storyboard_proposal_artifact/"
                    "ds_demo_001:da_storyboard_proposal_001"
                ),
                "owner_pack": "performance_direction",
                "object_kind": "storyboard_proposal_artifact",
                "object_id": "ds_demo_001:da_storyboard_proposal_001",
                "workspace_id": "ws_demo",
            },
            "verb": "promote",
            "meeting_id": "mtg_review_001",
            "intent_summary": "Promote this approved proposal through the owner review lane.",
            "write_mode": "canonical_with_review",
            "context_entries": [
                {
                    "role": "source",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_source_001",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_source_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "evidence",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_evidence_001",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_evidence_001",
                        "workspace_id": "ws_demo",
                    },
                },
            ],
            "request_context": {"approval_state": "approved"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planned"
    assert payload["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
    ]


def test_project_object_graph_normalizes_pack_relation_payloads(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    async def _fake_invoke_backend_callable(backend_path, **kwargs):
        if backend_path == (
            "capabilities.performance_direction.object_layer.storyboard_runtime:"
            "resolve_storyboard_proposal_artifact_summary"
        ):
            return {
                "proposal_locator_id": "ds_demo_001:da_storyboard_proposal_001",
                "artifact_id": "da_storyboard_proposal_001",
                "display_label": "Proposal da_storyboard_proposal_001",
                "patched_scene_id": "sc01",
                "editorial_status": "pending_review",
                "owner_surface_url": (
                    "/api/v1/capabilities/performance_direction/sessions/"
                    "ds_demo_001/storyboard"
                ),
            }
        assert backend_path == (
            "capabilities.performance_direction.object_layer.storyboard_runtime:"
            "project_storyboard_proposal_for_graph"
        )
        assert kwargs == {
            "workspace_id": "ws_demo",
            "object_id": "ds_demo_001:da_storyboard_proposal_001",
        }
        return {
            "node_kind": "storyboard_proposal_artifact",
            "relations": [
                {
                    "kind": "patches_storyboard_scene",
                    "target_pack": "performance_direction",
                    "target_kind": "storyboard_scene",
                    "target_object_id": "ds_demo_001:latest:sc01",
                },
                {
                    "relation_kind": "derived_from_reference",
                    "target_owner_pack": "ig",
                    "target_object_kind": "reference",
                    "target_object_id": "ref_001",
                    "confidence": "high",
                },
            ],
            "session_id": "ds_demo_001",
            "artifact_id": "da_storyboard_proposal_001",
        }

    monkeypatch.setattr(module, "_invoke_backend_callable", _fake_invoke_backend_callable)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-graph/project",
        json={
            "objects": [
                {
                    "uri": (
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_001"
                    ),
                    "owner_pack": "performance_direction",
                    "object_kind": "storyboard_proposal_artifact",
                    "object_id": "ds_demo_001:da_storyboard_proposal_001",
                    "workspace_id": "ws_demo",
                }
            ],
            "include_relations": True,
            "include_summaries": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws_demo"
    projection = payload["projections"][0]
    assert projection["node_kind"] == "storyboard_proposal_artifact"
    assert projection["summary"]["title"] == "Proposal da_storyboard_proposal_001"
    assert projection["relations"] == [
        {
            "relation_kind": "patches_storyboard_scene",
            "direction": "outbound",
            "target_ref": {
                "uri": "mindscape://performance_direction/storyboard_scene/ds_demo_001:latest:sc01",
                "owner_pack": "performance_direction",
                "object_kind": "storyboard_scene",
                "object_id": "ds_demo_001:latest:sc01",
                "workspace_id": "ws_demo",
                "version": None,
                "selector": None,
                "source_surface": None,
            },
            "metadata": {},
        },
        {
            "relation_kind": "derived_from_reference",
            "direction": "outbound",
            "target_ref": {
                "uri": "mindscape://ig/reference/ref_001",
                "owner_pack": "ig",
                "object_kind": "reference",
                "object_id": "ref_001",
                "workspace_id": "ws_demo",
                "version": None,
                "selector": None,
                "source_surface": None,
            },
            "metadata": {"confidence": "high"},
        },
    ]
    assert projection["metadata"]["projection_source"] == "owner_pack_graph_projection"
