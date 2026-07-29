"""Governance contexts bind group agent roles from server provenance."""

from types import SimpleNamespace

import pytest

from backend.app.services.knowledge_authorization.access_context_factory import (
    RetrievalAccessContextFactory,
    RetrievalScopeDenied,
)


def _governance(**updates):
    values = {
        "actor_user_id": "owner-1",
        "workspace_owner_user_id": "owner-1",
        "group_owner_user_id": "owner-1",
        "allowed_workspace_ids": ("workspace-1",),
        "allowed_group_ids": ("group-1",),
        "snapshot_hash": "a" * 64,
        "agent_role": "dispatch",
        "agent_policy_revision": "b" * 64,
        "topology_snapshot_id": "topology-1",
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_group_governance_context_projects_exact_agent_mask() -> None:
    context = RetrievalAccessContextFactory().build_from_governance(
        _governance(),
        requested_workspace_id="workspace-1",
        requested_group_id="group-1",
    )

    assert context.agent_mask is not None
    assert context.agent_mask.role == "dispatch"
    assert context.agent_mask.policy_revision == "b" * 64
    assert context.agent_mask.topology_snapshot_id == "topology-1"


@pytest.mark.parametrize(
    "missing",
    ("agent_role", "agent_policy_revision", "topology_snapshot_id"),
)
def test_group_governance_context_rejects_partial_agent_mask(
    missing: str,
) -> None:
    with pytest.raises(
        RetrievalScopeDenied,
        match="knowledge_agent_execution_mask_missing",
    ):
        RetrievalAccessContextFactory().build_from_governance(
            _governance(**{missing: None}),
            requested_workspace_id="workspace-1",
            requested_group_id="group-1",
        )


def test_workspace_context_rejects_group_agent_mask() -> None:
    with pytest.raises(
        RetrievalScopeDenied,
        match="knowledge_agent_execution_mask_without_group",
    ):
        RetrievalAccessContextFactory().build_from_governance(
            _governance(),
            requested_workspace_id="workspace-1",
        )
