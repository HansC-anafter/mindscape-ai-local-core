"""Non-user-writable execution authority passed between trusted controllers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from backend.app.core.ports.artifact_disclosure import (
    ArtifactDisclosureAuthority,
)
from backend.app.services.workspace_capability_admission.contracts import (
    RootAdmissionResult,
)


@dataclass(frozen=True)
class VerifiedToolExecutionContext:
    """Transient authority whose fields never come from tool arguments."""

    snapshot_hash: str
    workspace_id: str
    actor_user_id: str
    allowed_workspace_ids: tuple[str, ...]
    allowed_group_ids: tuple[str, ...]
    workspace_owner_user_id: str
    active_group_id: str | None
    group_owner_user_id: str | None
    root_execution_id: str
    trace_id: str
    source_entry: str
    selector_lineage: tuple[str, ...]
    context_sha256: str

    def verify_selector(self, selector_key: str) -> None:
        normalized = selector_key.strip()
        if (
            not normalized
            or not self.selector_lineage
            or self.selector_lineage[-1] != normalized
        ):
            raise ValueError("governance_context_selector_mismatch")

    def for_child(self, selector_key: str) -> "VerifiedToolExecutionContext":
        normalized = selector_key.strip()
        if not normalized:
            raise ValueError("child_selector_key_required")
        lineage = (*self.selector_lineage, normalized)
        return replace(
            self,
            selector_lineage=lineage,
            context_sha256=_context_digest(
                snapshot_hash=self.snapshot_hash,
                workspace_id=self.workspace_id,
                actor_user_id=self.actor_user_id,
                allowed_workspace_ids=self.allowed_workspace_ids,
                allowed_group_ids=self.allowed_group_ids,
                workspace_owner_user_id=self.workspace_owner_user_id,
                active_group_id=self.active_group_id,
                group_owner_user_id=self.group_owner_user_id,
                root_execution_id=self.root_execution_id,
                trace_id=self.trace_id,
                source_entry=self.source_entry,
                selector_lineage=lineage,
            ),
        )

    def to_artifact_disclosure_authority(
        self,
    ) -> ArtifactDisclosureAuthority:
        return ArtifactDisclosureAuthority(
            workspace_id=self.workspace_id,
            actor_user_id=self.actor_user_id,
            allowed_workspace_ids=self.allowed_workspace_ids,
            allowed_group_ids=self.allowed_group_ids,
            workspace_owner_user_id=self.workspace_owner_user_id,
            active_group_id=self.active_group_id,
            group_owner_user_id=self.group_owner_user_id,
            root_execution_id=self.root_execution_id,
            trace_id=self.trace_id,
            source_entry=self.source_entry,
            context_sha256=self.context_sha256,
        )


def build_verified_tool_execution_context(
    result: RootAdmissionResult,
) -> VerifiedToolExecutionContext:
    """Build the only production context from root-admission evidence."""

    evidence = result.principal_evidence
    if evidence is None:
        raise ValueError("verified_principal_evidence_required")
    if result.snapshot.workspace_id != evidence.workspace_id:
        raise ValueError("verified_principal_workspace_mismatch")
    if not evidence.workspace_owner_user_id:
        raise ValueError("workspace_owner_evidence_required")
    lineage = (result.snapshot.selector_key,)
    fields = {
        "snapshot_hash": result.snapshot.snapshot_hash,
        "workspace_id": evidence.workspace_id,
        "actor_user_id": evidence.actor_user_id,
        "allowed_workspace_ids": tuple(
            sorted(set(evidence.allowed_workspace_ids))
        ),
        "allowed_group_ids": tuple(sorted(set(evidence.allowed_group_ids))),
        "workspace_owner_user_id": evidence.workspace_owner_user_id,
        "active_group_id": result.snapshot.active_group_id,
        "group_owner_user_id": evidence.group_owner_user_id,
        "root_execution_id": result.snapshot.root_execution_id,
        "trace_id": result.snapshot.trace_id,
        "source_entry": result.snapshot.entry,
        "selector_lineage": lineage,
    }
    return VerifiedToolExecutionContext(
        **fields,
        context_sha256=_context_digest(**fields),
    )


def _context_digest(**fields) -> str:
    payload = json.dumps(
        fields,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "VerifiedToolExecutionContext",
    "build_verified_tool_execution_context",
]
