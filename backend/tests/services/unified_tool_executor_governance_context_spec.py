from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.services.unified_tool_executor import UnifiedToolExecutor
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
    build_verified_tool_execution_context,
)
from backend.app.services.workspace_capability_admission.contracts import (
    RootAdmissionResult,
    RootPrincipalEvidence,
)
from backend.app.services.workspace_capability_admission.execution_snapshot import (
    build_execution_snapshot,
)


def _context(selector_key: str = "default.echo"):
    return VerifiedToolExecutionContext(
        snapshot_hash="1" * 64,
        workspace_id="workspace-a",
        actor_user_id="owner-a",
        allowed_workspace_ids=("workspace-a",),
        allowed_group_ids=("group-a",),
        workspace_owner_user_id="owner-a",
        active_group_id="group-a",
        group_owner_user_id="owner-a",
        root_execution_id="root-a",
        trace_id="trace-a",
        source_entry="local",
        selector_lineage=(selector_key,),
        context_sha256="2" * 64,
    )


class _CaptureTool:
    description = "Capture trusted execution context"
    metadata = SimpleNamespace(source_type="test")

    def __init__(self):
        self.calls = []

    async def safe_execute(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            success=True,
            result={"ok": True},
            error=None,
            metadata={},
        )


@pytest.mark.asyncio
async def test_executor_uses_only_controller_context_and_strips_spoofed_keys():
    tool = _CaptureTool()
    executor = UnifiedToolExecutor(
        mcp_manager=object(),
        tool_resolver=object(),
    )

    async def fake_get_tool(tool_type, tool_name):
        assert (tool_type, tool_name) == ("builtin", "echo")
        return tool

    executor._get_tool = fake_get_tool
    context = _context()
    result = await executor.execute_tool(
        "default.echo",
        {
            "text": "hello",
            "governance_context": {"actor_user_id": "attacker"},
            "workspace_owner_user_id": "attacker",
            "allowed_workspace_ids": ["foreign"],
        },
        governance_context=context,
    )

    assert result.success is True
    assert tool.calls == [
        {
            "text": "hello",
            "governance_context": context,
        }
    ]
    assert result.metadata["ignored_controller_argument_keys"] == [
        "allowed_workspace_ids",
        "governance_context",
        "workspace_owner_user_id",
    ]


@pytest.mark.asyncio
async def test_executor_rejects_context_reuse_for_another_selector():
    tool = _CaptureTool()
    executor = UnifiedToolExecutor(
        mcp_manager=object(),
        tool_resolver=object(),
    )

    async def fake_get_tool(tool_type, tool_name):
        return tool

    executor._get_tool = fake_get_tool
    result = await executor.execute_tool(
        "default.other",
        {},
        governance_context=_context("default.echo"),
    )

    assert result.success is False
    assert "governance_context_selector_mismatch" in result.error
    assert tool.calls == []


def test_root_context_factory_requires_matching_owner_evidence():
    snapshot = build_execution_snapshot(
        {
            "source_runtime_id": "runtime-a",
            "workspace_id": "workspace-a",
            "active_group_id": None,
            "topology_revision": None,
            "topology_snapshot_id": None,
            "topology_snapshot_hash": None,
            "wpcs_hash": "3" * 64,
            "catalog_hash": "4" * 64,
            "admission_mode": "legacy_unmanaged",
            "pcs_id": None,
            "pcs_version": None,
            "product_surface_id": "mcp-gateway",
            "selector_kind": "tool",
            "selector_key": "default.echo",
            "operation_type": "read",
            "entry": "local",
            "execution_backend": "local",
            "deployment_mode": "unmanaged_local",
            "deployment_state_revision": 0,
            "deployment_envelope_revision": None,
            "dce_hash": None,
            "availability": "not_configured",
            "diagnostics": [],
            "external_decision_id": None,
            "external_decision_issuer": None,
            "external_decision_expires_at": None,
            "provider_token_id": None,
            "trace_id": "trace-a",
            "root_execution_id": "root-a",
            "admitted_at": datetime(
                2026,
                7,
                27,
                tzinfo=timezone.utc,
            ),
        }
    )
    evidence = RootPrincipalEvidence(
        workspace_id="workspace-a",
        actor_user_id="owner-a",
        allowed_workspace_ids=("workspace-a",),
        allowed_group_ids=(),
        workspace_owner_user_id="owner-a",
        group_owner_user_id=None,
    )
    context = build_verified_tool_execution_context(
        RootAdmissionResult(
            snapshot=snapshot,
            principal_evidence=evidence,
        )
    )
    assert context.selector_lineage == ("default.echo",)
    assert len(context.context_sha256) == 64

    with pytest.raises(
        ValueError,
        match="workspace_owner_evidence_required",
    ):
        build_verified_tool_execution_context(
            RootAdmissionResult(
                snapshot=snapshot,
                principal_evidence=RootPrincipalEvidence(
                    **{
                        **evidence.__dict__,
                        "workspace_owner_user_id": None,
                    }
                ),
            )
        )
