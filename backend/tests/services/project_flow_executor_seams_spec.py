from dataclasses import dataclass

import pytest

from backend.app.models.playbook_flow import FlowEdge, FlowNode
from backend.app.services.project import flow_executor
from backend.app.services.project.flow_executor import FlowExecutor


def _executor_without_init() -> FlowExecutor:
    return FlowExecutor.__new__(FlowExecutor)


def test_graph_helpers_build_sequence_and_order_nodes():
    executor = _executor_without_init()
    nodes = executor._build_nodes_from_playbook_sequence(["alpha", "beta", "gamma"])
    edges = [
        FlowEdge(from_node="node_1", to_node="node_2"),
        FlowEdge(from_node="node_2", to_node="node_3"),
    ]

    assert [node.playbook_code for node in nodes.values()] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert executor._get_execution_order(nodes, edges, completed_nodes=set()) == [
        "node_1",
        "node_2",
        "node_3",
    ]


def test_resume_predecessor_lookup_preserves_existing_rule():
    executor = _executor_without_init()
    nodes = {
        "node_1": FlowNode(id="node_1", playbook_code="alpha", name="Alpha"),
        "node_2": FlowNode(id="node_2", playbook_code="beta", name="Beta"),
        "node_3": FlowNode(id="node_3", playbook_code="gamma", name="Gamma"),
    }
    edges = [
        FlowEdge(from_node="node_1", to_node="node_2"),
        FlowEdge(from_node="node_2", to_node="node_3"),
    ]

    assert executor._get_completed_nodes_before(nodes, edges, "node_3") == {
        "node_1",
        "node_2",
    }


@pytest.mark.asyncio
async def test_node_retry_uses_backoff_and_registers_artifacts(monkeypatch):
    class FakeRunner:
        def __init__(self):
            self.calls = 0

        async def start_playbook_execution(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary")
            return {"execution_id": "exec-2"}

    class FakeArtifactRegistry:
        async def list_artifacts_by_node(self, **kwargs):
            return []

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    executor = _executor_without_init()
    executor.playbook_runner = FakeRunner()
    executor.artifact_registry = FakeArtifactRegistry()
    registered = []

    async def fake_register(**kwargs):
        registered.append(kwargs)

    executor._register_node_artifacts = fake_register
    monkeypatch.setattr(
        "backend.app.services.project.flow_executor_core.node_execution.asyncio.sleep",
        fake_sleep,
    )

    result = await executor._execute_node_with_retry(
        node=FlowNode(
            id="node_1",
            playbook_code="alpha",
            name="Alpha",
            inputs={"topic": "demo"},
        ),
        project_id="project-1",
        workspace_id="workspace-1",
        profile_id="profile-1",
        preserve_artifacts=True,
        max_retries=2,
    )

    assert sleeps == [1]
    assert executor.playbook_runner.calls == 2
    assert registered[0]["execution_id"] == "exec-2"
    assert result["status"] == "executed"
    assert result["attempt"] == 2


@pytest.mark.asyncio
async def test_existing_artifacts_skip_runner_execution():
    @dataclass
    class Artifact:
        artifact_id: str

    class FakeRunner:
        calls = 0

        async def start_playbook_execution(self, **kwargs):
            self.calls += 1
            return {"execution_id": "unexpected"}

    class FakeArtifactRegistry:
        async def list_artifacts_by_node(self, **kwargs):
            return [Artifact("artifact-1")]

    executor = _executor_without_init()
    executor.playbook_runner = FakeRunner()
    executor.artifact_registry = FakeArtifactRegistry()

    result = await executor._execute_node_with_retry(
        node=FlowNode(id="node_1", playbook_code="alpha", name="Alpha"),
        project_id="project-1",
        workspace_id="workspace-1",
        profile_id="profile-1",
        preserve_artifacts=True,
        max_retries=3,
    )

    assert executor.playbook_runner.calls == 0
    assert result == {
        "status": "skipped",
        "reason": "artifacts_exist",
        "artifacts": ["artifact-1"],
    }


def test_public_facade_keeps_flow_executor_surface():
    assert hasattr(flow_executor, "FlowExecutionError")
    assert hasattr(FlowExecutor, "execute_flow")
    assert hasattr(FlowExecutor, "resume_from_checkpoint")
