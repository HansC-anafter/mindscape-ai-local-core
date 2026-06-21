from object_meeting_attachment_test_support import (
    ASGIAsyncTestClient,
    ObjectRef,
    StubMeetingSessionStore,
    StubWorkspaceStore,
    _build_test_app,
    _seed_registry,
    module,
)


def test_object_meeting_attach_creates_session_and_bounded_attachments(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)

    async def _fake_invoke_backend_callable(backend_path, **kwargs):
        if backend_path == (
            "capabilities.ig.object_layer.reference_resolver:resolve_summary"
        ):
            assert kwargs["workspace_id"] == "ws_demo"
            object_id = kwargs["object_id"]
            return {
                "reference_id": object_id,
                "display_label": f"@demo_handle #{object_id}",
                "source_handle": "@demo_handle",
                "source_shortcode": object_id,
                "analysis_status": "ready",
                "scene_summary": f"Reference summary for {object_id}",
                "image_url": f"/api/v1/ig/references/{object_id}/image?workspace_id=ws_demo",
                "owner_surface_url": f"/api/v1/ig/references/{object_id}?workspace_id=ws_demo",
            }
        assert kwargs["workspace_id"] == "ws_demo"
        assert backend_path == (
            "capabilities.ig.object_layer.reference_resolver:build_meeting_projection"
        )
        object_id = kwargs["object_id"]
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

    monkeypatch.setattr(module, "_invoke_backend_callable", _fake_invoke_backend_callable)

    async def _fake_materialize_target_outcome(**kwargs):
        assert kwargs["target_ref"].uri == (
            "mindscape://performance_direction/storyboard_scene/scene_opening_01"
        )
        assert [record.role for record in kwargs["context_records"]] == [
            "source",
            "evidence",
            "target",
        ]
        assert kwargs["context_records"][0].ref.uri == "mindscape://ig/reference/ref_abc123"
        assert kwargs["context_records"][0].meeting_projection["object_context"][
            "reference_id"
        ] == "ref_abc123"
        assert kwargs["context_records"][1].ref.uri == "mindscape://ig/reference/ref_evidence_001"
        return (
            "materialized",
            [
                ObjectRef(
                    uri=(
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_001"
                    ),
                    owner_pack="performance_direction",
                    object_kind="storyboard_proposal_artifact",
                    object_id="ds_demo_001:da_storyboard_proposal_001",
                    workspace_id="ws_demo",
                )
            ],
            [
                "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
            ],
            [],
            {
                "status": "materialized",
                "staged_ref": {
                    "uri": (
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_001"
                    ),
                    "owner_pack": "performance_direction",
                    "object_kind": "storyboard_proposal_artifact",
                    "object_id": "ds_demo_001:da_storyboard_proposal_001",
                },
                "review_route": (
                    "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/"
                    "storyboard/proposals/da_storyboard_proposal_001/review"
                ),
            },
        )
    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "meeting_id": None,
            "entries": [
                {
                    "role": "source",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_abc123",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_abc123",
                        "workspace_id": "ws_demo",
                        "source_surface": "ig.references_grid",
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
                        "source_surface": "ig.references_grid",
                    },
                },
                {
                    "role": "target",
                    "ref": {
                        "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
                        "owner_pack": "performance_direction",
                        "object_kind": "storyboard_scene",
                        "object_id": "scene_opening_01",
                        "workspace_id": "ws_demo",
                    },
                },
            ],
            "intent_summary": (
                "Expand this ref into a 5-10s opening beat and stage it for PD review."
            ),
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws_demo"
    assert payload["status"] == "materialized"
    assert payload["staged_refs"] == [
        {
            "uri": (
                "mindscape://performance_direction/storyboard_proposal_artifact/"
                "ds_demo_001:da_storyboard_proposal_001"
            ),
            "owner_pack": "performance_direction",
            "object_kind": "storyboard_proposal_artifact",
            "object_id": "ds_demo_001:da_storyboard_proposal_001",
            "workspace_id": "ws_demo",
            "version": None,
            "selector": None,
            "source_surface": None,
        }
    ]
    assert payload["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
    ]
    assert [attachment["role"] for attachment in payload["attachments"]] == [
        "source",
        "evidence",
        "target",
    ]
    assert len(meeting_store.created) == 1
    created_session = meeting_store.created[0]
    metadata = created_session.metadata["addressable_object_layer"]
    assert metadata["write_mode"] == "proposal_only"
    assert metadata["status"] == "materialized"
    assert metadata["context_entries"] == [
        {
            "role": "source",
            "ref": {
                "uri": "mindscape://ig/reference/ref_abc123",
                "owner_pack": "ig",
                "object_kind": "reference",
                "object_id": "ref_abc123",
                "workspace_id": "ws_demo",
                "source_surface": "ig.references_grid",
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
                "source_surface": "ig.references_grid",
            },
        },
        {
            "role": "target",
            "ref": {
                "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
                "owner_pack": "performance_direction",
                "object_kind": "storyboard_scene",
                "object_id": "scene_opening_01",
                "workspace_id": "ws_demo",
            },
        },
    ]
    assert metadata["target_ref"]["uri"] == (
        "mindscape://performance_direction/storyboard_scene/scene_opening_01"
    )
    assert metadata["staged_refs"][0]["object_kind"] == "storyboard_proposal_artifact"
    assert metadata["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
    ]
    assert metadata["handoff_in"]["workspace_id"] == "ws_demo"
    attachments = metadata["context_attachments"]
    assert len(attachments) == 3
    source_attachment = attachments[0]
    assert source_attachment["object_ref"]["uri"] == "mindscape://ig/reference/ref_abc123"
    assert source_attachment["object_summary"]["title"] == "@demo_handle #ref_abc123"
    assert "canonical_schema" not in source_attachment
    assert "summary_fields" not in source_attachment
    assert source_attachment["meeting_projection"]["payload"] == {
        "verb": "attach",
        "title": "@demo_handle #ref_abc123",
        "summary_text": "Reference summary for ref_abc123",
        "object_context": {
            "reference_id": "ref_abc123",
            "source_handle": "@demo_handle",
        },
        "preview": {
            "image_url": "/api/v1/ig/references/ref_abc123/image?workspace_id=ws_demo"
        },
    }
    evidence_attachment = attachments[1]
    assert evidence_attachment["role"] == "evidence"
    assert evidence_attachment["object_ref"]["uri"] == (
        "mindscape://ig/reference/ref_evidence_001"
    )
    assert evidence_attachment["meeting_projection"]["payload"]["object_context"][
        "reference_id"
    ] == "ref_evidence_001"
