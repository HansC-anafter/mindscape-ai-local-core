from backend.app.models.run_harness import RunHarnessKind
from backend.app.services.run_harness.envelope_builder import RunIntentEnvelopeBuilder
from backend.app.services.run_harness.router import RunHarnessRouter


class Request:
    action_params = {"workflow_code": "workflow-1"}


def test_execution_mode_preview_selects_explicit_workflow() -> None:
    envelope = RunIntentEnvelopeBuilder().build_for_pipeline(
        decision_id="decision-1",
        workspace_id="workspace-1",
        profile_id="profile-1",
        intent_text="Run workflow",
        request=Request(),
    )
    selection = RunHarnessRouter().select(envelope)
    assert selection.harness_kind == RunHarnessKind.DURABLE_WORKFLOW
    assert selection.requires_durability is True

