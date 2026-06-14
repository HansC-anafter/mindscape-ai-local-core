from backend.app.models.run_harness import RunHarnessKind, SideEffectClass
from backend.app.services.run_harness.selection_builder import (
    RunHarnessSelectionBuilder,
)


def test_selection_marks_write_tool_as_approval_and_sandbox_required(run_intent) -> None:
    intent = run_intent.model_copy(
        update={"requested_side_effects": [SideEffectClass.EXTERNAL_WRITE]}
    )
    selection = RunHarnessSelectionBuilder().build(
        intent,
        RunHarnessKind.DETERMINISTIC_TOOL,
        ["test"],
    )
    assert selection.requires_approval is True
    assert selection.requires_sandbox is True
    assert selection.requires_durability is False

