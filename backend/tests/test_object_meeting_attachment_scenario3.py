from object_meeting_attachment_test_support import (
    ASGIAsyncTestClient,
    ObjectRef,
    StubMeetingSessionStore,
    StubWorkspaceStore,
    _build_test_app,
    _fake_scenario_3_invoke_backend_callable,
    _seed_registry,
    module,
)


def test_object_meeting_attach_preserves_scenario_3_roles_without_target(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    monkeypatch.setattr(
        module,
        "_invoke_backend_callable",
        _fake_scenario_3_invoke_backend_callable,
    )

    async def _unexpected_materialize_target_outcome(**kwargs):
        raise AssertionError("target materialization should not run without a target entry")

    monkeypatch.setattr(
        module,
        "_materialize_target_outcome",
        _unexpected_materialize_target_outcome,
    )

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "scenario_3_preflight",
            "entries": [
                {
                    "role": "baseline",
                    "ref": {
                        "uri": "mindscape://public_persona_studio/foundation_snapshot/foundation_001",
                        "owner_pack": "public_persona_studio",
                        "object_kind": "foundation_snapshot",
                        "object_id": "foundation_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "constraint",
                    "ref": {
                        "uri": "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001",
                        "owner_pack": "public_persona_studio",
                        "object_kind": "pd_workflow_handoff",
                        "object_id": "handoff_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "evidence",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_evidence_002",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_evidence_002",
                        "workspace_id": "ws_demo",
                        "source_surface": "ig.references_grid",
                    },
                },
            ],
            "intent_summary": "Attach baseline, constraint, and evidence before target staging.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "attached"
    assert payload["staged_refs"] == []
    assert payload["review_routes"] == []
    assert payload["errors"] == []
    assert [attachment["role"] for attachment in payload["attachments"]] == [
        "baseline",
        "constraint",
        "evidence",
    ]

    assert len(meeting_store.created) == 1
    created_session = meeting_store.created[0]
    metadata = created_session.metadata["addressable_object_layer"]
    assert metadata["write_mode"] == "proposal_only"
    assert metadata["status"] == "attached"
    assert metadata["target_ref"] is None
    assert metadata["context_entries"] == [
        {
            "role": "baseline",
            "ref": {
                "uri": "mindscape://public_persona_studio/foundation_snapshot/foundation_001",
                "owner_pack": "public_persona_studio",
                "object_kind": "foundation_snapshot",
                "object_id": "foundation_001",
                "workspace_id": "ws_demo",
            },
        },
        {
            "role": "constraint",
            "ref": {
                "uri": "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001",
                "owner_pack": "public_persona_studio",
                "object_kind": "pd_workflow_handoff",
                "object_id": "handoff_001",
                "workspace_id": "ws_demo",
            },
        },
        {
            "role": "evidence",
            "ref": {
                "uri": "mindscape://ig/reference/ref_evidence_002",
                "owner_pack": "ig",
                "object_kind": "reference",
                "object_id": "ref_evidence_002",
                "workspace_id": "ws_demo",
                "source_surface": "ig.references_grid",
            },
        },
    ]
    handoff_metadata = metadata["handoff_in"]["metadata"]["addressable_object_layer"]
    assert handoff_metadata["role_object_uris"] == {
        "baseline": [
            "mindscape://public_persona_studio/foundation_snapshot/foundation_001"
        ],
        "constraint": [
            "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001"
        ],
        "evidence": ["mindscape://ig/reference/ref_evidence_002"],
    }
    attachments = metadata["context_attachments"]
    assert [attachment["role"] for attachment in attachments] == [
        "baseline",
        "constraint",
        "evidence",
    ]
    assert attachments[0]["meeting_projection"]["payload"]["object_context"] == {
        "artifact_id": "foundation_001",
        "foundation_mode": "brand_foundation",
        "memory_scope": "workspace",
    }
    assert attachments[1]["meeting_projection"]["payload"]["object_context"] == {
        "handoff_id": "handoff_001",
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
    }
    assert attachments[2]["meeting_projection"]["payload"]["object_context"] == {
        "reference_id": "ref_evidence_002",
        "source_handle": "@demo_handle",
    }


def test_object_meeting_attach_materializes_scenario_3_target_bundle(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    monkeypatch.setattr(
        module,
        "_invoke_backend_callable",
        _fake_scenario_3_invoke_backend_callable,
    )

    async def _fake_materialize_target_outcome(**kwargs):
        assert kwargs["target_ref"].uri == (
            "mindscape://performance_direction/storyboard_scene/ds_demo_001:da_storyboard_001:sc01"
        )
        assert [record.role for record in kwargs["context_records"]] == [
            "baseline",
            "constraint",
            "evidence",
            "target",
        ]
        return (
            "materialized",
            [
                ObjectRef(
                    uri=(
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_030"
                    ),
                    owner_pack="performance_direction",
                    object_kind="storyboard_proposal_artifact",
                    object_id="ds_demo_001:da_storyboard_proposal_030",
                    workspace_id="ws_demo",
                )
            ],
            [
                "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_030/review"
            ],
            [],
            {
                "status": "materialized",
                "staged_ref": {
                    "uri": (
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_030"
                    ),
                    "owner_pack": "performance_direction",
                    "object_kind": "storyboard_proposal_artifact",
                    "object_id": "ds_demo_001:da_storyboard_proposal_030",
                },
                "review_route": (
                    "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/"
                    "storyboard/proposals/da_storyboard_proposal_030/review"
                ),
            },
        )

    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "scenario_3_preflight",
            "entries": [
                {
                    "role": "baseline",
                    "ref": {
                        "uri": "mindscape://public_persona_studio/foundation_snapshot/foundation_001",
                        "owner_pack": "public_persona_studio",
                        "object_kind": "foundation_snapshot",
                        "object_id": "foundation_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "constraint",
                    "ref": {
                        "uri": "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001",
                        "owner_pack": "public_persona_studio",
                        "object_kind": "pd_workflow_handoff",
                        "object_id": "handoff_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "evidence",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_evidence_002",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_evidence_002",
                        "workspace_id": "ws_demo",
                        "source_surface": "ig.references_grid",
                    },
                },
                {
                    "role": "target",
                    "ref": {
                        "uri": "mindscape://performance_direction/storyboard_scene/ds_demo_001:da_storyboard_001:sc01",
                        "owner_pack": "performance_direction",
                        "object_kind": "storyboard_scene",
                        "object_id": "ds_demo_001:da_storyboard_001:sc01",
                        "workspace_id": "ws_demo",
                    },
                },
            ],
            "intent_summary": "Stage the full Scenario 3 bundle into a PD proposal artifact.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "materialized"
    assert [attachment["role"] for attachment in payload["attachments"]] == [
        "baseline",
        "constraint",
        "evidence",
        "target",
    ]
    assert payload["staged_refs"] == [
        {
            "uri": (
                "mindscape://performance_direction/storyboard_proposal_artifact/"
                "ds_demo_001:da_storyboard_proposal_030"
            ),
            "owner_pack": "performance_direction",
            "object_kind": "storyboard_proposal_artifact",
            "object_id": "ds_demo_001:da_storyboard_proposal_030",
            "workspace_id": "ws_demo",
            "version": None,
            "selector": None,
            "source_surface": None,
        }
    ]
    assert payload["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_030/review"
    ]

    assert len(meeting_store.created) == 1
    created_session = meeting_store.created[0]
    metadata = created_session.metadata["addressable_object_layer"]
    assert metadata["status"] == "materialized"
    assert metadata["target_ref"] == {
        "uri": "mindscape://performance_direction/storyboard_scene/ds_demo_001:da_storyboard_001:sc01",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_scene",
        "object_id": "ds_demo_001:da_storyboard_001:sc01",
        "workspace_id": "ws_demo",
    }
    assert metadata["staged_refs"][0]["object_id"] == "ds_demo_001:da_storyboard_proposal_030"
    assert metadata["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_030/review"
    ]
    assert metadata["materialization_result"]["status"] == "materialized"
    assert metadata["handoff_in"]["metadata"]["addressable_object_layer"]["role_object_uris"] == {
        "baseline": [
            "mindscape://public_persona_studio/foundation_snapshot/foundation_001"
        ],
        "constraint": [
            "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001"
        ],
        "evidence": ["mindscape://ig/reference/ref_evidence_002"],
        "target": [
            "mindscape://performance_direction/storyboard_scene/ds_demo_001:da_storyboard_001:sc01"
        ],
    }
