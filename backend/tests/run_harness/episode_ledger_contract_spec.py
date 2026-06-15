from backend.app.models.run_harness import (
    RunHarnessEpisode,
    RunHarnessKind,
    RunHarnessResult,
    RunHarnessStatus,
)
from backend.app.services.run_harness.episode_ledger import (
    RunHarnessEpisodeLedgerService,
)


class FakeEpisodeLedgerStore:
    def __init__(self) -> None:
        self.episode = None
        self.selection_snapshot = None
        self.result = None

    def create_episode(self, episode, selection_snapshot):
        self.episode = episode
        self.selection_snapshot = selection_snapshot
        return episode

    def append_event(self, episode_id, event_type, status, payload):
        return 1

    def upsert_result(self, result):
        self.result = result
        return result

    def get_observation(self, episode_id):
        return None

    def get_terminal_result(self, episode_id):
        return self.result


def test_service_requires_workspace_run_and_harness_snapshot_fields() -> None:
    store = FakeEpisodeLedgerStore()
    service = RunHarnessEpisodeLedgerService(store=store)
    episode = RunHarnessEpisode(
        episode_id="episode-1",
        intent_envelope_ref="intent-1",
        selection_ref="selection-1",
    )

    try:
        service.create_episode(episode, {"run_id": "run-1"})
    except ValueError as exc:
        assert "harness_kind" in str(exc)
        assert "workspace_id" in str(exc)
    else:
        raise AssertionError("missing snapshot fields should fail")

    returned = service.create_episode(
        episode,
        {
            "run_id": "run-1",
            "workspace_id": "ws",
            "harness_kind": RunHarnessKind.DETERMINISTIC_TOOL.value,
        },
    )
    assert returned.episode_id == "episode-1"
    assert store.selection_snapshot["workspace_id"] == "ws"


def test_service_returns_terminal_result_through_store() -> None:
    store = FakeEpisodeLedgerStore()
    service = RunHarnessEpisodeLedgerService(store=store)
    result = RunHarnessResult(
        run_id="run-1",
        episode_id="episode-1",
        harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
        status=RunHarnessStatus.SUCCEEDED,
        output_artifact_refs=["artifact:out"],
    )

    service.upsert_result(result)

    terminal = service.get_terminal_result("episode-1")
    assert terminal is not None
    assert terminal.status == RunHarnessStatus.SUCCEEDED
    assert terminal.output_artifact_refs == ["artifact:out"]
