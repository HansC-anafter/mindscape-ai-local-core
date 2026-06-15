import pytest

from backend.app.models.run_harness import (
    RunHarnessKind,
    RunHarnessResult,
    RunHarnessStatus,
)
from backend.app.services.run_harness.episode_ledger import (
    RunHarnessEpisodeLedgerService,
)


class FakeEpisodeLedgerStore:
    def append_event(self, episode_id, event_type, status, payload):
        return 1

    def upsert_result(self, result):
        return result


def test_event_payload_budget_rejects_large_metadata() -> None:
    service = RunHarnessEpisodeLedgerService(store=FakeEpisodeLedgerStore())

    with pytest.raises(ValueError, match="exceeds 16384 bytes"):
        service.append_event(
            "episode-1",
            "tool.progress",
            RunHarnessStatus.RUNNING.value,
            {"metadata": {"large": "x" * (17 * 1024)}},
        )


def test_result_payload_budget_rejects_large_metadata() -> None:
    service = RunHarnessEpisodeLedgerService(store=FakeEpisodeLedgerStore())

    with pytest.raises(ValueError, match="exceeds 32768 bytes"):
        service.upsert_result(
            RunHarnessResult(
                run_id="run-1",
                episode_id="episode-1",
                harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
                status=RunHarnessStatus.SUCCEEDED,
                metadata={"large": "x" * (33 * 1024)},
            )
        )


def test_artifact_refs_are_allowed_but_inline_payloads_are_rejected() -> None:
    service = RunHarnessEpisodeLedgerService(store=FakeEpisodeLedgerStore())

    assert (
        service.upsert_result(
            RunHarnessResult(
                run_id="run-1",
                episode_id="episode-1",
                harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
                status=RunHarnessStatus.SUCCEEDED,
                output_artifact_refs=["artifact:result-json"],
            )
        ).output_artifact_refs
        == ["artifact:result-json"]
    )

    with pytest.raises(ValueError, match="artifact payload field is not allowed"):
        service.append_event(
            "episode-1",
            "tool.completed",
            RunHarnessStatus.SUCCEEDED.value,
            {"metadata": {"artifact_blob": {"payload": "inline-result"}}},
        )
