from datetime import datetime, timezone
from types import SimpleNamespace

from workspace_governance_memory_transition_api_test_support import _build_client


def test_workspace_memory_health_aggregates_recent_workflow_evidence(monkeypatch):
    base_time = datetime(2026, 3, 26, 8, 0, tzinfo=timezone.utc)
    sessions = [
        SimpleNamespace(
            id="sess-3",
            workspace_id="ws-1",
            project_id="proj-1",
            thread_id="thread-1",
            meeting_type="decision",
            started_at=base_time,
            ended_at=None,
            metadata={
                "workflow_evidence_diagnostics": {
                    "profile": "decision",
                    "scope": "thread",
                    "selected_line_count": 8,
                    "total_line_budget": 8,
                    "total_candidate_count": 12,
                    "total_dropped_count": 4,
                    "rendered_section_count": 4,
                    "budget_utilization_ratio": 1.0,
                }
            },
        ),
        SimpleNamespace(
            id="sess-2",
            workspace_id="ws-1",
            project_id="proj-1",
            thread_id="thread-1",
            meeting_type="review",
            started_at=base_time.replace(hour=7),
            ended_at=None,
            metadata={
                "workflow_evidence_diagnostics": {
                    "profile": "review",
                    "scope": "thread",
                    "selected_line_count": 2,
                    "total_line_budget": 8,
                    "total_candidate_count": 5,
                    "total_dropped_count": 0,
                    "rendered_section_count": 2,
                    "budget_utilization_ratio": 0.25,
                }
            },
        ),
        SimpleNamespace(
            id="sess-1",
            workspace_id="ws-1",
            project_id="proj-1",
            thread_id="thread-1",
            meeting_type="reflection",
            started_at=base_time.replace(hour=6),
            ended_at=None,
            metadata={
                "workflow_evidence_diagnostics": {
                    "profile": "reflection",
                    "scope": "project",
                    "selected_line_count": 0,
                    "total_line_budget": 8,
                    "total_candidate_count": 0,
                    "total_dropped_count": 0,
                    "rendered_section_count": 0,
                    "budget_utilization_ratio": 0.0,
                }
            },
        ),
    ]
    client, _promotion_service, _item_store, meeting_session_store = _build_client(
        monkeypatch,
        item=None,
        meeting_sessions=sessions,
    )

    response = client.get(
        "/api/v1/workspaces/ws-1/governance/memory-health",
        params={"thread_id": "thread-1", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == "ws-1"
    assert data["thread_id"] == "thread-1"
    assert data["sampled_sessions"] == 3
    assert data["tight_count"] == 1
    assert data["underused_count"] == 1
    assert data["empty_count"] == 1
    assert data["balanced_count"] == 0
    assert data["latest"]["session_id"] == "sess-3"
    assert data["latest"]["classification"] == "tight"
    assert data["average_utilization_ratio"] == 0.417
    assert data["average_selected_line_count"] == 3.33
    assert data["average_total_dropped_count"] == 1.33
    assert [session["session_id"] for session in data["sessions"]] == [
        "sess-3",
        "sess-2",
        "sess-1",
    ]
    assert meeting_session_store.calls == [
        {
            "workspace_id": "ws-1",
            "project_id": None,
            "limit": 9,
            "offset": 0,
        }
    ]
