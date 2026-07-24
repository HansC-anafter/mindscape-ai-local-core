"""New-root admission adapter for playbook reruns."""

from __future__ import annotations

from typing import Any

from backend.app.dependencies.auth import AuthContext
from backend.app.services.playbook_execution_admission import (
    admit_playbook_root,
)
from backend.app.services.workspace_capability_admission import (
    RootAdmissionResult,
)


async def admit_playbook_rerun(
    *,
    workspace_id: str | None,
    playbook_code: str,
    execution_backend: str,
    original_execution_context: dict[str, Any],
    merged_inputs: dict[str, Any],
    remote_ingress_verified: bool,
    auth: AuthContext,
    new_execution_id: str,
) -> RootAdmissionResult | None:
    if not workspace_id:
        return None
    original = original_execution_context.get(
        "execution_admission_snapshot"
    )
    original_snapshot = original if isinstance(original, dict) else {}
    result = await admit_playbook_root(
        workspace_id=workspace_id,
        product_surface_id=(
            original_snapshot.get("product_surface_id")
            or merged_inputs.get("product_surface_id")
        ),
        active_group_id=original_snapshot.get("active_group_id"),
        observed_topology_revision=original_snapshot.get(
            "topology_revision"
        ),
        playbook_code=playbook_code,
        execution_backend=execution_backend,
        remote_ingress_verified=remote_ingress_verified,
        auth=auth,
        trace_id=new_execution_id,
        root_execution_id=new_execution_id,
    )
    return result
