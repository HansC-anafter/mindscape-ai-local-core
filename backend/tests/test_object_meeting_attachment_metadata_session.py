from datetime import datetime, timezone

from object_meeting_attachment_test_support import (
    ASGIAsyncTestClient,
    MeetingSession,
    ObjectMeetingAttachRequest,
    ObjectRef,
    StubMeetingSessionStore,
    StubWorkspaceStore,
    _build_test_app,
    _seed_registry,
    module,
)


def test_build_session_attachment_metadata_coerces_datetime_materialization_payload():
    request = ObjectMeetingAttachRequest(
        meeting_type="direction",
        objects=[
            ObjectRef(
                uri="mindscape://ig/reference/ref_abc123",
                owner_pack="ig",
                object_kind="reference",
                object_id="ref_abc123",
                workspace_id="ws_demo",
            )
        ],
        intent_summary="Stage attach smoke artifact",
        write_mode="proposal_only",
    )

    metadata = module._build_session_attachment_metadata(
        request=request,
        handoff_payload={
            "context_attachments": [],
            "created_at": datetime(2026, 4, 23, 11, 59, tzinfo=timezone.utc),
        },
        response_status="materialized",
        staged_refs=[],
        review_routes=[],
        materialization_result={
            "status": "materialized",
            "artifact": {
                "artifact_id": "da_storyboard_proposal_001",
                "created_at": datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc),
            },
        },
    )

    assert metadata["materialization_result"] == {
        "status": "materialized",
        "artifact": {
            "artifact_id": "da_storyboard_proposal_001",
            "created_at": "2026-04-23T12:00:00+00:00",
        },
    }
    assert metadata["handoff_in"]["created_at"] == "2026-04-23T11:59:00+00:00"


def test_object_meeting_attach_uses_existing_session(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    existing = MeetingSession.new(workspace_id="ws_demo", meeting_type="direction")
    existing.start()
    meeting_store = StubMeetingSessionStore(existing=existing)
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    async def _fake_materialize_target_outcome(**kwargs):
        return ("attached", [], [], [], None)
    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        f"/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "meeting_id": existing.id,
            "objects": [
                {
                    "uri": "mindscape://ig/reference/ref_abc124",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": "ref_abc124",
                    "workspace_id": "ws_demo",
                }
            ],
            "intent_summary": "Attach another source ref to the open meeting.",
            "write_mode": "recommendation_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meeting_id"] == existing.id
    assert meeting_store.created == []
    assert meeting_store.updated[-1].metadata["addressable_object_layer"][
        "write_mode"
    ] == "recommendation_only"
