"""Root-or-child convergence for PlaybookRunExecutor."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from backend.app.dependencies.auth import AuthContext
from backend.app.services.playbook_execution_admission import (
    admit_playbook_root,
)
from backend.app.services.workspace_capability_admission.child_snapshot_verifier import (
    verify_child_snapshot,
)
from backend.app.services.workspace_capability_admission.contracts import (
    ExecutionAdmissionSnapshot,
)


async def prepare_playbook_admission(
    *,
    playbook_code: str,
    profile_id: str,
    workspace_id: str | None,
    inputs: dict[str, Any] | None,
) -> tuple[dict[str, Any], ExecutionAdmissionSnapshot | None]:
    normalized = dict(inputs or {})
    if not workspace_id:
        return normalized, None
    existing = normalized.get("execution_admission_snapshot")
    if isinstance(existing, dict):
        parsed = ExecutionAdmissionSnapshot.model_validate(existing)
        root_execution_id = str(
            normalized.get("execution_id")
            or parsed.root_execution_id
        )
        normalized.setdefault("execution_id", root_execution_id)
        return normalized, verify_child_snapshot(
            parsed,
            expected_workspace_id=workspace_id,
            expected_root_execution_id=root_execution_id,
        )

    root_execution_id = str(
        normalized.get("execution_id") or f"playbook-{uuid4().hex}"
    )
    active_group_id = normalized.get("active_group_id")
    topology_revision = normalized.get("observed_topology_revision")
    result = await admit_playbook_root(
        workspace_id=workspace_id,
        product_surface_id=normalized.get("product_surface_id"),
        active_group_id=(
            active_group_id
            if isinstance(active_group_id, str)
            else None
        ),
        observed_topology_revision=(
            topology_revision
            if isinstance(topology_revision, int)
            else None
        ),
        playbook_code=playbook_code,
        execution_backend=str(
            normalized.get("execution_backend") or "in_process"
        ),
        remote_ingress_verified=False,
        auth=AuthContext(
            user_id=profile_id,
            tenant_id="local-service",
            workspace_ids=[workspace_id],
            group_ids=(
                [active_group_id]
                if isinstance(active_group_id, str)
                else []
            ),
        ),
        trace_id=str(normalized.get("trace_id") or root_execution_id),
        root_execution_id=root_execution_id,
    )
    normalized["execution_admission_snapshot"] = (
        result.snapshot.model_dump(mode="json")
    )
    normalized.setdefault("execution_id", root_execution_id)
    return normalized, result.snapshot
