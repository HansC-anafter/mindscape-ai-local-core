from __future__ import annotations

from workspace_object_runtime_api_helpers import (
    ASGIAsyncTestClient,
    StubWorkspaceStore,
    build_test_app,
    module,
    seed_registry,
)


def test_materialize_object_outcome_returns_owner_review_plan(monkeypatch, tmp_path):
    registry = seed_registry(tmp_path)
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

    client = ASGIAsyncTestClient(build_test_app())
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
    registry = seed_registry(tmp_path)
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

    client = ASGIAsyncTestClient(build_test_app())
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
    registry = seed_registry(tmp_path)
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

    client = ASGIAsyncTestClient(build_test_app())
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
