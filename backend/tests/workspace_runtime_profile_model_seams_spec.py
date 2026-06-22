from backend.app.models.workspace_runtime_profile import (
    CodingStyle,
    ConfirmationFormat,
    RationaleLevel,
    WorkspaceRuntimeProfile,
    WritingStyle,
)


def test_runtime_profile_facade_exports_enum_values():
    assert RationaleLevel.BRIEF.value == "brief"
    assert CodingStyle.PATCH_FIRST.value == "patch_first"
    assert WritingStyle.STRUCTURE_FIRST.value == "structure_first"
    assert ConfirmationFormat.LIST_CHANGES.value == "list_changes"


def test_runtime_profile_defaults_stay_publicly_available():
    profile = WorkspaceRuntimeProfile()

    assert profile.default_mode.value == "qa"
    assert profile.schema_version == "2.0"
    assert profile.resolved_mode.value == "qa"
    assert profile.loop_budget.max_iterations == 10
    assert profile.loop_budget.max_turns == 20
    assert profile.loop_budget.max_steps == 50


def test_runtime_profile_phase2_fields_are_initialized():
    profile = WorkspaceRuntimeProfile(schema_version="1.0")

    upgraded = profile.ensure_phase2_fields()

    assert upgraded is profile
    assert upgraded.schema_version == "2.0"
    assert upgraded.loop_budget.max_iterations == 10
    assert upgraded.stop_conditions.max_retries == 3
    assert upgraded.quality_gates.require_changelist is True
    assert upgraded.shared_state_policy.memory_event_types == [
        "intents",
        "artifacts",
        "decisions",
    ]
    assert upgraded.recovery_policy.retry_on_failure is True
