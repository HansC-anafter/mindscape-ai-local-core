from datetime import datetime, timezone

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.meeting_graph.task_projection import build_task_graph_nodes


def test_tool_execution_planner_contract_projects_work_graph_nodes():
    task = Task(
        id="task-tool-1",
        workspace_id="ws_demo",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="ig.ig_create_creative_space",
        task_type="tool_execution",
        status=TaskStatus.SUCCEEDED,
        params={
            "tool_name": "ig.ig_create_creative_space",
            "input_params": {"title": "Yoga"},
            "title": "Create creative space",
            "planner_contract_binding": {
                "binding_id": "planner_contract:abc123",
                "tool_name": "ig.ig_create_creative_space",
                "tool_code": "ig_create_creative_space",
                "pack_id": "ig",
                "resource_kind": "creative_space",
                "effect": "write",
                "approval_required": True,
                "idempotency": "idempotency_key",
            },
        },
        result={"creative_space_id": "space-yoga"},
        execution_context={
            "tool_name": "ig.ig_create_creative_space",
            "planner_contract_binding": {
                "binding_id": "planner_contract:abc123",
                "tool_name": "ig.ig_create_creative_space",
                "tool_code": "ig_create_creative_space",
                "pack_id": "ig",
                "resource_kind": "creative_space",
                "effect": "write",
                "approval_required": True,
                "idempotency": "idempotency_key",
            },
        },
        meeting_session_id="meeting-1",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    nodes, edges = build_task_graph_nodes(task)

    kinds = {node.kind for node in nodes}
    assert {
        "planner_contract_binding",
        "tool_call",
        "approval_gate",
        "runner_task",
        "tool_result",
        "object_write",
    }.issubset(kinds)
    assert any(edge.type == "requires_approval" for edge in edges)
    assert any(node.id == "tool-result-task-tool-1" for node in nodes)
