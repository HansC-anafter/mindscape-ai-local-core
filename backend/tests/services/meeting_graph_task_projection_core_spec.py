from datetime import datetime, timezone
from pathlib import Path
import re

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.meeting_graph.task_projection import build_task_graph_nodes


REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / ".git").exists() and (parent / "backend/app").exists()
)
SOURCE_PATHS = [
    REPO_ROOT / "backend/app/services/meeting_graph/task_projection.py",
    REPO_ROOT / "backend/app/services/meeting_graph/task_projection_core/__init__.py",
    REPO_ROOT / "backend/app/services/meeting_graph/task_projection_core/common.py",
    REPO_ROOT / "backend/app/services/meeting_graph/task_projection_core/planner_contract.py",
    REPO_ROOT / "backend/app/services/meeting_graph/task_projection_core/planner_tool_plan.py",
    REPO_ROOT / "backend/app/services/meeting_graph/task_projection_core/object_action.py",
]
RESOURCE_MARKER_TERMS = (
    "Mindscape" + "Store",
    "session" + "maker",
    "create" + "_engine",
    "Pg" + "Bouncer",
    "Queue" + "(",
    "Thread" + "(",
    "Process" + "(",
    "red" + "is",
    "poll" + "ing",
    "Event" + "Source",
    "Web" + "Socket",
    "web" + "socket",
    "set" + "Interval",
    "set" + "Timeout",
    "work" + "er",
    "http" + "x",
    "request" + "s",
    "slee" + "p",
    "Fast" + "API",
    "API" + "Router",
)
RESOURCE_MARKERS = re.compile("|".join(re.escape(term) for term in RESOURCE_MARKER_TERMS))
SOURCE_LANGUAGE_MARKERS = re.compile(
    r"[\u4e00-\u9fff]|[\U0001f600-\U0001f64f]"
)


def _task(**overrides):
    base = {
        "id": "task-demo",
        "workspace_id": "ws_demo",
        "message_id": "msg-1",
        "execution_id": "exec-1",
        "pack_id": "meeting.demo",
        "task_type": "tool_execution",
        "status": TaskStatus.SUCCEEDED,
        "params": {},
        "result": {},
        "execution_context": {},
        "meeting_session_id": "meeting-1",
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return Task(**base)


def test_public_facade_projects_planner_contract_branch():
    binding = {
        "binding_id": "planner_contract:abc123",
        "tool_name": "ig.ig_create_creative_space",
        "resource_kind": "creative_space",
        "effect": "write",
        "approval_required": True,
        "idempotency": "idempotency_key",
    }
    task = _task(
        id="task-tool-1",
        pack_id="ig.ig_create_creative_space",
        params={
            "tool_name": "ig.ig_create_creative_space",
            "title": "Create creative space",
            "planner_contract_binding": binding,
        },
        result={"creative_space_id": "space-yoga"},
        execution_context={"planner_contract_binding": binding},
    )

    nodes, edges = build_task_graph_nodes(task)

    assert {"planner_contract_binding", "tool_call", "approval_gate"}.issubset(
        {node.kind for node in nodes}
    )
    assert any(edge.type == "requires_approval" for edge in edges)


def test_public_facade_projects_planner_tool_plan_branch():
    plan = {
        "plan_id": "plan-1",
        "pack_id": "ig",
        "categories": [{"category_id": "creative", "label": "Creative"}],
        "steps": [
            {
                "step_id": "step-1",
                "category_id": "creative",
                "role": "writer",
                "tool_name": "ig.ig_create_creative_space",
                "effect": "write",
                "resource_kind": "creative_space",
            }
        ],
    }
    task = _task(
        id="task-plan-1",
        pack_id="meeting.execute_planner_tool_plan",
        execution_context={"inputs": {"planner_tool_plan": plan}},
        result={"result": {"status": "success", "plan_steps": [{"step_id": "step-1", "status": "success"}]}},
    )

    nodes, edges = build_task_graph_nodes(task)

    assert {"planner_tool_plan", "planner_category", "tool_call", "tool_result"}.issubset(
        {node.kind for node in nodes}
    )
    assert any(edge.type == "contributes" for edge in edges)


def test_public_facade_projects_object_action_branch():
    task = _task(
        id="task-action-1",
        task_type="object_action",
        pack_id="object.action",
        execution_context={
            "inputs": {
                "object_action_plan_id": "plan-1",
                "meeting_command": "Create an output",
                "object_action_entries": [
                    {
                        "role": "source",
                        "ref": {
                            "uri": "object://source/1",
                            "object_kind": "brief",
                            "object_id": "brief-1",
                        },
                    }
                ],
            },
            "object_action_closure": {
                "status": "completed",
                "indexed_output_count": 1,
                "indexed_relation_count": 1,
                "output_refs": [
                    {
                        "uri": "object://asset/1",
                        "object_kind": "generated_asset",
                        "object_id": "asset-1",
                    }
                ],
            },
        },
    )

    nodes, edges = build_task_graph_nodes(task)

    assert {"command", "run", "object", "result", "artifact"}.issubset(
        {node.kind for node in nodes}
    )
    assert any(edge.type == "produced" for edge in edges)


def test_task_projection_files_stay_below_line_gate():
    touched_paths = SOURCE_PATHS + [Path(__file__)]
    over_limit = {
        str(path.relative_to(REPO_ROOT)): len(path.read_text().splitlines())
        for path in touched_paths
        if len(path.read_text().splitlines()) > 500
    }
    assert over_limit == {}


def test_task_projection_core_has_no_shared_resource_markers():
    matches = {
        path.name: RESOURCE_MARKERS.findall(path.read_text())
        for path in SOURCE_PATHS
        if path.name != "task_projection.py"
    }
    assert matches == {path.name: [] for path in SOURCE_PATHS if path.name != "task_projection.py"}


def test_task_projection_touched_sources_have_no_chinese_or_emoji():
    touched_paths = SOURCE_PATHS + [Path(__file__)]
    matches = {
        path.name: SOURCE_LANGUAGE_MARKERS.findall(path.read_text())
        for path in touched_paths
    }
    assert matches == {path.name: [] for path in touched_paths}
