from backend.app.models.task_ir import (
    ArtifactReference,
    ArtifactType,
    CheckpointSnapshot,
    ExecutionEngine,
    ExecutionMetadata,
    GovernanceContext,
    HandoffEvent,
    PhaseIR,
    PhaseStatus,
    TaskIR,
    TaskIRUpdate,
    TaskStatus,
)


def _task() -> TaskIR:
    return TaskIR(
        task_id="task-1",
        intent_instance_id="intent-1",
        workspace_id="workspace-1",
        actor_id="actor-1",
        phases=[
            PhaseIR(id="phase-1", name="Plan"),
            PhaseIR(id="phase-2", name="Write", depends_on=["phase-1"]),
        ],
    )


def test_public_facade_exports_core_names():
    assert TaskStatus.PENDING.value == "pending"
    assert PhaseStatus.SKIPPED.value == "skipped"
    assert ExecutionEngine.PLAYBOOK.value == "playbook"
    assert ArtifactType.APPLICATION_JSON.value == "application/json"
    assert CheckpointSnapshot


def test_task_phase_dependency_and_artifact_helpers():
    task = _task()
    artifact = ArtifactReference(
        id="artifact-1",
        type=ArtifactType.TEXT_MARKDOWN.value,
        source="playbook:test",
        uri="file:///tmp/artifact.md",
    )

    task.add_artifact(artifact)

    assert task.get_artifact("artifact-1") is artifact
    assert task.can_start_phase("phase-2") is False
    assert [phase.id for phase in task.get_next_executable_phases()] == ["phase-1"]
    assert task.update_phase_status("phase-1", PhaseStatus.COMPLETED.value) is True
    assert task.can_start_phase("phase-2") is True
    assert [phase.id for phase in task.get_completed_phases()] == ["phase-1"]
    assert task.update_phase_status("missing", PhaseStatus.FAILED.value) is False


def test_lower_to_actuation_plan_preserves_existing_defaults():
    task = _task()

    result = task.lower_to_actuation_plan(
        default_engine="playbook:generic",
        default_gate="human-review",
    )

    assert result is task
    assert task.phases[0].preferred_engine == "playbook:generic"
    assert task.phases[0].gate == "human-review"
    assert task.phases[0].checkpoint_label == "pre_phase-1"
    assert task.phases[1].checkpoint_label == "pre_phase-2"


def test_checkpoint_roundtrip_restores_task_ir_state():
    task = _task().lower_to_actuation_plan(default_gate="gate-1")

    checkpoint = task.create_checkpoint("phase-1")
    restored = TaskIR.rollback_to_checkpoint(checkpoint)

    assert checkpoint.task_id == "task-1"
    assert checkpoint.phase_id == "phase-1"
    assert checkpoint.label == "pre_phase-1"
    assert restored.task_id == task.task_id
    assert restored.phases[0].checkpoint_label == "pre_phase-1"


def test_execution_metadata_governance_serialization():
    metadata = ExecutionMetadata()
    metadata.set_intent_context(intent_id="intent-1", intent_instance_id="instance-1")
    metadata.set_execution_context(playbook_code="demo", playbook_execution_id="exec-1")
    metadata.cloud = {"tenant_id": "tenant-1", "cloud_workspace_id": "cloud-1"}
    metadata.set_governance(GovernanceContext(goals=["ship"], handoff_id="handoff-1"))

    governance = metadata.get_governance()

    assert metadata.get_intent_id() == "intent-1"
    assert metadata.get_intent_instance_id() == "instance-1"
    assert metadata.get_playbook_code() == "demo"
    assert metadata.get_playbook_execution_id() == "exec-1"
    assert metadata.get_tenant_id() == "tenant-1"
    assert metadata.get_cloud_workspace_id() == "cloud-1"
    assert governance.goals == ["ship"]
    assert governance.handoff_id == "handoff-1"


def test_update_and_handoff_models_remain_available():
    task = _task()
    empty_update = TaskIRUpdate()
    non_empty_update = TaskIRUpdate(status_update=TaskStatus.RUNNING.value)

    event = HandoffEvent(
        event_type="handoff.to_skill",
        from_engine=ExecutionEngine.PLAYBOOK.value,
        from_execution_id="exec-1",
        from_phase_id="phase-1",
        to_engine=ExecutionEngine.SKILL.value,
        task_ir=task,
        input_artifacts=["artifact-1"],
        workspace_id="workspace-1",
    )

    assert empty_update.is_empty() is True
    assert non_empty_update.is_empty() is False
    assert event.task_ir is task
    assert event.input_artifacts == ["artifact-1"]
