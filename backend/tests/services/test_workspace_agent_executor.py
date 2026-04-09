from types import SimpleNamespace
import time

import pytest

from backend.app.services.external_agents.core.base_adapter import RuntimeExecResponse
from backend.app.services.workspace_agent_executor import WorkspaceAgentExecutor


class _DummyAdapter:
    def __init__(self):
        self.request = None

    async def execute(self, request):
        self.request = request
        return RuntimeExecResponse(
            success=True,
            output="ok",
            duration_seconds=0.1,
        )


class _DummyRegistry:
    def __init__(self, adapter):
        self._adapter = adapter

    def get_adapter(self, agent_id):
        return self._adapter


class _DummyTrace:
    trace_id = "trace-1"

    def complete(self, **kwargs):
        self.completed = kwargs

    def fail(self, error):
        self.failed = error


class _DummyTraceService:
    def start_trace(self, **kwargs):
        self.started = kwargs
        return _DummyTrace()


@pytest.mark.asyncio
async def test_execute_promotes_governance_context_to_runtime_request():
    workspace = SimpleNamespace(
        id="ws-1",
        executor_runtime="gemini_cli",
        storage_base_path="/tmp/ws-1",
        sandbox_config={},
    )
    adapter = _DummyAdapter()
    executor = object.__new__(WorkspaceAgentExecutor)
    executor.workspace = workspace
    executor.registry = _DummyRegistry(adapter)
    executor.preflight = None
    executor.trace_service = _DummyTraceService()

    async def _fake_build_context():
        return {"brand_identity": {"tone": "calm"}}

    executor._build_context = _fake_build_context

    result = await executor.execute(
        task="test task",
        agent_id="gemini_cli",
        skip_preflight=True,
        context_overrides={
            "project_id": "project-123",
            "thread_id": "thread-456",
            "intent_id": "intent-789",
            "lens_id": "lens-abc",
            "auth_workspace_id": "auth-workspace-999",
            "source_workspace_id": "source-workspace-888",
            "conversation_context": "ctx",
            "target_client_id": "client-e2e-002",
        },
    )

    assert result.success is True
    assert adapter.request is not None
    assert adapter.request.project_id == "project-123"
    assert adapter.request.intent_id == "intent-789"
    assert adapter.request.lens_id == "lens-abc"
    assert adapter.request.auth_workspace_id == "auth-workspace-999"
    assert adapter.request.source_workspace_id == "source-workspace-888"
    assert adapter.request.agent_config["thread_id"] == "thread-456"
    assert adapter.request.agent_config["project_id"] == "project-123"
    assert adapter.request.agent_config["target_client_id"] == "client-e2e-002"


@pytest.mark.asyncio
async def test_build_context_loads_core_memory_with_store(monkeypatch):
    workspace = SimpleNamespace(
        id="ws-1",
        sandbox_config={},
        runtime_profile=None,
    )
    executor = object.__new__(WorkspaceAgentExecutor)
    executor.workspace = workspace

    class _DummyMemory:
        brand_identity = {"name": "Mindscape"}
        voice_and_tone = {"tone": "calm"}
        style_constraints = ["moody"]
        custom_instructions = "keep it concise"

    created = {}

    class _DummyMemoryService:
        def __init__(self, store):
            created["store"] = store

        async def get_core_memory(self, workspace_id):
            assert workspace_id == "ws-1"
            return _DummyMemory()

    monkeypatch.setattr(
        "backend.app.services.memory.workspace_core_memory.WorkspaceCoreMemoryService",
        _DummyMemoryService,
    )
    monkeypatch.setattr(
        "backend.app.services.mindscape_store.MindscapeStore",
        lambda: "store-instance",
    )

    context = await executor._build_context()

    assert created["store"] == "store-instance"
    assert context["brand_identity"] == {"name": "Mindscape"}
    assert context["voice_and_tone"] == {"tone": "calm"}
    assert context["style_constraints"] == ["moody"]
    assert context["custom_instructions"] == "keep it concise"


@pytest.mark.asyncio
async def test_build_context_injects_governance_packet(monkeypatch):
    workspace = SimpleNamespace(
        id="ws-1",
        owner_user_id="profile-1",
        sandbox_config={},
        runtime_profile=None,
    )
    executor = object.__new__(WorkspaceAgentExecutor)
    executor.workspace = workspace

    class _DummyReadModel:
        def __init__(self, store=None):
            self.store = store

        async def build_for_workspace(self, workspace):
            assert workspace.id == "ws-1"
            return {
                "governance_context": {"workspace_id": "ws-1", "profile_id": "profile-1"},
                "memory_packet": {"selection": {"memory_scope": "standard"}, "layers": {}},
            }

        def format_memory_packet_for_context(self, packet):
            return "Guiding knowledge:\n- prefer concise summaries"

    monkeypatch.setattr(
        "backend.app.services.governance.governance_context_read_model.GovernanceContextReadModel",
        _DummyReadModel,
    )
    monkeypatch.setattr(
        "backend.app.services.mindscape_store.MindscapeStore",
        lambda: "store-instance",
    )

    context = await executor._build_context()

    assert context["governance_context"]["workspace_id"] == "ws-1"
    assert context["memory_packet"]["selection"]["memory_scope"] == "standard"
    assert "Guiding knowledge" in context["memory_context_summary"]


@pytest.mark.asyncio
async def test_build_context_times_out_blocking_core_memory_lookup(monkeypatch):
    workspace = SimpleNamespace(
        id="ws-1",
        sandbox_config={},
        runtime_profile=None,
    )
    executor = object.__new__(WorkspaceAgentExecutor)
    executor.workspace = workspace
    executor.CORE_MEMORY_CONTEXT_TIMEOUT_S = 0.05

    class _BlockingMemoryService:
        def __init__(self, store):
            self.store = store

        async def get_core_memory(self, workspace_id):
            time.sleep(0.2)
            return None

    monkeypatch.setattr(
        "backend.app.services.memory.workspace_core_memory.WorkspaceCoreMemoryService",
        _BlockingMemoryService,
    )
    monkeypatch.setattr(
        "backend.app.services.mindscape_store.MindscapeStore",
        lambda: "store-instance",
    )

    context = await executor._build_context()

    assert "brand_identity" not in context
    assert "voice_and_tone" not in context


@pytest.mark.asyncio
async def test_build_context_times_out_blocking_governance_packet(monkeypatch):
    workspace = SimpleNamespace(
        id="ws-1",
        sandbox_config={},
        runtime_profile=None,
    )
    executor = object.__new__(WorkspaceAgentExecutor)
    executor.workspace = workspace
    executor.GOVERNANCE_PACKET_TIMEOUT_S = 0.05

    class _BlockingReadModel:
        def __init__(self, store=None):
            self.store = store

        async def build_for_workspace(self, workspace):
            time.sleep(0.2)
            return None

        def format_memory_packet_for_context(self, packet):
            return ""

    monkeypatch.setattr(
        "backend.app.services.governance.governance_context_read_model.GovernanceContextReadModel",
        _BlockingReadModel,
    )
    monkeypatch.setattr(
        "backend.app.services.mindscape_store.MindscapeStore",
        lambda: "store-instance",
    )

    context = await executor._build_context()

    assert "governance_context" not in context
    assert "memory_packet" not in context
