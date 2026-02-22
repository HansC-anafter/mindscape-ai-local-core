"""
Phase 0 P2 Rename Regression Tests

Validates that the P2 terminology renames are correctly applied:
  P2-a: preferred_agent -> executor_runtime
  P2-b: AgentRequest -> RuntimeExecRequest, AgentResponse -> RuntimeExecResponse
  P2-c: BaseAgentAdapter -> BaseRuntimeAdapter

Also verifies backward-compatibility aliases remain functional.
"""

import pytest


# ======================================================================
#  P2-b: RuntimeExecRequest / RuntimeExecResponse
# ======================================================================


class TestRuntimeExecRequestRename:
    """Verify RuntimeExecRequest class and its backward-compat alias."""

    def test_import_new_name(self):
        from backend.app.services.external_agents.core.base_adapter import (
            RuntimeExecRequest,
        )

        assert RuntimeExecRequest is not None

    def test_import_old_alias(self):
        from backend.app.services.external_agents.core.base_adapter import (
            AgentRequest,
        )

        assert AgentRequest is not None

    def test_alias_identity(self):
        from backend.app.services.external_agents.core.base_adapter import (
            AgentRequest,
            RuntimeExecRequest,
        )

        assert AgentRequest is RuntimeExecRequest

    def test_instantiation(self):
        from backend.app.services.external_agents.core.base_adapter import (
            RuntimeExecRequest,
        )

        req = RuntimeExecRequest(task="test", sandbox_path="/tmp/test")
        assert req.task == "test"
        assert req.sandbox_path == "/tmp/test"
        assert req.workspace_id is None

    def test_response_new_name(self):
        from backend.app.services.external_agents.core.base_adapter import (
            RuntimeExecResponse,
        )

        resp = RuntimeExecResponse(success=True, output="ok", duration_seconds=1.0)
        assert resp.success is True
        assert resp.output == "ok"

    def test_response_alias_identity(self):
        from backend.app.services.external_agents.core.base_adapter import (
            AgentResponse,
            RuntimeExecResponse,
        )

        assert AgentResponse is RuntimeExecResponse


# ======================================================================
#  P2-c: BaseRuntimeAdapter
# ======================================================================


class TestBaseRuntimeAdapterRename:
    """Verify BaseRuntimeAdapter class and its backward-compat alias."""

    def test_import_new_name(self):
        from backend.app.services.external_agents.core.base_adapter import (
            BaseRuntimeAdapter,
        )

        assert BaseRuntimeAdapter is not None

    def test_import_old_alias(self):
        from backend.app.services.external_agents.core.base_adapter import (
            BaseAgentAdapter,
        )

        assert BaseAgentAdapter is not None

    def test_alias_identity(self):
        from backend.app.services.external_agents.core.base_adapter import (
            BaseAgentAdapter,
            BaseRuntimeAdapter,
        )

        assert BaseAgentAdapter is BaseRuntimeAdapter

    def test_has_runtime_name_attr(self):
        from backend.app.services.external_agents.core.base_adapter import (
            BaseRuntimeAdapter,
        )

        assert hasattr(BaseRuntimeAdapter, "RUNTIME_NAME")
        assert hasattr(BaseRuntimeAdapter, "RUNTIME_VERSION")

    def test_has_get_runtime_info(self):
        from backend.app.services.external_agents.core.base_adapter import (
            BaseRuntimeAdapter,
        )

        assert hasattr(BaseRuntimeAdapter, "get_runtime_info")

    def test_has_compat_get_agent_info(self):
        from backend.app.services.external_agents.core.base_adapter import (
            BaseRuntimeAdapter,
        )

        assert hasattr(BaseRuntimeAdapter, "get_agent_info")


# ======================================================================
#  P2-c: PollingRuntimeAdapter alias
# ======================================================================


class TestPollingRuntimeAdapterRename:
    """Verify PollingRuntimeAdapter and its backward-compat alias."""

    def test_alias_identity(self):
        from backend.app.services.external_agents.core.polling_adapter import (
            PollingAgentAdapter,
            PollingRuntimeAdapter,
        )

        assert PollingAgentAdapter is PollingRuntimeAdapter

    def test_runtime_name_attr(self):
        from backend.app.services.external_agents.core.polling_adapter import (
            PollingRuntimeAdapter,
        )

        assert hasattr(PollingRuntimeAdapter, "RUNTIME_NAME")


# ======================================================================
#  P2-a: executor_runtime field on Workspace model
# ======================================================================


class TestExecutorRuntimeField:
    """Verify Workspace model uses executor_runtime (not preferred_agent)."""

    def test_workspace_has_executor_runtime(self):
        from backend.app.models.workspace.core import Workspace

        w = Workspace(id="test", title="test", owner_user_id="u1")
        assert hasattr(w, "executor_runtime")

    def test_workspace_executor_runtime_defaults_none(self):
        from backend.app.models.workspace.core import Workspace

        w = Workspace(id="test", title="test", owner_user_id="u1")
        assert w.executor_runtime is None

    def test_workspace_executor_runtime_settable(self):
        from backend.app.models.workspace.core import Workspace

        w = Workspace(
            id="test",
            title="test",
            owner_user_id="u1",
            executor_runtime="gemini_cli",
        )
        assert w.executor_runtime == "gemini_cli"

    def test_create_request_has_executor_runtime(self):
        from backend.app.models.workspace.core import CreateWorkspaceRequest

        fields = CreateWorkspaceRequest.model_fields
        assert "executor_runtime" in fields

    def test_update_request_has_executor_runtime(self):
        from backend.app.models.workspace.core import UpdateWorkspaceRequest

        fields = UpdateWorkspaceRequest.model_fields
        assert "executor_runtime" in fields


# ======================================================================
#  Package-level re-exports
# ======================================================================


class TestPackageLevelExports:
    """Verify that __init__.py re-exports both old and new names."""

    def test_core_init_exports_new(self):
        from backend.app.services.external_agents.core import (
            RuntimeExecRequest,
            RuntimeExecResponse,
            BaseRuntimeAdapter,
        )

        assert RuntimeExecRequest is not None
        assert RuntimeExecResponse is not None
        assert BaseRuntimeAdapter is not None

    def test_core_init_exports_old(self):
        from backend.app.services.external_agents.core import (
            AgentRequest,
            AgentResponse,
            BaseAgentAdapter,
        )

        assert AgentRequest is not None
        assert AgentResponse is not None
        assert BaseAgentAdapter is not None

    def test_top_init_exports_new(self):
        from backend.app.services.external_agents import (
            RuntimeExecRequest,
            BaseRuntimeAdapter,
        )

        assert RuntimeExecRequest is not None
        assert BaseRuntimeAdapter is not None
