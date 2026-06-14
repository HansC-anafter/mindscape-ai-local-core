from backend.app.models.run_harness import RunHarnessKind, SideEffectClass
from backend.app.services.run_harness.envelope_builder import RunIntentEnvelopeBuilder


class Request:
    action_params = {
        "tool_ref": "tool:publish",
        "requested_side_effects": ["external_write"],
        "workspace_roots": ["/workspace"],
    }


def test_pipeline_envelope_normalizes_explicit_tool_request() -> None:
    envelope = RunIntentEnvelopeBuilder().build_for_pipeline(
        decision_id="decision-1",
        workspace_id="workspace-1",
        profile_id="profile-1",
        intent_text="Publish the approved artifact.",
        request=Request(),
    )

    assert envelope.preferred_harness == RunHarnessKind.DETERMINISTIC_TOOL
    assert envelope.requested_side_effects == [SideEffectClass.EXTERNAL_WRITE]
    assert envelope.workspace_roots == ["/workspace"]
    assert len(envelope.idempotency_key) == 64

