import pytest

from backend.app.models.meeting_session import MeetingSession
from backend.app.routes import meeting_sessions


class _StubMeetingSessionStore:
    def __init__(self, sessions):
        self._sessions = sessions

    def list_by_workspace(self, workspace_id, project_id=None, limit=20, offset=0):
        return self._sessions[offset: offset + limit]


@pytest.mark.asyncio
async def test_list_sessions_summary_metadata_keeps_aol_context_without_heavy_handoff(monkeypatch):
    session = MeetingSession.new(
        workspace_id="ws_summary",
        meeting_type="direction",
        agenda=["Review reference"],
    )
    session.metadata = {
        "addressable_object_layer": {
            "status": "attached",
            "intent_summary": "Review reference",
            "handoff_in": {"large": "payload"},
            "materialization_result": {"large": "payload"},
            "governance_constraints": {"large": "payload"},
            "context_entries": [
                {
                    "role": "source",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_001",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_001",
                        "workspace_id": "ws_summary",
                        "extra": "drop",
                    },
                }
            ],
            "context_attachments": [
                {
                    "role": "source",
                    "verb": "attach",
                    "owner_pack": "ig",
                    "object_ref": {
                        "uri": "mindscape://ig/reference/ref_001",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_001",
                        "workspace_id": "ws_summary",
                        "raw_payload": {"drop": True},
                    },
                    "object_summary": {
                        "title": "Reference 001",
                        "summary_text": "Reusable visual reference.",
                        "labels": ["ig", "reference"],
                        "owner_surface_url": "/workspaces/ws/capability-ui-hosts/ig",
                        "raw_payload": {"drop": True},
                    },
                    "meeting_projection": {"large": "payload"},
                    "selected_relations": [{"large": "payload"}],
                }
            ],
            "staged_refs": [
                {
                    "uri": "mindscape://performance_direction/storyboard_proposal/proposal_001",
                    "owner_pack": "performance_direction",
                    "object_kind": "storyboard_proposal",
                    "object_id": "proposal_001",
                    "raw_payload": {"drop": True},
                }
            ],
            "review_routes": ["/review/proposal_001"],
        },
        "other_large_metadata": {"drop": True},
    }

    monkeypatch.setattr(
        meeting_sessions,
        "MeetingSessionStore",
        lambda: _StubMeetingSessionStore([session]),
    )

    response = await meeting_sessions.list_sessions(
        "ws_summary",
        project_id=None,
        limit=100,
        offset=0,
        metadata_mode="summary",
    )

    aol_metadata = response["sessions"][0]["metadata"]["addressable_object_layer"]
    assert aol_metadata["status"] == "attached"
    assert aol_metadata["intent_summary"] == "Review reference"
    assert aol_metadata["context_entries"][0]["ref"]["object_id"] == "ref_001"
    assert aol_metadata["context_attachments"][0]["object_summary"]["title"] == "Reference 001"
    assert aol_metadata["staged_refs"][0]["object_id"] == "proposal_001"
    assert aol_metadata["review_routes"] == ["/review/proposal_001"]
    assert "handoff_in" not in aol_metadata
    assert "materialization_result" not in aol_metadata
    assert "governance_constraints" not in aol_metadata
    assert "meeting_projection" not in aol_metadata["context_attachments"][0]
    assert "raw_payload" not in aol_metadata["context_attachments"][0]["object_ref"]
    assert "other_large_metadata" not in response["sessions"][0]["metadata"]


@pytest.mark.asyncio
async def test_list_sessions_rejects_unknown_metadata_mode(monkeypatch):
    monkeypatch.setattr(
        meeting_sessions,
        "MeetingSessionStore",
        lambda: _StubMeetingSessionStore([]),
    )

    with pytest.raises(meeting_sessions.HTTPException) as exc_info:
        await meeting_sessions.list_sessions(
            "ws_summary",
            metadata_mode="expanded",
        )

    assert exc_info.value.status_code == 400
