from __future__ import annotations

from workspace_object_runtime_api_helpers import (
    ASGIAsyncTestClient,
    StubWorkspaceStore,
    build_test_app,
    module,
    seed_registry,
)


def test_get_workspace_object_catalog_returns_filtered_entries(monkeypatch, tmp_path):
    registry = seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    client = ASGIAsyncTestClient(build_test_app())
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
    registry = seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=False)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    client = ASGIAsyncTestClient(build_test_app())
    response = client.get("/api/v1/workspaces/ws_missing/object-catalog")

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace 'ws_missing' not found"


def test_resolve_workspace_selection_returns_resolved_object(monkeypatch, tmp_path):
    registry = seed_registry(tmp_path)
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

    client = ASGIAsyncTestClient(build_test_app())
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
    registry = seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    client = ASGIAsyncTestClient(build_test_app())
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
    registry = seed_registry(tmp_path)
    monkeypatch.setattr(
        module, "_get_workspace_store", lambda: StubWorkspaceStore(existing=True)
    )
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)

    client = ASGIAsyncTestClient(build_test_app())
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
