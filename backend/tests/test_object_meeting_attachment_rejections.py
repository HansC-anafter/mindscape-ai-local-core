from object_meeting_attachment_test_support import (
    ASGIAsyncTestClient,
    MeetingSession,
    StubMeetingSessionStore,
    StubWorkspaceStore,
    _build_test_app,
    _seed_registry,
    module,
)


def test_object_meeting_attach_rejects_missing_meeting_projection(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path, include_source_projection=False)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    async def _fake_materialize_target_outcome(**kwargs):
        return ("attached", [], [], [], None)
    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "objects": [
                {
                    "uri": "mindscape://ig/reference/ref_abc125",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": "ref_abc125",
                    "workspace_id": "ws_demo",
                }
            ],
            "intent_summary": "Try attaching a non-projectable object.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "projection_unavailable"


def test_object_meeting_attach_rejects_closed_session(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    closed = MeetingSession.new(workspace_id="ws_demo", meeting_type="direction")
    closed.start()
    closed.close()
    meeting_store = StubMeetingSessionStore(existing=closed)
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    async def _fake_materialize_target_outcome(**kwargs):
        return ("attached", [], [], [], None)
    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "meeting_id": closed.id,
            "objects": [
                {
                    "uri": "mindscape://ig/reference/ref_abc126",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": "ref_abc126",
                    "workspace_id": "ws_demo",
                }
            ],
            "intent_summary": "Attach to a closed meeting.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "meeting_closed"


def test_object_meeting_attach_returns_rejected_when_materializer_fails(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)

    async def _fake_materialize_target_outcome(**kwargs):
        return (
            "rejected",
            [],
            [],
            [
                module.SelectionResolveError(
                    code="materializer_failed",
                    message="Owner-pack materializer failed while staging the attach outcome.",
                )
            ],
            None,
        )

    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "objects": [
                {
                    "uri": "mindscape://ig/reference/ref_abc129",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": "ref_abc129",
                    "workspace_id": "ws_demo",
                }
            ],
            "target_ref": {
                "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
                "owner_pack": "performance_direction",
                "object_kind": "storyboard_scene",
                "object_id": "scene_opening_01",
                "workspace_id": "ws_demo",
            },
            "intent_summary": "Try staging a PD proposal artifact.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["staged_refs"] == []
    assert payload["review_routes"] == []
    assert payload["errors"] == [
        {
            "code": "materializer_failed",
            "message": "Owner-pack materializer failed while staging the attach outcome.",
        }
    ]
