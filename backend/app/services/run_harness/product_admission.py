"""Run Harness root admission and immutable snapshot projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from backend.app.dependencies.auth import AuthContext
from backend.app.models.run_harness_tool_execution import (
    RunHarnessToolExecutionRequest,
)
from backend.app.models.run_harness_workflow_execution import (
    RunHarnessWorkflowExecutionRequest,
)
from backend.app.services.workspace_capability_admission import (
    RootAdmissionRequest,
    WorkspaceCapabilityAdmissionFacade,
)
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
    build_verified_tool_execution_context,
)


RunHarnessRequest = TypeVar(
    "RunHarnessRequest",
    RunHarnessToolExecutionRequest,
    RunHarnessWorkflowExecutionRequest,
)
_facade = WorkspaceCapabilityAdmissionFacade()


@dataclass(frozen=True)
class AdmittedRunHarnessRoot:
    request: RunHarnessToolExecutionRequest | RunHarnessWorkflowExecutionRequest
    external_decision: Any | None
    governance_context: VerifiedToolExecutionContext | None


def _tool_operation(
    request: RunHarnessToolExecutionRequest,
) -> Literal["read", "modify"]:
    return "read" if request.side_effect.value in {"none", "readonly"} else "modify"


async def admit_run_harness_root(
    request: RunHarnessRequest,
    *,
    auth: AuthContext,
    remote_ingress_verified: bool,
    facade: WorkspaceCapabilityAdmissionFacade | None = None,
) -> AdmittedRunHarnessRoot:
    if isinstance(request, RunHarnessToolExecutionRequest):
        workspace_id = request.envelope.workspace_id
        selector_kind = "tool"
        selector_key = request.tool_ref
        operation_type = _tool_operation(request)
        execution_backend = request.execution_backend
    else:
        workspace_id = request.workspace_id
        selector_kind = "playbook"
        selector_key = request.playbook_code
        operation_type = "generate"
        execution_backend = request.execution_backend

    result = await (facade or _facade).admit_root(
        RootAdmissionRequest(
            workspace_id=workspace_id,
            explicit_active_group_id=request.active_group_id,
            observed_topology_revision=request.observed_topology_revision,
            product_surface_id=request.product_surface_id,
            selector_kind=selector_kind,
            selector_key=selector_key,
            operation_type=operation_type,
            entry="remote" if remote_ingress_verified else "local",
            remote_ingress_verified=remote_ingress_verified,
            execution_backend=(
                "external_provider"
                if execution_backend in {"remote", "external_provider"}
                else "local"
            ),
            actor_user_id=auth.user_id,
            allowed_workspace_ids=auth.workspace_ids,
            allowed_group_ids=auth.group_ids,
            trace_id=request.envelope.trace_id,
            root_execution_id=request.run_id,
        )
    )
    snapshot_payload = result.snapshot.model_dump(mode="json")
    capability_ref = request.envelope.capability_snapshot_ref.model_copy(
        update={
            "ref": f"execution-admission:{result.snapshot.snapshot_hash}",
            "version": result.snapshot.schema_version,
            "capability_codes": [selector_key],
            "digest": result.snapshot.snapshot_hash,
            "execution_admission_snapshot": snapshot_payload,
        }
    )
    envelope = request.envelope.model_copy(
        update={"capability_snapshot_ref": capability_ref}
    )
    return AdmittedRunHarnessRoot(
        request=request.model_copy(update={"envelope": envelope}),
        external_decision=result.external_decision,
        governance_context=(
            build_verified_tool_execution_context(result)
            if isinstance(request, RunHarnessToolExecutionRequest)
            else None
        ),
    )
