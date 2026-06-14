import pytest

from backend.app.models.run_harness import (
    RunHarnessStatus,
    SideEffectClass,
    ToolAdmissionPolicy,
)
from backend.app.services.run_harness.tool_adapter import (
    DeterministicToolHarnessAdapter,
)


@pytest.mark.asyncio
async def test_tool_adapter_executes_after_admission() -> None:
    result = await DeterministicToolHarnessAdapter().execute(
        run_id="run-1",
        episode_id="episode-1",
        tool_ref="tool-1",
        arguments={"value": 1},
        side_effect=SideEffectClass.READONLY,
        policy=ToolAdmissionPolicy(policy_ref="policy-1"),
        executor=lambda _tool, _args: {"artifact_refs": ["artifact-1"]},
    )
    assert result.status == RunHarnessStatus.SUCCEEDED
    assert result.output_artifact_refs == ["artifact-1"]

