"""Execution envelope construction for host runtime turns."""

from __future__ import annotations

from typing import Any

from .governance_snapshot import build_governance_refs, validate_governance_refs
from .models import HostRuntimeExecutionEnvelope, HostRuntimeSession, HostRuntimeTurn


class GovernanceSnapshotError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("Host runtime governance snapshot is incomplete")
        self.errors = errors


def build_execution_envelope(
    *,
    session: HostRuntimeSession,
    turn: HostRuntimeTurn,
    prompt: str,
    context_ref: dict[str, Any] | None = None,
    intent_ref: dict[str, Any] | None = None,
    lens_ref: dict[str, Any] | None = None,
    policy_ref: dict[str, Any] | None = None,
    artifact_ref: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> HostRuntimeExecutionEnvelope:
    refs = build_governance_refs(
        workspace_id=session.workspace_id,
        prompt=prompt,
        context_ref=context_ref,
        intent_ref=intent_ref,
        lens_ref=lens_ref,
        policy_ref=policy_ref,
        artifact_ref=artifact_ref,
    )
    errors = validate_governance_refs(refs)
    if errors:
        raise GovernanceSnapshotError(errors)

    return HostRuntimeExecutionEnvelope(
        execution_id=session.execution_id,
        workspace_id=session.workspace_id,
        session_id=session.id,
        turn_id=turn.id,
        actor_id=session.actor_id,
        trace_id=refs["governance_trace_ref"],
        runtime_surface=session.runtime_surface,
        runtime_id=session.runtime_id,
        prompt_hash=refs["prompt_hash"],
        compiled_prompt_hash=refs["compiled_prompt_hash"],
        intent_ref=refs["intent_ref"],
        lens_ref=refs["lens_ref"],
        policy_ref=refs["policy_ref"],
        context_ref=refs["context_ref"],
        artifact_ref=refs["artifact_ref"],
        governance_trace_ref=refs["governance_trace_ref"],
        metadata=metadata or {},
    )
