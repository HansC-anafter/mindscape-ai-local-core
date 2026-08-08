from collections import OrderedDict, defaultdict

from backend.app.routes.agent_dispatch.message_completion_state import (
    MessageCompletionStateMixin,
)


class CompletionStateHarness(MessageCompletionStateMixin):
    COMPLETED_MAX_SIZE = 1000

    def __init__(self) -> None:
        self._completed = OrderedDict()
        self._pending_queue = defaultdict(list)
        self._inflight = {}


def _resume(
    harness: CompletionStateHarness,
    *,
    workspace_id: str,
    surface_type: str = "codex_cli",
    recent_execution_ids: list[str] | None = None,
    last_completed_at: float | None = None,
) -> dict:
    return harness._build_resume_sync(
        workspace_id=workspace_id,
        surface_type=surface_type,
        recent_execution_ids=recent_execution_ids or [],
        pending_rest_execution_ids=[],
        last_completed_at=last_completed_at,
    )


def test_fresh_client_does_not_replay_global_completion_cache() -> None:
    harness = CompletionStateHarness()
    harness._mark_completed_execution(
        "execution-a",
        workspace_id="workspace-a",
        surface_type="codex_cli",
    )

    response = _resume(
        harness,
        workspace_id="workspace-a",
        last_completed_at=0.0,
    )

    assert response["replayed_completions"] == []
    assert response["duplicates_to_ignore"] == []


def test_known_execution_replays_only_inside_its_workspace() -> None:
    harness = CompletionStateHarness()
    harness._mark_completed_execution(
        "execution-a",
        workspace_id="workspace-a",
        surface_type="codex_cli",
    )

    matching = _resume(
        harness,
        workspace_id="workspace-a",
        recent_execution_ids=["execution-a"],
    )
    mismatched = _resume(
        harness,
        workspace_id="workspace-b",
        recent_execution_ids=["execution-a"],
    )

    assert [
        item["execution_id"] for item in matching["replayed_completions"]
    ] == ["execution-a"]
    assert matching["duplicates_to_ignore"] == ["execution-a"]
    assert mismatched["replayed_completions"] == []
    assert mismatched["duplicates_to_ignore"] == []


def test_timestamp_catchup_is_scoped_by_workspace_and_surface() -> None:
    harness = CompletionStateHarness()
    harness._completed["same-client"] = {
        "execution_id": "same-client",
        "completed_at": 200.0,
        "status": "completed",
        "workspace_id": "workspace-a",
        "surface_type": "codex_cli",
    }
    harness._completed["other-workspace"] = {
        "execution_id": "other-workspace",
        "completed_at": 201.0,
        "status": "completed",
        "workspace_id": "workspace-b",
        "surface_type": "codex_cli",
    }
    harness._completed["other-surface"] = {
        "execution_id": "other-surface",
        "completed_at": 202.0,
        "status": "completed",
        "workspace_id": "workspace-a",
        "surface_type": "gemini_cli",
    }

    response = _resume(
        harness,
        workspace_id="workspace-a",
        surface_type="codex_cli",
        last_completed_at=100.0,
    )

    assert [
        item["execution_id"] for item in response["replayed_completions"]
    ] == ["same-client"]


def test_legacy_unscoped_completion_is_not_exposed() -> None:
    harness = CompletionStateHarness()
    harness._completed["legacy"] = 200.0

    response = _resume(
        harness,
        workspace_id="workspace-a",
        recent_execution_ids=["legacy"],
        last_completed_at=100.0,
    )

    assert response["replayed_completions"] == []
    assert response["duplicates_to_ignore"] == []


def test_completion_scope_is_preserved_by_later_landing_update() -> None:
    harness = CompletionStateHarness()
    harness._mark_completed_execution(
        "execution-a",
        workspace_id="workspace-a",
        surface_type="codex_cli",
        status="completed",
    )
    harness._mark_completed_execution(
        "execution-a",
        landing_succeeded=True,
    )

    entry = harness._completed["execution-a"]
    assert entry["workspace_id"] == "workspace-a"
    assert entry["surface_type"] == "codex_cli"
    assert entry["landing_succeeded"] is True
