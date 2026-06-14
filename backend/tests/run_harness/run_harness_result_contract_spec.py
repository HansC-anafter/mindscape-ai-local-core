from pydantic import ValidationError
import pytest

from backend.app.models.run_harness import (
    RunHarnessKind,
    RunHarnessResult,
    RunHarnessStatus,
)


def test_waiting_result_requires_wait_state() -> None:
    with pytest.raises(ValidationError):
        RunHarnessResult(
            run_id="run-1",
            episode_id="episode-1",
            harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
            status=RunHarnessStatus.WAITING,
        )

