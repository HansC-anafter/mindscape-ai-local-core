from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.models.phase_attempt import PhaseAttempt
from backend.app.models.request_contract import (
    DataOperationContract,
    DataOperationEffect,
    RequestContract,
)
from backend.app.models.task_ir import PhaseIR, TaskIR
from backend.app.services.orchestration.dispatch_orchestrator import DispatchOrchestrator
from backend.app.services.orchestration.meeting.planner_contract_execution.binding_service import (
    PlannerContractBindingService,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)


class TempManifestRegistry(PlannerContractManifestRegistry):
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path

    def capability_manifest_paths(self, pack_id: str) -> list[Path]:
        return [self.manifest_path]


def _write_manifest(path: Path) -> None:
    path.write_text(
        """
code: ig
tools:
  - name: ig_query_references
    code: ig_query_references
    planner_contract:
      exposed: true
      resource_kind: reference
      effect: read
      workspace_scoped: true
      input_schema: capabilities.ig.tools.schemas:QueryReferencesInput
      output_schema: capabilities.ig.tools.schemas:QueryReferencesOutput
      idempotency: none
      audit_fields:
        - workspace_id
        - query
  - name: ig_create_creative_space
    code: ig_create_creative_space
    planner_contract:
      exposed: true
      resource_kind: creative_space
      effect: write
      workspace_scoped: true
      input_schema: capabilities.ig.tools.schemas:CreateCreativeSpaceInput
      output_schema: capabilities.ig.tools.schemas:CreateCreativeSpaceOutput
      idempotency: idempotency_key
      audit_fields:
        - workspace_id
        - title
""",
        encoding="utf-8",
    )


def _task_ir(phases: list[PhaseIR]) -> TaskIR:
    return TaskIR(
        task_id="task-ir-1",
        intent_instance_id="intent-1",
        workspace_id="ws_demo",
        actor_id="user-1",
        phases=phases,
    )


def test_binds_phase_tool_to_installed_planner_contract(tmp_path):
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(manifest_path)
    phase = PhaseIR(
        id="phase-read",
        name="Query references",
        tool_name="ig_query_references",
        input_params={"query": "yoga"},
    )

    report = PlannerContractBindingService(
        TempManifestRegistry(manifest_path)
    ).bind_task_ir(
        task_ir=_task_ir([phase]),
        request_contract=RequestContract(
            data_operations=[
                DataOperationContract(
                    id="OP1",
                    resource_kind="reference",
                    effect=DataOperationEffect.READ,
                    tool_name="ig_query_references",
                )
            ]
        ),
        session_metadata={"active_capability_code": "ig"},
    )

    assert report["status"] == "bound"
    assert phase.tool_name == "ig.ig_query_references"
    assert phase.planner_contract_binding is not None
    assert phase.planner_contract_binding.resource_kind == "reference"
    assert phase.planner_contract_binding.approval_required is False


@pytest.mark.asyncio
async def test_dispatch_tool_propagates_planner_contract_binding(tmp_path, monkeypatch):
    import backend.app as backend_app
    import sys

    sys.modules.setdefault("app", backend_app)
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(manifest_path)
    phase = PhaseIR(
        id="phase-write",
        name="Create creative space",
        tool_name="ig_create_creative_space",
        input_params={"title": "Yoga"},
    )
    PlannerContractBindingService(TempManifestRegistry(manifest_path)).bind_task_ir(
        task_ir=_task_ir([phase]),
        request_contract=RequestContract(
            data_operations=[
                DataOperationContract(
                    id="OP2",
                    resource_kind="creative_space",
                    effect=DataOperationEffect.WRITE,
                    tool_name="ig_create_creative_space",
                )
            ]
        ),
        session_metadata={"active_capability_code": "ig"},
    )

    async def _route_context(_workspace_id: str):
        return {"workspace_id": "ws_demo"}

    monkeypatch.setattr(
        "backend.app.services.executor_route_context.load_executor_route_context",
        _route_context,
    )

    class FakeTasksStore:
        def __init__(self):
            self.created = None

        def create_task(self, task):
            self.created = task

    store = FakeTasksStore()
    orchestrator = DispatchOrchestrator(
        tasks_store=store,
        session=SimpleNamespace(id="meeting-1", workspace_id="ws_demo", metadata={}),
        profile_id="user-1",
        project_id="proj-1",
    )
    result = await orchestrator._dispatch_tool(
        phase,
        {},
        "ws_demo",
        PhaseAttempt(task_ir_id="task-ir-1", phase_id=phase.id),
        {"ir": "provenance"},
    )

    assert result["tool_name"] == "ig.ig_create_creative_space"
    assert result["planner_contract_binding"]["approval_required"] is True
    assert store.created.params["planner_contract_binding"]["resource_kind"] == "creative_space"
    assert store.created.execution_context["planner_contract_binding"]["effect"] == "write"
